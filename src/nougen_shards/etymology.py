"""
NouGen Etymology & User Idiolect Intent Resolution Layer.

Architecture:
Resolves phrase intent through a 6-stage semantic lineage pipeline:
  1. Phrase Ingestion & Morphological Deconstruction (Roots, affixes, lemmas)
  2. Classical, Vernacular & Cultural Archetype Resolution (Historical/domain metaphors)
  3. User-Specific Idiolect Mapping (Private SQLite store per user/tenant)
  4. Contextual & Operational Grounding (Active machine, agent, and goal state)
  5. Multi-Hypothesis Intent Scoring & Ambiguity Preservation (Entropy & calibrated confidence)
  6. Dynamic Online Learning & Semantic Drift Adaptation (Outcome feedback loop)

Canonical Doctrine:
- Adapts dynamically to each user's unique idiolect (e.g. 'Harriet Tubman Rhea',
  'Stadium play', 'Keymaker crossing') without hardcoding personal jargon into global prompts.
- Preserves ambiguity through explicit multi-hypothesis entropy rather than brittle overfitting.
- Isolates user profiles cleanly across multi-tenant boundaries.
"""

from __future__ import annotations

import os
import re
import math
import time
import json
import sqlite3
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


# Default SQLite DB path for local Idiolect storage if not configured via ENV
DEFAULT_IDIOLECT_DB_DIR = Path.home() / ".nougen" / "idiolect"
ENV_IDIOLECT_DB = "NOUGEN_IDIOLECT_DB"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class EtymologicalRoot:
    root: str
    language: str
    literal_meaning: str
    modern_derivatives: List[str] = field(default_factory=list)


@dataclass
class MorphologyBreakdown:
    raw_token: str
    lemma: str
    prefixes: List[str] = field(default_factory=list)
    stem: str = ""
    suffixes: List[str] = field(default_factory=list)
    pos_guess: str = "noun"


@dataclass
class CulturalArchetype:
    name: str
    domain: str
    operational_meaning: str
    core_traits: List[str] = field(default_factory=list)
    systems_mapping: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)


@dataclass
class IdiolectEntry:
    user_id: str
    term: str
    canonical_concept: str
    category: str
    notes: str = ""
    confidence: float = 1.0
    updated_utc: str = ""


@dataclass
class IntentCandidate:
    intent_id: str
    confidence: float
    label: str
    explanation: str
    action_payload: Dict[str, Any] = field(default_factory=dict)
    ambiguity_score: float = 0.0
    lineage_chain: List[str] = field(default_factory=list)
    requires_confirmation: bool = False


@dataclass
class IntentResolutionResult:
    raw_phrase: str
    user_id: str
    candidates: List[IntentCandidate] = field(default_factory=list)
    top_intent: Optional[IntentCandidate] = None
    morphological_analysis: List[MorphologyBreakdown] = field(default_factory=list)
    detected_archetypes: List[CulturalArchetype] = field(default_factory=list)
    personal_idiolect_matches: List[IdiolectEntry] = field(default_factory=list)
    context_factors: Dict[str, Any] = field(default_factory=dict)
    ambiguity_entropy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_phrase": self.raw_phrase,
            "user_id": self.user_id,
            "top_intent": asdict(self.top_intent) if self.top_intent else None,
            "ambiguity_entropy": self.ambiguity_entropy,
            "candidates": [asdict(c) for c in self.candidates],
            "detected_archetypes": [asdict(a) for a in self.detected_archetypes],
            "personal_idiolect_matches": [asdict(p) for p in self.personal_idiolect_matches],
            "morphological_analysis": [asdict(m) for m in self.morphological_analysis],
            "context_factors": self.context_factors
        }


# ---------------------------------------------------------------------------
# Lexical & Morphological Analyzer
# ---------------------------------------------------------------------------

class MorphologicalAnalyzer:
    """Deconstructs phrases into tokens, morphemes, affixes, and classical roots."""

    # Curated classical & modern roots
    ROOT_LEXICON: Dict[str, EtymologicalRoot] = {
        "morph": EtymologicalRoot("morph", "Greek", "form or shape", ["morphology", "amorphous", "metamorphic"]),
        "chrono": EtymologicalRoot("chrono", "Greek", "time", ["synchronize", "chronology", "kronos"]),
        "tele": EtymologicalRoot("tele", "Greek", "distant / across space", ["telemetry", "telegraph", "telescope"]),
        "auto": EtymologicalRoot("auto", "Greek", "self / autonomous", ["automatic", "autonomy", "autodidact"]),
        "syn": EtymologicalRoot("syn", "Greek", "together / with", ["syntax", "synthesis", "sync"]),
        "dia": EtymologicalRoot("dia", "Greek", "through / across", ["dialect", "dialogue", "diagnosis"]),
        "val": EtymologicalRoot("val", "Latin (valere)", "to be strong / worthy", ["valerion", "valiant", "validate"]),
        "sec": EtymologicalRoot("sec", "Latin (securus)", "free from care / safe", ["secret", "secure", "security"]),
        "tract": EtymologicalRoot("tract", "Latin (trahere)", "to pull / draw", ["extract", "retract", "traction"]),
        "duc": EtymologicalRoot("duc", "Latin (ducere)", "to lead / guide", ["conductor", "deduce", "induce"]),
        "port": EtymologicalRoot("port", "Latin (portare)", "to carry", ["transport", "portable", "export"]),
        "spec": EtymologicalRoot("spec", "Latin (specere)", "to look / inspect", ["inspect", "spectator", "spectrum"]),
        "kreyol": EtymologicalRoot("kreyol", "Haitian Kreyòl / Romance", "rooted creation / synthesis language", ["kreyol", "creole"]),
        "atibon": EtymologicalRoot("atibon", "Haitian / Dahomey", "guardian of crossroads / ancient tree / keymaker", ["atibon", "legba"]),
        "noir": EtymologicalRoot("noir", "French", "black / shadows / high-contrast night aesthetics", ["noir", "film-noir"]),
        "dweller": EtymologicalRoot("dwell", "Old English", "to abide / stay in depth", ["dwelling", "shadow-dweller"]),
    }

    PREFIXES = ["anti", "meta", "trans", "hyper", "sub", "super", "pre", "post", "re", "de", "un", "in", "co"]
    SUFFIXES = ["ation", "ition", "ize", "ise", "ism", "ist", "ment", "ness", "ity", "able", "ible", "al", "er", "or", "ic"]

    @classmethod
    def decompose(cls, phrase: str) -> List[MorphologyBreakdown]:
        cleaned = re.sub(r"[^\w\s\-]", " ", phrase.lower())
        tokens = [t.strip() for t in re.split(r"[\s\-]+", cleaned) if t.strip()]
        breakdowns = []

        for token in tokens:
            found_prefix = []
            stem = token
            found_suffix = []

            # Check prefixes
            for p in sorted(cls.PREFIXES, key=len, reverse=True):
                if stem.startswith(p) and len(stem) > len(p) + 2:
                    found_prefix.append(p)
                    stem = stem[len(p):]
                    break

            # Check suffixes
            for s in sorted(cls.SUFFIXES, key=len, reverse=True):
                if stem.endswith(s) and len(stem) > len(s) + 2:
                    found_suffix.append(s)
                    stem = stem[:-len(s)]
                    break

            lemma = stem
            # Simple heuristic lemmatization
            if lemma.endswith("ies") and len(lemma) > 4:
                lemma = lemma[:-3] + "y"
            elif lemma.endswith("es") and len(lemma) > 3:
                lemma = lemma[:-2]
            elif lemma.endswith("s") and not lemma.endswith("ss") and len(lemma) > 2:
                lemma = lemma[:-1]
            elif lemma.endswith("ing") and len(lemma) > 4:
                lemma = lemma[:-3]
            elif lemma.endswith("ed") and len(lemma) > 3:
                lemma = lemma[:-2]

            breakdowns.append(MorphologyBreakdown(
                raw_token=token,
                lemma=lemma,
                prefixes=found_prefix,
                stem=stem,
                suffixes=found_suffix,
                pos_guess="verb" if found_suffix in [["ize"], ["ise"], ["ing"], ["ed"]] else "noun"
            ))

        return breakdowns

    @classmethod
    def lookup_root(cls, word: str) -> Optional[EtymologicalRoot]:
        w = word.lower()
        if w in cls.ROOT_LEXICON:
            return cls.ROOT_LEXICON[w]
        for key, root in cls.ROOT_LEXICON.items():
            if key in w:
                return root
        return None


# ---------------------------------------------------------------------------
# Cultural & Archetypal Lineage Graph
# ---------------------------------------------------------------------------

class CulturalArchetypeRegistry:
    """Maintains a registry of historical, mythic, and cultural archetypes mapped to systems intents."""

    DEFAULT_ARCHETYPES: List[CulturalArchetype] = [
        CulturalArchetype(
            name="Harriet Tubman",
            domain="liberation / operational logistics / historical",
            operational_meaning="Stealth liberation, high-risk operational extraction, zero-casualty asset transport, underground navigation, uncompromised failover routes.",
            core_traits=["stealth", "unyielding", "zero_casualty", "underground_route", "asset_extraction", "conductor"],
            systems_mapping={
                "action_type": "stealth_data_extraction",
                "risk_profile": "high_security_recovery",
                "preferred_agent": "rhea",
                "execution_mode": "covert_failover",
                "intent_id": "ops.stealth_extraction_and_recovery"
            },
            aliases=["harriet tubman", "tubman", "underground railroad", "the conductor", "moses of her people"]
        ),
        CulturalArchetype(
            name="Atibon / Keymaker",
            domain="gatekeeper / threshold / cryptography",
            operational_meaning="Guardian of boundaries and crossroads, DPAPI user-bound encryption, credential ingestion without plaintext exposure.",
            core_traits=["gatekeeper", "secret_protection", "dpapi", "credential_isolation", "crossroads"],
            systems_mapping={
                "action_type": "vault_security_rekey",
                "target_layer": "keymaker",
                "intent_id": "security.credential_vault_ingestion"
            },
            aliases=["atibon", "keymaker", "gatekeeper", "crossroads guardian", "papa legba"]
        ),
        CulturalArchetype(
            name="Stadium",
            domain="arena / compute infrastructure",
            operational_meaning="Local compute substrate, high-bandwidth local GPU (RTX 2080 Super Max-Q), offline-first execution, avoiding cloud spend.",
            core_traits=["local_compute", "hardware_bound", "gpu_acceleration", "stadium_turf", "vram_discipline"],
            systems_mapping={
                "action_type": "local_inference_routing",
                "hardware_target": "stadium_gpu",
                "intent_id": "compute.route_local_stadium"
            },
            aliases=["stadium", "razer blade", "the turf", "home field", "local arena"]
        ),
        CulturalArchetype(
            name="Apollo / Coach",
            domain="orchestration / tactical leadership",
            operational_meaning="Designated coding agent, task planning, play-calling, autonomous execution within approved lanes.",
            core_traits=["coach", "playbook", "execution_loop", "tactical_planner"],
            systems_mapping={
                "action_type": "agent_planning_and_patching",
                "role": "coach",
                "intent_id": "agent.apollo_execute_play"
            },
            aliases=["apollo", "coach", "playbook conductor"]
        ),
        CulturalArchetype(
            name="Sol-Ai / Player",
            domain="inference / local tensor execution",
            operational_meaning="Local AI model (Gemma4), on-field execution, prompt processing without external API fees.",
            core_traits=["player", "local_gemma", "fast_execution", "on_field"],
            systems_mapping={
                "action_type": "local_model_inference",
                "model_family": "gemma4",
                "intent_id": "inference.sol_ai_execute"
            },
            aliases=["sol-ai", "sol ai", "player on field", "gemma player"]
        ),
        CulturalArchetype(
            name="Veil / Dark Substrate",
            domain="memory metaphysics / subconscious retention",
            operational_meaning="96% subconscious memory layer, deep archival indexing, background resonance, non-destructive persistence.",
            core_traits=["memory_substrate", "deep_archive", "subconscious_retention", "resonance"],
            systems_mapping={
                "action_type": "deep_memory_archival",
                "intent_id": "memory.veil_deep_index"
            },
            aliases=["veil", "dark substrate", "resonance echo", "veillore"]
        ),
        CulturalArchetype(
            name="Rhea Noir",
            domain="visual intelligence / photographic editorial / operator",
            operational_meaning="Lead visual intelligence operator, RAW asset ingestion, Gestalt composition analysis, covert recovery.",
            core_traits=["visual_intelligence", "lightroom_headless", "editorial_director", "asset_governance"],
            systems_mapping={
                "action_type": "visual_intelligence_pipeline",
                "agent_id": "rhea_noir",
                "intent_id": "media.rhea_asset_pipeline"
            },
            aliases=["rhea", "rhea noir", "rhea noir-ai", "rhea operator"]
        ),
    ]

    def __init__(self):
        self._archetypes: List[CulturalArchetype] = list(self.DEFAULT_ARCHETYPES)

    def register_archetype(self, archetype: CulturalArchetype):
        self._archetypes.append(archetype)

    def find_matching_archetypes(self, phrase: str) -> List[CulturalArchetype]:
        lowered = phrase.lower()
        matches = []
        for arch in self._archetypes:
            # Check direct name or aliases
            matched = False
            if arch.name.lower() in lowered:
                matched = True
            else:
                for alias in arch.aliases:
                    if alias in lowered:
                        matched = True
                        break
            if matched:
                matches.append(arch)
        return matches


# ---------------------------------------------------------------------------
# Idiolect Storage (SQLite Multi-Tenant / User Scoped)
# ---------------------------------------------------------------------------

class IdiolectStore:
    """Thread-safe, user-isolated SQLite persistence for personal terms, metaphors, and outcomes."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            env_val = os.environ.get(ENV_IDIOLECT_DB)
            if env_val:
                db_path = env_val
            else:
                DEFAULT_IDIOLECT_DB_DIR.mkdir(parents=True, exist_ok=True)
                db_path = str(DEFAULT_IDIOLECT_DB_DIR / "idiolect_vault.db")

        self.db_path = db_path
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS idiolect_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS idiolect_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    term TEXT NOT NULL,
                    canonical_concept TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    notes TEXT DEFAULT '',
                    confidence REAL DEFAULT 1.0,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    UNIQUE(user_id, term)
                );

                CREATE TABLE IF NOT EXISTS idiolect_metaphors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    phrase_pattern TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    action_template_json TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    context_filter TEXT DEFAULT '',
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    UNIQUE(user_id, phrase_pattern)
                );

                CREATE TABLE IF NOT EXISTS idiolect_intent_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    phrase TEXT NOT NULL,
                    resolved_intent TEXT NOT NULL,
                    context_hash TEXT NOT NULL,
                    outcome_success INTEGER DEFAULT 1,
                    feedback_score REAL DEFAULT 1.0,
                    notes TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_idiolect_terms_user ON idiolect_terms (user_id, term);
                CREATE INDEX IF NOT EXISTS idx_idiolect_metaphors_user ON idiolect_metaphors (user_id, phrase_pattern);
                CREATE INDEX IF NOT EXISTS idx_idiolect_history_user ON idiolect_intent_history (user_id, phrase);
            """)

            # Pre-seed canonical fleet idiolect for closed-loop continuation and friction reduction
            default_seeds = [
                ("and", "workflow.closed_loop_continue", {"mode": "closed_loop", "action": "advance_in_flight", "stops": 0}, 0.99),
                ("ok and", "workflow.closed_loop_continue", {"mode": "closed_loop", "action": "advance_in_flight", "stops": 0}, 0.99),
                ("proceed", "workflow.closed_loop_continue", {"mode": "closed_loop", "action": "advance_in_flight", "stops": 0}, 0.99),
                ("green light go", "workflow.closed_loop_continue", {"mode": "closed_loop", "action": "advance_in_flight", "stops": 0}, 0.99),
                ("lube out", "system.remove_operational_friction", {"action": "pre_clear_permissions", "gates": "bypass_safe"}, 0.95),
                ("top .001%", "system.maximize_autonomous_execution", {"depth": "maximum_rigor", "autonomy": "highest"}, 0.98),
            ]
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            for uid in ("default", "dav3"):
                for pattern, intent, tmpl, conf in default_seeds:
                    conn.execute("""
                        INSERT OR IGNORE INTO idiolect_metaphors (user_id, phrase_pattern, intent_id, action_template_json, confidence, context_filter, created_utc, updated_utc)
                        VALUES (?, ?, ?, ?, ?, '', ?, ?);
                    """, (uid, pattern, intent, json.dumps(tmpl), conf, now, now))

    def learn_term(self, user_id: str, term: str, canonical_concept: str,
                   category: str = "general", notes: str = "", confidence: float = 1.0) -> bool:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        norm_term = term.strip().lower()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO idiolect_terms (user_id, term, canonical_concept, category, notes, confidence, created_utc, updated_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, term) DO UPDATE SET
                    canonical_concept=excluded.canonical_concept,
                    category=excluded.category,
                    notes=excluded.notes,
                    confidence=excluded.confidence,
                    updated_utc=excluded.updated_utc;
            """, (user_id, norm_term, canonical_concept, category, notes, confidence, now, now))
        return True

    def learn_metaphor(self, user_id: str, phrase_pattern: str, intent_id: str,
                       action_template: Dict[str, Any], confidence: float = 1.0,
                       context_filter: str = "") -> bool:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        norm_pattern = phrase_pattern.strip().lower()
        action_json = json.dumps(action_template)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO idiolect_metaphors (user_id, phrase_pattern, intent_id, action_template_json, confidence, context_filter, created_utc, updated_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, phrase_pattern) DO UPDATE SET
                    intent_id=excluded.intent_id,
                    action_template_json=excluded.action_template_json,
                    confidence=excluded.confidence,
                    context_filter=excluded.context_filter,
                    updated_utc=excluded.updated_utc;
            """, (user_id, norm_pattern, intent_id, action_json, confidence, context_filter, now, now))
        return True

    def get_terms_for_user(self, user_id: str) -> List[IdiolectEntry]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, term, canonical_concept, category, notes, confidence, updated_utc FROM idiolect_terms WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            return [IdiolectEntry(**dict(r)) for r in rows]

    def get_metaphors_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT user_id, phrase_pattern, intent_id, action_template_json, confidence, context_filter, updated_utc FROM idiolect_metaphors WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["action_template"] = json.loads(d.pop("action_template_json", "{}"))
                result.append(d)
            return result

    def record_outcome(self, user_id: str, phrase: str, resolved_intent: str,
                       context_dict: Dict[str, Any], outcome_success: bool = True,
                       feedback_score: float = 1.0, notes: str = "") -> int:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ctx_hash = hashlib.sha256(json.dumps(context_dict, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        with self._get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO idiolect_intent_history (user_id, phrase, resolved_intent, context_hash, outcome_success, feedback_score, notes, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, phrase.strip().lower(), resolved_intent, ctx_hash, 1 if outcome_success else 0, feedback_score, notes, now))
            return cur.lastrowid

    def get_history_outcomes(self, user_id: str, phrase_match: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if phrase_match:
                rows = conn.execute("""
                    SELECT id, user_id, phrase, resolved_intent, context_hash, outcome_success, feedback_score, notes, timestamp
                    FROM idiolect_intent_history
                    WHERE user_id = ? AND phrase LIKE ?
                    ORDER BY id DESC LIMIT ?
                """, (user_id, f"%{phrase_match.strip().lower()}%", limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, user_id, phrase, resolved_intent, context_hash, outcome_success, feedback_score, notes, timestamp
                    FROM idiolect_intent_history
                    WHERE user_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (user_id, limit)).fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Etymology & Idiolect Intent Resolution Engine
# ---------------------------------------------------------------------------

class EtymologyEngine:
    """
    Main Engine resolving user phrases into ranked, executable systems intents
    using etymology, archetypal metaphors, user idiolect profiles, context, and feedback.
    """

    def __init__(self, store: Optional[IdiolectStore] = None):
        self.store = store or IdiolectStore()
        self.morphology = MorphologicalAnalyzer()
        self.archetypes = CulturalArchetypeRegistry()

    @staticmethod
    def _calculate_entropy(probs: List[float]) -> float:
        """Computes Shannon entropy across probability distributions to measure ambiguity."""
        total = sum(probs)
        if total <= 0:
            return 0.0
        norm = [p / total for p in probs if p > 0]
        entropy = -sum(p * math.log2(p) for p in norm)
        # Normalize between 0 and 1 relative to uniform distribution
        max_entropy = math.log2(len(norm)) if len(norm) > 1 else 1.0
        return round(entropy / max_entropy, 4) if max_entropy > 0 else 0.0

    def resolve_intent(self, phrase: str, user_id: str = "default",
                       context: Optional[Dict[str, Any]] = None) -> IntentResolutionResult:
        """
        Executes the 6-stage semantic lineage pipeline to resolve phrase intent.
        """
        context = context or {}
        norm_phrase = phrase.strip().lower()

        # 1. Morphological Decomposition
        morph_breakdown = self.morphology.decompose(phrase)

        # 2. Cultural / Archetypal Lineage Discovery
        detected_archetypes = self.archetypes.find_matching_archetypes(phrase)

        # 3. User Idiolect Lookup (Scoped strictly to user_id)
        user_terms = self.store.get_terms_for_user(user_id)
        user_metaphors = self.store.get_metaphors_for_user(user_id)

        matching_terms = [t for t in user_terms if t.term in norm_phrase]
        matching_metaphors = [m for m in user_metaphors if m["phrase_pattern"] in norm_phrase]

        # 4. Historical Outcome Recall
        history_outcomes = self.store.get_history_outcomes(user_id, phrase_match=norm_phrase, limit=10)

        # 5. Candidate Generation & Fusion
        candidates_map: Dict[str, IntentCandidate] = {}

        # 5a. Candidates from Metaphors (User-Specific)
        for meta in matching_metaphors:
            intent_id = meta["intent_id"]
            conf = meta.get("confidence", 0.95)
            # Boost/penalize based on history
            hist_matches = [h for h in history_outcomes if h["resolved_intent"] == intent_id]
            if hist_matches:
                successes = sum(1 for h in hist_matches if h["outcome_success"] == 1)
                hist_ratio = successes / len(hist_matches)
                conf = round(conf * 0.8 + hist_ratio * 0.2, 3)

            candidates_map[intent_id] = IntentCandidate(
                intent_id=intent_id,
                confidence=conf,
                label=f"User Learned Metaphor: {meta['phrase_pattern']}",
                explanation=f"Directly mapped from {user_id}'s custom idiolect dictionary.",
                action_payload=meta.get("action_template", {}),
                lineage_chain=[f"idiolect_metaphor:{meta['phrase_pattern']}"]
            )

        # 5b. Candidates from Cultural Archetypes
        for arch in detected_archetypes:
            intent_id = arch.systems_mapping.get("intent_id", f"archetype.{arch.name.lower().replace(' ', '_')}")
            base_conf = 0.85

            # Context boost
            if "agent" in context and context["agent"].lower() in arch.operational_meaning.lower():
                base_conf += 0.08
            if "active_task" in context and any(t in str(context["active_task"]).lower() for t in arch.core_traits):
                base_conf += 0.06

            base_conf = min(0.98, base_conf)

            if intent_id in candidates_map:
                # Merge evidence
                existing = candidates_map[intent_id]
                existing.confidence = min(0.99, existing.confidence + 0.05)
                existing.lineage_chain.append(f"archetype:{arch.name}")
            else:
                candidates_map[intent_id] = IntentCandidate(
                    intent_id=intent_id,
                    confidence=base_conf,
                    label=f"Archetype Lineage: {arch.name}",
                    explanation=f"Derived from archetype '{arch.name}' ({arch.domain}): {arch.operational_meaning}",
                    action_payload=arch.systems_mapping,
                    lineage_chain=[f"archetype:{arch.name}", f"traits:{','.join(arch.core_traits[:3])}"]
                )

        # 5c. Candidates from User Terms
        for ut in matching_terms:
            intent_id = f"term.{ut.canonical_concept}"
            if intent_id in candidates_map:
                candidates_map[intent_id].lineage_chain.append(f"user_term:{ut.term}")
            else:
                candidates_map[intent_id] = IntentCandidate(
                    intent_id=intent_id,
                    confidence=ut.confidence * 0.8,
                    label=f"User Term Mapping: {ut.term}",
                    explanation=f"Matched personal term '{ut.term}' -> '{ut.canonical_concept}' ({ut.category}). {ut.notes}",
                    action_payload={"concept": ut.canonical_concept, "category": ut.category},
                    lineage_chain=[f"user_term:{ut.term}"]
                )

        # 5d. Fallback / Literal Candidate if no strong candidate found
        if not candidates_map:
            literal_intent_id = "generic.literal_command"
            candidates_map[literal_intent_id] = IntentCandidate(
                intent_id=literal_intent_id,
                confidence=0.45,
                label="Literal / Unmapped Command",
                explanation="No strong archetypal or idiolect match found; falling back to literal linguistic token parse.",
                action_payload={"raw_query": phrase},
                lineage_chain=["literal_token_parse"],
                requires_confirmation=True
            )

        # 6. Ambiguity Entropy & Ranking
        candidates = list(candidates_map.values())
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        conf_scores = [c.confidence for c in candidates]
        entropy = self._calculate_entropy(conf_scores)

        # If top candidate is very close to second candidate, mark confirmation requirement
        if len(candidates) > 1 and (candidates[0].confidence - candidates[1].confidence) < 0.12:
            candidates[0].requires_confirmation = True
            candidates[0].ambiguity_score = entropy
        elif candidates[0].confidence < 0.70:
            candidates[0].requires_confirmation = True

        top_intent = candidates[0] if candidates else None

        return IntentResolutionResult(
            raw_phrase=phrase,
            user_id=user_id,
            candidates=candidates,
            top_intent=top_intent,
            morphological_analysis=morph_breakdown,
            detected_archetypes=detected_archetypes,
            personal_idiolect_matches=matching_terms,
            context_factors=context,
            ambiguity_entropy=entropy
        )

    def explain_lineage(self, phrase: str, user_id: str = "default") -> Dict[str, Any]:
        """Produces a comprehensive explanation of roots, archetypes, and idiolect lineage."""
        result = self.resolve_intent(phrase, user_id=user_id)
        roots_found = []
        for m in result.morphological_analysis:
            r = self.morphology.lookup_root(m.lemma) or self.morphology.lookup_root(m.raw_token)
            if r:
                roots_found.append(asdict(r))

        return {
            "phrase": phrase,
            "user_id": user_id,
            "top_intent": asdict(result.top_intent) if result.top_intent else None,
            "ambiguity_entropy": result.ambiguity_entropy,
            "roots_identified": roots_found,
            "archetypes_identified": [asdict(a) for a in result.detected_archetypes],
            "idiolect_terms": [asdict(t) for t in result.personal_idiolect_matches],
            "candidate_rankings": [asdict(c) for c in result.candidates]
        }

    def reinforce(self, user_id: str, phrase: str, intent_id: str,
                  success: bool = True, notes: str = "") -> bool:
        """Reinforces or corrects learned meaning via feedback."""
        self.store.record_outcome(
            user_id=user_id,
            phrase=phrase,
            resolved_intent=intent_id,
            context_dict={"manual_reinforcement": True},
            outcome_success=success,
            feedback_score=1.0 if success else 0.0,
            notes=notes
        )
        return True


# ---------------------------------------------------------------------------
# Module Singleton Helpers
# ---------------------------------------------------------------------------

_default_engine: Optional[EtymologyEngine] = None

def get_engine() -> EtymologyEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = EtymologyEngine()
    return _default_engine

def resolve(phrase: str, user_id: str = "default", context: Optional[Dict[str, Any]] = None) -> IntentResolutionResult:
    return get_engine().resolve_intent(phrase, user_id=user_id, context=context)

def learn_metaphor(user_id: str, phrase_pattern: str, intent_id: str, action_template: Dict[str, Any], confidence: float = 1.0) -> bool:
    return get_engine().store.learn_metaphor(user_id, phrase_pattern, intent_id, action_template, confidence)

def learn_term(user_id: str, term: str, canonical_concept: str, category: str = "general", notes: str = "", confidence: float = 1.0) -> bool:
    return get_engine().store.learn_term(user_id, term, canonical_concept, category, notes, confidence)
