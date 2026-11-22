"""One authoritative destiny store for the fleet, reached over the shard gateway.

Why: every node's CLI wrote to its own ``destinies.db`` while the fleet connector
read whichever node answered behind the shard gateway, so destiny #6 on phoebus
and destiny #6 in the fleet were different records and other lanes never saw
phoebus's destinies (issue #1085).

Shape (the DNS primary / git origin pattern): one store is authoritative; every
other node writes through to it and reads from it. When ``NOUGEN_DESTINY_AUTHORITY``
names the gateway's MCP URL (it ends in ``/mcp/``), the CLI's
destiny commands go there through the gateway's MCP tools. When it is unset,
nothing changes: the local store is used as before.

Offline: a write that cannot reach the authority is NOT applied locally (that
would fork the store again). It is appended to an outbox file and the command
says so; ``flush_outbox()`` replays it later. Creates carry an idempotency key
(normalized title) and are skipped on replay when a destiny with that title
already exists, so a replay never makes a duplicate.

Auth: ``Authorization: Bearer`` with the Keymaker key named by
``NOUGEN_DESTINY_AUTHORITY_KEY`` (default ``FLEET_KEY_OUTPOST``). The key is
never printed or stored in the outbox.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ENV_URL = "NOUGEN_DESTINY_AUTHORITY"
ENV_KEY = "NOUGEN_DESTINY_AUTHORITY_KEY"
DEFAULT_KEY_NAME = "FLEET_KEY_OUTPOST"


def authority_url() -> Optional[str]:
    url = os.environ.get(ENV_URL, "").strip()
    return url or None


def outbox_path() -> Path:
    raw = os.environ.get("NOUGEN_DESTINY_OUTBOX", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".nougen" / "state" / "destiny_outbox.jsonl"


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def clean_title(title: str) -> str:
    """Title as stored: whitespace collapsed, case kept."""
    return " ".join((title or "").split())


@contextlib.contextmanager
def _outbox_lock():
    """Exclusive lock shared by queue() and flush_outbox(), on macOS, Linux and Windows nodes.
    Held for the whole flush, so a write queued meanwhile waits and is never overwritten."""
    path = outbox_path().with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            while True:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.2)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _key() -> str:
    name = os.environ.get(ENV_KEY, "").strip() or DEFAULT_KEY_NAME
    env_val = os.environ.get(name, "").strip()
    if env_val:
        return env_val
    try:
        from . import keymaker
        keymaker.find_legacy_stores = lambda *a, **k: []  # the home-folder scan can hang
        return (keymaker.get_secret(name) or "").strip()
    except Exception:  # pylint: disable=broad-except
        return ""


class AuthorityUnreachable(RuntimeError):
    """The authority could not be reached (network, auth, server). Writes go to the outbox."""


class RemoteDestiny:
    """Same call surface as ``nougen_shards.destiny`` for the CLI, backed by the gateway."""

    def __init__(self, url: str, transport: Optional[Callable[[dict], dict]] = None,
                 timeout: float = 30.0):
        self.url = url
        self.timeout = timeout
        self._transport = transport or self._http
        self._ids = 0

    # ------------------------------------------------------------------ transport
    def _http(self, body: dict) -> dict:
        key = _key()
        if not key:
            raise AuthorityUnreachable("no gateway key in the Keymaker")
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        req.add_header("Authorization", "Bearer " + key)
        req.add_header("User-Agent", "nougen-destiny/1.0")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                ctype = resp.headers.get("Content-Type") or ""
        except urllib.error.HTTPError as exc:
            raise AuthorityUnreachable(f"gateway HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AuthorityUnreachable(f"gateway unreachable: {type(exc).__name__}") from exc
        if "event-stream" in ctype:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            raise AuthorityUnreachable("gateway sent an empty event stream")
        return json.loads(raw)

    def call(self, tool: str, arguments: dict) -> Dict[str, Any]:
        self._ids += 1
        reply = self._transport({"jsonrpc": "2.0", "id": self._ids, "method": "tools/call",
                                 "params": {"name": tool, "arguments": arguments}})
        if "error" in reply:
            err = reply["error"]
            return {"error": err.get("message", str(err)) if isinstance(err, dict) else str(err)}
        result = reply.get("result") or {}
        if result.get("isError"):
            text = "".join(c.get("text", "") for c in result.get("content", []))
            return {"error": text or f"{tool} failed at the authority"}
        if "structuredContent" in result and isinstance(result["structuredContent"], dict):
            sc = result["structuredContent"]
            return sc.get("result", sc) if set(sc) == {"result"} else sc
        text = "".join(c.get("text", "") for c in result.get("content", []))
        try:
            return json.loads(text)
        except ValueError:
            return {"error": f"{tool}: unreadable reply from the authority"}

    # ------------------------------------------------------------------ writes
    def _write(self, tool: str, arguments: dict, idem: Optional[str] = None) -> Dict[str, Any]:
        try:
            return self.call(tool, arguments)
        except AuthorityUnreachable as exc:
            queue(tool, arguments, idem)
            return {"error": f"authority unreachable ({exc}); queued in {outbox_path()}, not applied locally",
                    "queued": True}

    def create_destiny(self, title: str, goal: str, *, branch=None, trigger=None,
                       required_events=None, forbidden_outcomes=None, acceptable_variance=None,
                       verification=None, status="dormant", actor=None, **_unused) -> Dict[str, Any]:
        title = clean_title(title)
        existing = self._find_by_title(title)
        if existing:
            return {"error": f"a destiny with this title already exists at the authority: #{existing['id']}",
                    "existing_id": existing["id"]}
        args = {"title": title, "goal": goal, "status": status}
        for k, v in (("branch", branch), ("trigger", trigger), ("required", _flat(required_events)),
                     ("forbidden", _flat(forbidden_outcomes)), ("variance", acceptable_variance),
                     ("verification", verification), ("actor", actor)):
            if v:
                args[k] = v
        return self._write("create_destiny", args, idem="create:" + norm_title(title))

    def update_status(self, destiny_id: int, to_status: str, *, actor=None, evidence=None) -> Dict[str, Any]:
        args = {"destiny_id": int(destiny_id), "status": to_status}
        if actor:
            args["actor"] = actor
        if evidence:
            args["evidence"] = evidence
        return self._write("update_destiny", args)

    def link(self, destiny_id: int, kind: str, ref: str, role: str = "evidence", note=None) -> Dict[str, Any]:
        args = {"destiny_id": int(destiny_id), "kind": kind, "ref": ref, "role": role}
        if note:
            args["note"] = note
        return self._write("link_destiny", args)

    # ------------------------------------------------------------------ reads
    def get_destiny(self, destiny_id: int) -> Dict[str, Any]:
        return self.call("get_destiny", {"destiny_id": int(destiny_id)})

    def search_destinies(self, query: str, *, limit: int = 20, include_finished: bool = True) -> Dict[str, Any]:
        return self.call("search_destinies", {"query": query or "", "limit": limit,
                                              "include_finished": include_finished})

    def unfinished_destinies(self, *, status=None, trigger=None, branch=None, limit: int = 20) -> Dict[str, Any]:
        args = {"limit": limit}
        for k, v in (("status", status), ("trigger", trigger), ("branch", branch)):
            if v:
                args[k] = v
        return self.call("unfinished_destinies", args)

    def evolve_report(self, **_kw) -> Dict[str, Any]:
        return {"error": "evolve report is local-only; unset NOUGEN_DESTINY_AUTHORITY to run it"}

    def _find_by_title(self, title: str) -> Optional[dict]:
        """An existing destiny whose title matches after whitespace and case are normalized.
        The authority's search is a literal substring match, so a stored title with odd
        internal spacing is only found by its own spelling or by a single word of it: the
        collapsed title, the raw title and the longest word are all tried."""
        want = norm_title(title)
        words = sorted(set(clean_title(title).split()), key=len, reverse=True)
        queries = []
        for q in (clean_title(title), (title or "").strip(), words[0] if words else ""):
            if q and q not in queries:
                queries.append(q)
        for q in queries:
            try:
                found = self.search_destinies(q, limit=200, include_finished=True)
            except AuthorityUnreachable:
                return None
            for d in (found or {}).get("destinies", []) or []:
                if norm_title(d.get("title", "")) == want:
                    return d
        return None


def _flat(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ";".join(str(v) for v in value if str(v).strip()) or None
    return str(value)


def queue(tool: str, arguments: dict, idem: Optional[str] = None) -> None:
    path = outbox_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"queued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tool": tool,
           "arguments": arguments, "idem": idem}
    with _outbox_lock():
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


def flush_outbox(remote: RemoteDestiny) -> Dict[str, Any]:
    """Replay queued writes in order. Stops at the first unreachable error and keeps the rest.
    Holds the outbox lock throughout, so nothing queued during the flush is lost."""
    with _outbox_lock():
        return _flush_locked(remote)


def _flush_locked(remote: RemoteDestiny) -> Dict[str, Any]:
    path = outbox_path()
    if not path.exists():
        return {"sent": 0, "skipped": 0, "left": 0}
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    sent = skipped = 0
    remaining: List[str] = []
    for i, line in enumerate(lines):
        rec = json.loads(line)
        try:
            if rec.get("idem", "") and str(rec["idem"]).startswith("create:") \
                    and remote._find_by_title(rec["arguments"].get("title", "")):
                skipped += 1
                continue
            res = remote.call(rec["tool"], rec["arguments"])
            if "error" in res:
                rec["last_error"] = res["error"]
                remaining.append(json.dumps(rec))
            else:
                sent += 1
        except AuthorityUnreachable:
            remaining.extend(lines[i:])
            break
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(r + "\n" for r in remaining), encoding="utf-8")
    tmp.replace(path)
    return {"sent": sent, "skipped": skipped, "left": len(remaining)}


def backend():
    """The store the CLI should use: the authority when configured, else the local module."""
    url = authority_url()
    if url:
        return RemoteDestiny(url)
    from . import destiny
    return destiny
