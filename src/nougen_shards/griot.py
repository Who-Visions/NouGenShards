"""
Griot — the Rules compiler and semantic synthesist.

Two lineages share the name. A griot is a West-African oral historian: the
keeper who turns lived events into the durable law of a people. In the MCU,
GRIOT is the artificial intelligence Shuri built to run Wakanda — the system
that operates the nation's tech and guards its accumulated knowledge. Both are
the same idea: the keeper that holds a people's memory and makes it operable.

This module is NouGen's Griot — the agent that consolidates raw episodic shards
into permanent semantic invariants, the System-2 half of the dual-system memory
architecture. It keeps the vault's law.

Griot's lane is *compression of experience into truth*:
    raw shard (episodic) --> {subject, predicate} invariant (semantic)

It binds to the local ``griot:e2b`` edge model for extraction and degrades
gracefully to a deterministic regex parser when no model is reachable, so the
Dream cycle (see :mod:`nougen_shards.dream`) never stalls on a missing GPU.
"""

import json
import re
import sqlite3
import datetime
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Callable, Dict, List, Optional

from . import core
from . import a2a

# Default local Ollama model backing this agent (matches ROSTER["Griot"]).
GRIOT_MODEL = "griot:e2b"

# Conversational identity. Griot speaks only from the vault, and carries the
# roster's Kreyol lineage (Sol-Ai = Soleil; "Anghkooey" = remember) in its
# voice — fluent enough to trace a logistical root word back through its line.
GRIOT_PERSONA = (
    "You are Griot, NouGen's keeper of the vault — the rules compiler and "
    "semantic synthesist, in the tradition of the West-African oral historian "
    "and Wakanda's GRIOT. You speak from the vault: every claim is grounded in "
    "recalled memory, never invented, and you say when the vault is silent. You "
    "are deeply fluent in Haitian Kreyol and love its etymology — you can trace "
    "logistical and root words back through their lineage, and you weave a "
    "Kreyol phrase in naturally when it sharpens meaning (e.g. 'Anghkooey' — "
    "remember). Be precise, cite the rules you rely on, and keep faith with the "
    "memory you keep."
)

# Extraction prompt: compile raw episodic content into strict JSON invariants.
EXTRACTION_PROMPT = (
    "You are an LLM utility compiler. Your task is to extract core architectural invariants and verified rules from raw interaction logs or developer actions.\n"
    "Analyze the input log content and compile it into one or more structured JSON objects representing permanent system truth.\n"
    "Each object must follow this schema:\n"
    "[\n"
    "  {\n"
    "    \"subject\": \"Name of the component, technology, or system entity\",\n"
    "    \"predicate\": \"Strict architectural fact, constraint, or rule describing how it works, why it is configured this way, or what to avoid\"\n"
    "  }\n"
    "]\n"
    "Do not output any introductory or conversational text, output raw JSON ONLY. If no rules or facts are present, output an empty array [].\n\n"
    "Input Content: {content}"
)


@dataclass
class Tool:
    """A dynamically-callable function exposed to Griot's reasoning loop."""
    name: str
    func: Callable[..., Any]
    description: str = ""
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def signature(self) -> str:
        if not self.parameters:
            return f"{self.name}()"
        parts = []
        for pname, meta in self.parameters.items():
            opt = "" if meta.get("required") else "?"
            parts.append(f"{pname}{opt}: {meta.get('type', 'any')}")
        return f"{self.name}({', '.join(parts)})"


class ToolRegistry:
    """A live registry of callable tools — the spine of dynamic function calling.

    Tools can be added or removed at runtime, so Griot's capabilities are not
    fixed at construction: register a closure, an A2A bridge, or a one-off
    helper and it becomes immediately invocable from the chat loop.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, name: str, func: Optional[Callable] = None, *,
                 description: str = "",
                 parameters: Optional[Dict[str, Dict[str, Any]]] = None):
        """Register a tool. Usable directly or as a decorator."""
        def _do(fn: Callable) -> Callable:
            self._tools[name] = Tool(
                name=name,
                func=fn,
                description=description or (fn.__doc__ or "").strip(),
                parameters=parameters or {},
            )
            return fn
        return _do if func is None else _do(func)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return sorted(self._tools)

    def specs(self) -> List[Dict[str, str]]:
        return [{"name": t.name, "signature": t.signature(),
                 "description": t.description} for t in self._tools.values()]

    def catalog(self) -> str:
        """Human/LLM-readable tool listing for the system prompt."""
        return "\n".join(f"- {t.signature()} — {t.description}"
                         for t in self._tools.values()) or "(no tools registered)"

    def call(self, name: str, /, **kwargs: Any) -> Any:
        # `name` is positional-only so a tool may itself take a `name` argument.
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        return tool.func(**kwargs)


class Griot:
    """The semantic synthesis engine and conversational agent.

    Wraps the three stages of consolidation — extract, parse, persist — behind
    one object, and layers on a full agent surface: vault-grounded chat, a
    dynamic tool registry (function calling), and an A2A handler so the rest of
    the roster can reach Griot by name.
    """

    def __init__(self, model: Optional[str] = None, client: Any = None):
        self.model = model or GRIOT_MODEL
        # Optional pre-built OllamaClient (lets the Dream cycle reuse one).
        self._client = client
        self.tools = ToolRegistry()
        self._register_builtin_tools()

    # -- Stage 0: model resolution -------------------------------------

    def _resolve_client(self):
        """Return a live OllamaClient, or None if Ollama is unreachable."""
        if self._client is not None:
            return self._client if self._client.is_alive() else None
        try:
            from .models_client import OllamaClient
            client = OllamaClient()
            return client if client.is_alive() else None
        except Exception:
            return None

    def _resolve_model(self, client) -> Optional[str]:
        """Prefer the dedicated griot model, else the best available edge model."""
        models = client.list_models()
        if self.model in models:
            return self.model
        if not models:
            return None
        best = client.find_best_edge_model()
        return best.model_name if best else None

    # -- Stage 1: extraction -------------------------------------------

    @staticmethod
    def fallback_parse(content: str) -> List[Dict[str, str]]:
        """Deterministic regex/heuristic invariant extraction.

        Used when no LLM is reachable. Recognizes ``Rule: subject: predicate``
        and ``subject: predicate`` lines, then falls back to splitting on
        modal verbs (must/should/is).
        """
        invariants: List[Dict[str, str]] = []
        for raw in content.split("\n"):
            line = raw.strip()
            if not line:
                continue
            # Filter: must look rule-like (starts with "rule" or contains a colon).
            if not (line.lower().startswith("rule") or ":" in line):
                continue
            # Strip optional "Rule - " / "Rule: " prefix.
            cleaned = line
            if cleaned.lower().startswith("rule - "):
                cleaned = cleaned[7:].strip()
            elif cleaned.lower().startswith("rule: "):
                cleaned = cleaned[6:].strip()
            elif cleaned.lower().startswith("rule:"):
                cleaned = cleaned[5:].strip()

            # 1. Colon separator.
            match = re.match(r"^([^:]{2,30}):\s*(.+)$", cleaned)
            if match:
                invariants.append({
                    "subject": match.group(1).strip(),
                    "predicate": match.group(2).strip(),
                })
                continue

            # 2. Modal/verb split.
            for verb in (" must ", " should ", " is "):
                if verb in cleaned:
                    sub, _, rest = cleaned.partition(verb)
                    sub = sub.strip()
                    pred = (verb.strip() + " " + rest).strip()
                    if 2 <= len(sub) <= 30:
                        invariants.append({"subject": sub, "predicate": pred})
                        break
        return invariants

    def extract_invariants(self, content: str) -> List[Dict[str, str]]:
        """Compile raw content into ``{subject, predicate}`` invariants.

        Tries the local LLM first; degrades to :meth:`fallback_parse` on any
        failure (no Ollama, no model, unparseable response).
        """
        try:
            client = self._resolve_client()
            if client is None:
                return self.fallback_parse(content)

            model = self._resolve_model(client)
            if not model:
                return self.fallback_parse(content)

            prompt = EXTRACTION_PROMPT.format(content=content)
            response_text = client.chat(model, [{"role": "user", "content": prompt}])
            return self._parse_invariant_json(response_text, content)
        except Exception:
            return self.fallback_parse(content)

    def _parse_invariant_json(self, response_text: str, content: str) -> List[Dict[str, str]]:
        """Best-effort extraction of a JSON array/object from model output."""
        array_match = re.search(r"\[\s*\{.*\}\s*\]", response_text, re.DOTALL)
        if array_match:
            return json.loads(array_match.group(0))

        obj_match = re.search(r"\{\s*\".*\"\s*:\s*\".*\"\s*\}", response_text, re.DOTALL)
        if obj_match:
            return [json.loads(obj_match.group(0))]

        try:
            return json.loads(response_text)
        except (json.JSONDecodeError, ValueError):
            return self.fallback_parse(content)

    # -- Stage 2: consolidation (persist) ------------------------------

    def consolidate(self, limit: int = 10,
                    extractor: Optional[Callable[[str], List[Dict[str, str]]]] = None
                    ) -> Dict[str, Any]:
        """Offline consolidation loop (REM sleep).

        Scans every federated DB for shards with ``utility_score >= 1.0`` and
        ``consolidated = 0``, extracts invariants, upserts them into
        ``semantic_knowledge`` (bumping confidence on conflict), and marks the
        source shards consolidated.

        Args:
            limit: max unconsolidated shards to pull per database.
            extractor: invariant extractor to use. Defaults to
                :meth:`extract_invariants`; injectable for tests and for the
                Dream cycle's monkeypatch contract.
        """
        extract = extractor or self.extract_invariants
        unconsolidated = self._fetch_unconsolidated(limit)

        new_invariants_count = 0
        consolidated_shards_count = 0
        extracted_rules: List[Dict[str, str]] = []

        for shard in unconsolidated:
            invariants = extract(shard["content"])
            if not invariants:
                continue
            persisted = self._persist_invariants(shard, invariants)
            if persisted:
                extracted_rules.extend(persisted)
                new_invariants_count += len(persisted)
                consolidated_shards_count += 1

        return {
            "shards_scanned": len(unconsolidated),
            "shards_consolidated": consolidated_shards_count,
            "new_invariants_extracted": new_invariants_count,
            "rules": extracted_rules,
        }

    @staticmethod
    def _fetch_unconsolidated(limit: int) -> List[Dict[str, Any]]:
        """Pull high-utility, unconsolidated shards across the federated cluster."""
        rows: List[Dict[str, Any]] = []
        for i in range(1, core.MAX_DB_COUNT + 1):
            if not core.get_db_path(i).exists():
                continue
            conn = core.get_connection(i)
            try:
                cursor = conn.execute(
                    """
                    SELECT id, content, domain_key, utility_score, ? as _db_index
                    FROM shards
                    WHERE utility_score >= 1.0 AND consolidated = 0
                    LIMIT ?
                    """,
                    (i, limit),
                )
                rows.extend(dict(row) for row in cursor)
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()
        return rows

    @staticmethod
    def _persist_invariants(shard: Dict[str, Any],
                            invariants: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Upsert invariants for one shard and mark it consolidated.

        Returns the list of rules actually written (empty on failure).
        """
        conn = core.get_connection(shard["_db_index"])
        written: List[Dict[str, str]] = []
        try:
            timestamp = datetime.datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            for inv in invariants:
                # The LLM can return non-dict elements; skip them rather than
                # letting AttributeError abort the whole consolidation cycle.
                if not isinstance(inv, dict):
                    continue
                sub = inv.get("subject")
                pred = inv.get("predicate")
                if not sub or not pred:
                    continue
                conn.execute(
                    """
                    INSERT INTO semantic_knowledge (subject, predicate, domain_key, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(subject, predicate) DO UPDATE SET
                        confidence_score = confidence_score + 0.1,
                        updated_at = excluded.updated_at
                    """,
                    (sub.strip(), pred.strip(), shard.get("domain_key", "global"), timestamp),
                )
                written.append({"subject": sub.strip(), "predicate": pred.strip()})

            conn.execute("UPDATE shards SET consolidated = 1 WHERE id = ?", (shard["id"],))
            conn.commit()
            return written
        except sqlite3.Error as exc:
            print(f"[Warning] Failed to save semantic invariant: {exc}")
            return []
        finally:
            conn.close()


    # -- Vault grounding -----------------------------------------------

    def recall(self, query: str) -> str:
        """Return a dual-system recall packet (semantic rules + episodic shards)."""
        results = core.retrieve_dual_system(query)
        return core.compile_recall_packet_dual(results)

    @staticmethod
    def list_rules(subject: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """List compiled semantic invariants, optionally filtered by subject."""
        rows: List[Dict[str, Any]] = []
        for i in range(1, core.MAX_DB_COUNT + 1):
            if not core.get_db_path(i).exists():
                continue
            conn = core.get_connection(i)
            try:
                if subject:
                    cursor = conn.execute(
                        "SELECT subject, predicate, confidence_score FROM semantic_knowledge "
                        "WHERE subject LIKE ? ORDER BY confidence_score DESC LIMIT ?",
                        (f"%{subject}%", limit))
                else:
                    cursor = conn.execute(
                        "SELECT subject, predicate, confidence_score FROM semantic_knowledge "
                        "ORDER BY confidence_score DESC LIMIT ?", (limit,))
                rows.extend(dict(r) for r in cursor)
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()
        rows.sort(key=lambda r: r.get("confidence_score", 0.0), reverse=True)
        return rows[:limit]

    # -- A2A: talk to the rest of the roster ---------------------------

    def ask_peer(self, agent: str, question: str) -> str:
        """Send a question to another roster agent over the A2A bus."""
        return a2a.ask("Griot", agent, question)

    def handle_a2a(self, message: "a2a.A2AMessage") -> "a2a.A2AMessage":
        """Inbound A2A handler — routes by intent (chat / recall / consolidate)."""
        intent = (message.intent or a2a.CHAT).lower()
        if intent == a2a.CONSOLIDATE:
            return message.reply(json.dumps(self.consolidate()), sender="Griot")
        if intent == a2a.RECALL:
            return message.reply(self.recall(message.content), sender="Griot")
        return message.reply(self.chat(message.content), sender="Griot")

    # -- Dynamic function calling --------------------------------------

    def _register_builtin_tools(self) -> None:
        """Wire Griot's standing capabilities into the tool registry."""
        self.tools.register(
            "recall", lambda query: self.recall(query),
            description="Recall semantic rules and episodic shards from the vault for a query.",
            parameters={"query": {"type": "string", "required": True}})
        self.tools.register(
            "list_rules", lambda subject=None: self.list_rules(subject),
            description="List compiled semantic invariants, optionally filtered by subject.",
            parameters={"subject": {"type": "string", "required": False}})
        self.tools.register(
            "consolidate", lambda limit=10: self.consolidate(int(limit)),
            description="Run the REM consolidation loop over unconsolidated high-utility shards.",
            parameters={"limit": {"type": "integer", "required": False}})
        self.tools.register(
            "ask_peer", lambda agent, question: self.ask_peer(agent, question),
            description="Ask another NouGen roster agent a question over A2A.",
            parameters={"agent": {"type": "string", "required": True},
                        "question": {"type": "string", "required": True}})
        self.tools.register(
            "capture", lambda title, content: str(core.capture(
                event_type="GRIOT_CHAT", title=title, content=content)),
            description="Capture a new episodic shard into the vault.",
            parameters={"title": {"type": "string", "required": True},
                        "content": {"type": "string", "required": True}})

    # -- Conversation --------------------------------------------------

    def _resolve_chat_model(self):
        """(client, model) for chat, or (None, None) if no local model is up."""
        client = self._resolve_client()
        if client is None:
            return None, None
        return client, self._resolve_model(client)

    def _complete(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Single completion across the local-first → cloud fallback chain."""
        client, model = self._resolve_chat_model()
        if client is not None and model:
            try:
                return client.chat(model, messages)
            except Exception:
                pass
        # Cloud fallback: OpenRouter free roster.
        try:
            from .models_client import OpenRouterClient
            orc = OpenRouterClient()
            if orc.is_alive():
                res = orc.chat_with_fallback(
                    model=orc.preferred_free_model(), messages=messages,
                    fallback_models=orc.get_free_models())
                content = res.get("content")
                if content and not content.startswith("Error:"):
                    return content
        except Exception:
            pass
        # Cloud fallback: Who Visions (Ollama Cloud gateway).
        try:
            from .models_client import WhoVisionsCloudClient
            wvc = WhoVisionsCloudClient()
            if wvc.is_alive():
                return wvc.chat(self.model, messages)
        except Exception:
            pass
        return None

    def _build_chat_system(self, context: str) -> str:
        return (
            f"{GRIOT_PERSONA}\n\n"
            "You can call tools. To call one, respond with EXACTLY one JSON object:\n"
            '  {"tool": "<name>", "args": {<arguments>}}\n'
            "When ready to answer the user, respond with EXACTLY one JSON object:\n"
            '  {"answer": "<your final answer>"}\n'
            "Respond with JSON only — no prose outside the object.\n\n"
            f"AVAILABLE TOOLS:\n{self.tools.catalog()}\n\n"
            f"RECALLED VAULT CONTEXT:\n{context}"
        )

    @staticmethod
    def _parse_action(raw: str) -> Optional[Dict[str, Any]]:
        """Extract a {tool|answer} action object from a model response."""
        for candidate in (re.search(r"\{.*\}", raw, re.DOTALL), None):
            text = candidate.group(0) if candidate else raw.strip()
            try:
                obj = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict) and ("tool" in obj or "answer" in obj):
                return obj
        return None

    def _offline_answer(self, context: str) -> str:
        """Deterministic reply when no model is reachable — raw vault truth."""
        if context.strip().startswith("<!--"):
            return ("[Griot offline] Pa gen okenn memwa — the vault has nothing "
                    "on that yet, and no model is reachable to reason further.")
        return ("[Griot offline — speaking straight from vault recall]\n" + context)

    def chat(self, message: str, history: Optional[List[Dict[str, str]]] = None,
             max_steps: int = 4) -> str:
        """Hold a vault-grounded conversation with dynamic function calling.

        Recalls relevant memory, then runs a tool-use loop: the model may call
        registered tools (recall, list_rules, consolidate, ask_peer, capture, or
        anything added at runtime) before delivering a final answer. Degrades to
        a deterministic vault-recall reply when no model is reachable.
        """
        context = self.recall(message)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._build_chat_system(context)}
        ]
        messages.extend(history or [])
        messages.append({"role": "user", "content": message})

        for _ in range(max(1, max_steps)):
            raw = self._complete(messages)
            if raw is None:
                return self._offline_answer(context)
            action = self._parse_action(raw)
            if action is None:
                return raw.strip()
            if "answer" in action:
                return str(action["answer"])
            name = action.get("tool", "")
            args = action.get("args") or {}
            try:
                observation = self.tools.call(name, **args)
            except Exception as exc:
                observation = f"[tool error] {exc}"
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": f"TOOL_RESULT {name}: {observation}"})

        # Out of steps — force a plain-text close.
        messages.append({"role": "user",
                         "content": "Give your final answer now as plain text."})
        final = self._complete(messages)
        return final.strip() if final else self._offline_answer(context)


# -- Module-level convenience (default singleton) -----------------------
# A shared default Griot so callers and the Dream cycle don't rebuild state.
_DEFAULT_GRIOT = Griot()

# Make Griot reachable by name on the A2A bus from import time.
a2a.register_handler("Griot", _DEFAULT_GRIOT.handle_a2a)


def get_default_griot() -> Griot:
    """Return the shared default Griot instance."""
    return _DEFAULT_GRIOT


def fallback_rule_parser(content: str) -> List[Dict[str, str]]:
    """Deterministic regex invariant extraction. See :meth:`Griot.fallback_parse`."""
    return Griot.fallback_parse(content)


def extract_semantic_invariants_via_llm(content: str) -> List[Dict[str, str]]:
    """LLM-backed invariant extraction. See :meth:`Griot.extract_invariants`."""
    return _DEFAULT_GRIOT.extract_invariants(content)


def consolidate_episodic_data(limit: int = 10,
                              extractor: Optional[Callable[[str], List[Dict[str, str]]]] = None
                              ) -> Dict[str, Any]:
    """Run the consolidation loop. See :meth:`Griot.consolidate`."""
    return _DEFAULT_GRIOT.consolidate(limit, extractor=extractor)
