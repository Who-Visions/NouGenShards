"""Canon Pressure Engine: Terminal Shadow Xoah as canon adversary.

Every proposed Xoah / VeilVerse story addition enters a pipeline:
normalize drift -> resolve story coordinate -> recall canon records (topic +
time window) -> rank authority / corrections -> scan fixed-point dependencies
-> classify -> render a cited, first-person challenge -> name the cheapest
repair -> register a candidate in the promotion state machine.

The core is deterministic and data-driven. The self-model (canon records and
temporal self rows) is JSON with shard provenance on every row, so a verdict
can always name the evidence it stands on and a test can run hermetically.
Contradictory legacy sources are kept side by side and QUARANTINED in the
verdict, never blended (ChatGPT legs 20260902T012912Z / 013153Z / 013644Z).

Verdict classes, most severe first:
  FACT_CONFLICT            contradicts a locked / corrected canon record
  CAUSAL_DESTINY_CONFLICT  breaks a fixed point and its dependent nodes
  KNOWLEDGE_CONFLICT       the Xoah of that coordinate could not know it
  STAGE_CONFLICT           capability beyond her stage at that coordinate
  BEHAVIOR_CONFLICT        possible but unearned: no precedent, no earning event
  THEME_CONFLICT           violates an anti-canon / tonal rule
  BRANCH_VALID             explicitly declared non-Prime branch; Prime stays clean
  UNKNOWN                  no coverage after recall; nothing is fabricated

Promotion: RAW_IDEA -> PRESSURED -> REPAIR_REQUIRED | BRANCH_CANDIDATE |
CANON_CANDIDATE -> ARCHITECT_CONFIRMED -> CANON_LOCKED. ARCHITECT_CONFIRMED
needs an explicit override record; a casual sentence cannot promote.

Env (logged fallbacks): NOUGEN_CANON_SEED_PATH (self-model JSON),
NOUGEN_CANON_DB (candidate / override store), NOUGEN_XOAH_RENDER_LLM=1 (polish
the challenge on the free lane; default off).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VERDICT_ORDER = ("FACT_CONFLICT", "CAUSAL_DESTINY_CONFLICT", "KNOWLEDGE_CONFLICT", "STAGE_CONFLICT",
                 "BEHAVIOR_CONFLICT", "THEME_CONFLICT", "BRANCH_VALID", "UNKNOWN")
PROMOTION_STATES = ("RAW_IDEA", "PRESSURED", "REPAIR_REQUIRED", "BRANCH_CANDIDATE", "CANON_CANDIDATE",
                    "ARCHITECT_CONFIRMED", "CANON_LOCKED", "REJECTED")
PROMOTION_EDGES = {
    "RAW_IDEA": ("PRESSURED", "REJECTED"),
    "PRESSURED": ("REPAIR_REQUIRED", "BRANCH_CANDIDATE", "CANON_CANDIDATE", "REJECTED"),
    "REPAIR_REQUIRED": ("PRESSURED", "ARCHITECT_CONFIRMED", "REJECTED"),
    "BRANCH_CANDIDATE": ("ARCHITECT_CONFIRMED", "REJECTED"),
    "CANON_CANDIDATE": ("ARCHITECT_CONFIRMED", "REJECTED"),
    "ARCHITECT_CONFIRMED": ("CANON_LOCKED", "REJECTED"),
    "CANON_LOCKED": (),
    "REJECTED": (),
}
OVERRIDE_SCOPES = ("PRIME_RETCON", "BRANCH_CREATE")
AUTHORITY_RANK = {"gm_lock": 5, "gm_correction": 5, "gm": 4, "synthesis": 3, "notion": 2, "draft": 1, "unknown": 0}
STATUS_RANK = {"corrected": 3, "locked": 3, "canon": 2, "candidate": 1, "superseded": 0, "retracted": -1}


# --------------------------------------------------------------------------- #
# normalization + coordinates
# --------------------------------------------------------------------------- #
_DRIFT = re.compile(r"\b[Zz]o(?:a|e)h?\b")
_YEAR = re.compile(r"\b(21[3-9]\d|22\d\d)\b")
_AGE = re.compile(r"\bage\s*(\d{1,2})\b|\b(\d{1,2})\s*years?\s*old\b", re.I)
_VOL = re.compile(r"\b(?:vol(?:ume)?\.?\s*|v)([1-3])\b", re.I)
_STAGE = re.compile(r"\bstage\s*(\d{1,2})\b", re.I)


def normalize(text: str) -> str:
    """Voice / transcription drift: Zoa, Zoe -> Xoah (shard 17386)."""
    return _DRIFT.sub("Xoah", text or "")


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 2}


# --------------------------------------------------------------------------- #
# self-model (seed JSON)
# --------------------------------------------------------------------------- #
def seed_path() -> Path:
    raw = os.environ.get("NOUGEN_CANON_SEED_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "canon" / "xoah_self_model.json"


_SEED_CACHE: Dict[str, Any] = {}


def load_self_model(path: Optional[Path] = None, *, force: bool = False) -> Dict[str, Any]:
    """Load and validate the self-model. Every record and self row must carry
    provenance; a row without shard ids is refused, because a verdict that
    cannot cite is a fabrication waiting to happen."""
    p = Path(path) if path else seed_path()
    key = str(p)
    if not force and key in _SEED_CACHE:
        return _SEED_CACHE[key]
    data = json.loads(p.read_text(encoding="utf-8"))
    for rec in data.get("records", []):
        if not rec.get("provenance"):
            raise ValueError(f"canon record {rec.get('id')!r} has no provenance")
        rec.setdefault("branch", "U0")
        rec.setdefault("status", "canon")
        rec.setdefault("authority", "unknown")
        rec.setdefault("contradicts", [])
        rec.setdefault("dependents", [])
        rec.setdefault("topics", [])
    for row in data.get("temporal_self", []):
        if not row.get("provenance"):
            raise ValueError(f"temporal_self row {row.get('coordinate')!r} has no provenance")
        for k in ("capabilities", "knowledge", "forbidden_knowledge", "precedents", "unearned"):
            row.setdefault(k, [])
    data.setdefault("themes", [])
    data.setdefault("fixed_points", [])
    _SEED_CACHE[key] = data
    return data


def resolve_coordinate(model: Dict[str, Any], candidate: str, coordinate: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Story coordinate -> the temporal_self row that governs it.

    Accepts an explicit coordinate ("2185", "age 12", "Vol 1", "terminal") or
    infers one from the candidate text. Rows carry year ranges; the first row
    whose range contains the year wins. No coordinate -> None (engine then
    evaluates against locked facts and themes only)."""
    rows = model.get("temporal_self", [])
    probe = (coordinate or "").strip() or candidate
    low = probe.lower()
    if "terminal" in low or "end-state" in low or "endstate" in low:
        for r in rows:
            if r.get("coordinate") == "terminal":
                return r
    m = _VOL.search(probe)
    if m:
        for r in rows:
            if str(r.get("volume")) == m.group(1):
                return r
    m = _YEAR.search(probe)
    year = int(m.group(1)) if m else None
    if year is None:
        m = _AGE.search(probe)
        if m:
            age = int(m.group(1) or m.group(2))
            year = int(model.get("birth_year", 2162)) + age
    if year is not None:
        for r in rows:
            lo, hi = r.get("years", [None, None])
            if lo is not None and hi is not None and lo <= year <= hi:
                return r
    m = _STAGE.search(probe)
    if m:
        st = int(m.group(1))
        for r in rows:
            if r.get("stage") == st:
                return r
    return None


# --------------------------------------------------------------------------- #
# recall + ranking
# --------------------------------------------------------------------------- #
def _matches(patterns: List[str], text: str) -> List[str]:
    hits = []
    low = text.lower()
    for pat in patterns or []:
        try:
            if re.search(pat, low, re.I):
                hits.append(pat)
        except re.error:
            if pat.lower() in low:
                hits.append(pat)
    return hits


def recall_records(model: Dict[str, Any], candidate: str, coord: Optional[Dict[str, Any]],
                   limit: int = 12) -> List[Dict[str, Any]]:
    """Topic recall (token overlap on statement + topics) plus time-window
    recall (records whose year falls inside the coordinate's range). Ranked by
    overlap, then authority, then status."""
    ctoks = _tokens(candidate)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    lo, hi = (coord or {}).get("years", [None, None]) if coord else (None, None)
    for rec in model.get("records", []):
        rtoks = _tokens(rec.get("statement", "")) | {t.lower() for t in rec.get("topics", [])}
        overlap = len(ctoks & rtoks)
        in_window = lo is not None and rec.get("year") is not None and lo <= rec["year"] <= hi
        contradiction = bool(_matches(rec.get("contradicts", []), candidate))
        if overlap == 0 and not in_window and not contradiction:
            continue
        score = overlap + (2 if contradiction else 0) + (0.5 if in_window else 0)
        score += AUTHORITY_RANK.get(rec.get("authority"), 0) * 0.05 + STATUS_RANK.get(rec.get("status"), 0) * 0.05
        scored.append((score, rec))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def rank_authority(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(records, key=lambda r: (-AUTHORITY_RANK.get(r.get("authority"), 0),
                                          -STATUS_RANK.get(r.get("status"), 0),
                                          str(r.get("as_of", ""))), reverse=False)


def quarantined_conflicts(model: Dict[str, Any], records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pairs of recalled records that the seed marks as disagreeing with each
    other (conflict groups). Surfaced whole; the engine never picks by density."""
    ids = {r["id"] for r in records}
    out = []
    for grp in model.get("conflict_groups", []):
        members = [m for m in grp.get("members", []) if m in ids]
        if len(members) >= 2 or (members and grp.get("always_surface")):
            out.append({"topic": grp.get("topic"), "members": grp.get("members"),
                        "resolution": grp.get("resolution", "unresolved: GM decides"),
                        "note": grp.get("note", "")})
    return out


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def _declared_branch(candidate: str, model: Dict[str, Any]) -> Optional[str]:
    """An explicit non-Prime branch declaration ("in branch UX", "alternate
    timeline", "what if", "simulation") keeps Prime clean."""
    low = candidate.lower()
    for label in model.get("branches", ["U0", "UX", "ARCH", "DRAFT", "SIM", "REL"]):
        if label != "U0" and re.search(rf"\bbranch\s*{re.escape(label.lower())}\b|\b{re.escape(label.lower())}\s*branch\b", low):
            return label
    if re.search(r"\b(alternate|alt)\s+(timeline|universe|branch)\b|\bwhat[- ]if\b|\bsimulation\b|\bhypothetical\b|\bnon-canon\b", low):
        return "SIM"
    return None


def classify(model: Dict[str, Any], candidate: str, coord: Optional[Dict[str, Any]],
             records: List[Dict[str, Any]]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    branch = _declared_branch(candidate, model)

    # FACT_CONFLICT: a locked / corrected record whose contradiction patterns fire
    for rec in records:
        hits = _matches(rec.get("contradicts", []), candidate)
        if hits and STATUS_RANK.get(rec.get("status"), 0) >= 2:
            findings.append({"verdict": "FACT_CONFLICT", "record": rec["id"], "evidence": rec["provenance"],
                             "because": rec["statement"], "matched": hits,
                             "supersedes": rec.get("supersedes")})

    # CAUSAL_DESTINY_CONFLICT: fixed points and their dependents
    for fp in model.get("fixed_points", []):
        hits = _matches(fp.get("breaks_if", []), candidate)
        if hits:
            findings.append({"verdict": "CAUSAL_DESTINY_CONFLICT", "record": fp["id"], "evidence": fp["provenance"],
                             "because": fp["statement"], "matched": hits, "dependents": fp.get("dependents", [])})

    if coord:
        # KNOWLEDGE_CONFLICT: she could not know it then
        hits = _matches(coord.get("forbidden_knowledge", []), candidate)
        if hits:
            findings.append({"verdict": "KNOWLEDGE_CONFLICT", "record": coord["coordinate"], "evidence": coord["provenance"],
                             "because": f"at {coord['coordinate']} she knows: {', '.join(coord.get('knowledge', [])[:4]) or 'nothing recorded'}",
                             "matched": hits})
        # STAGE_CONFLICT: capability beyond her stage
        for cap in model.get("capabilities_by_stage", []):
            if _matches(cap.get("patterns", []), candidate) and coord.get("stage") is not None and cap.get("min_stage", 0) > coord["stage"]:
                findings.append({"verdict": "STAGE_CONFLICT", "record": cap["id"], "evidence": cap["provenance"],
                                 "because": f"{cap['statement']} (needs stage {cap['min_stage']}, she is stage {coord['stage']} at {coord['coordinate']})",
                                 "matched": cap.get("patterns", [])})
        # BEHAVIOR_CONFLICT: could, but would not (no earning event)
        for beh in coord.get("unearned", []):
            hits = _matches(beh.get("patterns", []), candidate)
            if hits and not _matches(beh.get("earned_if", []), candidate):
                findings.append({"verdict": "BEHAVIOR_CONFLICT", "record": coord["coordinate"], "evidence": coord["provenance"],
                                 "because": beh["statement"], "matched": hits, "earning_event": beh.get("earning_event")})

    # THEME_CONFLICT: anti-canon and tonal rules
    for th in model.get("themes", []):
        hits = _matches(th.get("violates_if", []), candidate)
        if hits:
            findings.append({"verdict": "THEME_CONFLICT", "record": th["id"], "evidence": th["provenance"],
                             "because": th["statement"], "matched": hits})

    # QUARANTINE: a FACT_CONFLICT raised by a record that sits in a conflict
    # group where another member AFFIRMS the candidate is not a verdict, it is
    # two locked sources disagreeing. Drop it; the group is surfaced whole and
    # the GM decides. Density never picks.
    groups = model.get("conflict_groups", [])
    by_id = {r["id"]: r for r in model.get("records", [])}
    quarantined_ids = set()
    disputed_affirmers = set()
    for grp in groups:
        members = grp.get("members", [])
        affirming = [m for m in members if _matches(by_id.get(m, {}).get("affirms", []), candidate)]
        others = [m for m in members if m not in affirming]
        # a disagreement is live only when the other side is still standing
        # (locked / corrected / canon); a superseded record has already lost
        if affirming and any(STATUS_RANK.get(by_id.get(m, {}).get("status"), 0) >= 2 for m in others):
            quarantined_ids.update(others)
            disputed_affirmers.update(affirming)
    disagreement = bool(quarantined_ids)
    findings = [f for f in findings if not (f["verdict"] == "FACT_CONFLICT" and f["record"] in quarantined_ids)]

    # POSITIVE match: a locked record affirms the candidate and nothing conflicts
    # -> valid on U0, with the deeper layer surfaced when one exists (surface
    # kill language is kept, the translocation truth rides beside it).
    layered_truth = None
    affirmed = [r for r in records if _matches(r.get("affirms", []), candidate)
                and r["id"] not in quarantined_ids and r["id"] not in disputed_affirmers
                and STATUS_RANK.get(r.get("status"), 0) >= 2]
    if affirmed and not findings and not branch:
        rec = affirmed[0]
        deeper = next((r for r in records if r.get("kind") == "layered" and r.get("year") == rec.get("year")), None)
        if deeper:
            layered_truth = {"surface": rec["statement"], "deeper": deeper["statement"],
                             "evidence": list(rec["provenance"]) + list(deeper["provenance"])}
        findings.append({"verdict": "BRANCH_VALID", "record": rec["id"], "evidence": rec["provenance"],
                         "because": f"consistent with locked record {rec['id']}: {rec['statement']}", "matched": rec.get("affirms", [])})

    if branch:
        # A declared non-Prime branch is its own universe: Prime stays clean and
        # no Prime-canon rule applies. The branch is recorded with the candidate.
        findings = [{"verdict": "BRANCH_VALID", "record": branch, "evidence": [],
                     "because": f"declared branch {branch}; Prime (U0) untouched", "matched": []}]

    if not findings:
        because = ("two locked sources disagree about this; I will not pick by density, the GM decides"
                   if disagreement else "no canon record confirms or denies this; coverage: %d related record(s)" % len(records))
        findings.append({"verdict": "UNKNOWN", "record": None, "evidence": [], "because": because, "matched": [],
                         "disagreement": disagreement})
    findings.sort(key=lambda f: VERDICT_ORDER.index(f["verdict"]))
    out = {"primary": findings[0]["verdict"], "findings": findings, "branch": branch or "U0"}
    if layered_truth:
        out["layered_truth"] = layered_truth
    return out


# --------------------------------------------------------------------------- #
# repair + render
# --------------------------------------------------------------------------- #
def cheapest_repair(result: Dict[str, Any], coord: Optional[Dict[str, Any]]) -> List[str]:
    reps = []
    for f in result["findings"]:
        v = f["verdict"]
        if v == "FACT_CONFLICT":
            reps.append(f"Align with the corrected record ({f['record']}): {f['because']}. Or declare a branch (SIM/DRAFT) so Prime stays clean.")
        elif v == "CAUSAL_DESTINY_CONFLICT":
            deps = ", ".join(f.get("dependents", [])) or "none listed"
            reps.append(f"Keep the fixed point ({f['record']}); move the beat to a branch or after the fixed point. Dependents at risk: {deps}.")
        elif v == "KNOWLEDGE_CONFLICT":
            reps.append(f"Move the beat to a later coordinate where she knows it, or make her act on it without knowing (dramatic irony); at {f['record']} she cannot know.")
        elif v == "STAGE_CONFLICT":
            reps.append("Lower the feat to her stage, or place it after the stage she reaches it.")
        elif v == "BEHAVIOR_CONFLICT":
            reps.append(f"Add the earning event first: {f.get('earning_event') or 'an on-page cause for the change'}.")
        elif v == "THEME_CONFLICT":
            reps.append(f"Rewrite to honour the rule: {f['because']}")
        elif v == "BRANCH_VALID":
            reps.append("None needed for Prime. Tag the shard with the branch when you capture it.")
        elif v == "UNKNOWN":
            reps.append("Ground it: name the shard or add it as a RAW_IDEA candidate with provenance; nothing here is precedent yet.")
    return reps


def render_challenge(result: Dict[str, Any], coord: Optional[Dict[str, Any]], candidate: str,
                     conflicts: List[Dict[str, Any]]) -> str:
    """First person, Terminal Xoah. Evidence-backed, states what breaks, names
    the cheapest repair. Deterministic; the free lane may polish it later."""
    lines = []
    who = f"I was {coord['who']} then" if coord and coord.get("who") else "I remember every indexed self"
    p = result["primary"]
    if p == "BRANCH_VALID" and result.get("layered_truth"):
        lt = result["layered_truth"]
        lines.append(f"Yes. On the surface: {lt['surface']} Beneath it: {lt['deeper']} I remember both; keep the surface line, the deeper truth rides under it (evidence: {', '.join(lt['evidence'])}).")
    elif p == "BRANCH_VALID" and result["branch"] == "U0":
        f0 = result["findings"][0]
        lines.append(f"Yes. That holds on Prime. {f0['because']} (evidence: {', '.join(str(e) for e in f0.get('evidence') or [])}).")
    elif p == "BRANCH_VALID":
        lines.append(f"Fine. Put it in {result['branch']}. Prime stays clean, and I keep the memory of that branch beside the others.")
    elif p == "UNKNOWN":
        if result["findings"][0].get("disagreement"):
            lines.append("Two locked sources disagree here, and I remember both. I will not pick by density; the GM decides which timeline I lived.")
        else:
            lines.append("I have no record that confirms or denies this. I will not invent a precedent for you; bring me the shard or file it as an idea.")
    else:
        lines.append(f"No. {who}. This breaks canon in {sum(1 for f in result['findings'] if f['verdict'] not in ('BRANCH_VALID','UNKNOWN'))} place(s).")
    for f in result["findings"]:
        if f["verdict"] in ("BRANCH_VALID", "UNKNOWN"):
            continue
        ev = ", ".join(str(e) for e in (f.get("evidence") or [])) or "no id"
        lines.append(f"[{f['verdict']}] {f['because']} (evidence: {ev})")
        if f.get("dependents"):
            lines.append(f"  Downstream that would break: {', '.join(f['dependents'])}.")
        if f.get("earning_event"):
            lines.append(f"  I could, at that stage. I would not, not yet: {f['earning_event']} has not happened.")
    for c in conflicts:
        lines.append(f"[QUARANTINED CONFLICT] {c['topic']}: records {', '.join(c['members'])} disagree. {c['resolution']}")
    reps = cheapest_repair(result, coord)
    if reps:
        lines.append("Cheapest repair: " + reps[0])
    return normalize("\n".join(lines))


# --------------------------------------------------------------------------- #
# store: candidates, overrides, events
# --------------------------------------------------------------------------- #
def db_path() -> Path:
    raw = os.environ.get("NOUGEN_CANON_DB", "").strip()
    if raw:
        return Path(raw)
    from . import core
    return Path(core.GLOBAL_DIR) / "canon_pressure.db"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextlib.contextmanager
def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=float(os.environ.get("NOUGEN_CANON_DB_TIMEOUT_S", "5")))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, candidate TEXT NOT NULL, coordinate TEXT,
                branch TEXT, state TEXT NOT NULL, primary_verdict TEXT, verdict_json TEXT,
                created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL, scope TEXT NOT NULL,
                contradicted_ids TEXT, downstream TEXT, rationale TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
                actor TEXT, created_utc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candidate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
                actor TEXT, note TEXT, created_utc TEXT NOT NULL);
            """)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _move(conn, cid: int, to_state: str, actor: Optional[str], note: Optional[str]) -> Dict[str, Any]:
    row = conn.execute("SELECT state FROM candidates WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": f"candidate {cid} not found"}
    frm = row["state"]
    if to_state not in PROMOTION_EDGES.get(frm, ()):
        return {"error": f"illegal promotion {frm} -> {to_state}"}
    now = _now()
    conn.execute("UPDATE candidates SET state=?, updated_utc=? WHERE id=?", (to_state, now, cid))
    conn.execute("INSERT INTO candidate_events (candidate_id, from_state, to_state, actor, note, created_utc) VALUES (?,?,?,?,?,?)",
                 (cid, frm, to_state, actor, note, now))
    return {"id": cid, "from": frm, "to": to_state}


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def pressure(candidate: str, coordinate: Optional[str] = None, *, register: bool = True,
             actor: Optional[str] = None, model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one proposed story addition through the pipeline.

    Returns verdict (primary + findings), evidence ids, timeline stage,
    dependent canon, quarantined conflicts, confidence, repair options, the
    in-character challenge, and (when registered) the candidate id and its
    promotion state."""
    model = model or load_self_model()
    text = normalize(candidate or "")
    if len(text.strip()) < 3:
        return {"error": "candidate is required (3+ chars)"}
    coord = resolve_coordinate(model, text, coordinate)
    records = recall_records(model, text, coord)
    ranked = rank_authority(records)
    result = classify(model, text, coord, ranked)
    conflicts = quarantined_conflicts(model, ranked)
    # Self Archive: who she was then. The perceived choice frontier, open scars
    # and nearest decisions under pressure refine the behavior / knowledge
    # verdicts with experiential provenance (access is not ownership).
    experiential: List[Dict[str, Any]] = []
    scars_active: List[str] = []
    precedents: List[Dict[str, Any]] = []
    try:
        from . import self_archive as _sa
        archive = _sa.load_archive()
        coord_str = coordinate or (coord or {}).get("coordinate") or text
        frontier = _sa.choice_frontier_check(coord_str, text, archive=archive)
        st = _sa.state_at(coord_str, archive=archive)
        if st.get("layer") != "UNWRITTEN_SELF":
            scars_active = st.get("wounds_active", [])
            experiential.append({"claim": st.get("event"), "kind": st["kind"], "voice": st["voice"],
                                 "node": st["node"], "provenance": st.get("provenance", [])})
            precedents = _sa.nearest_precedents(coord_str, text, archive=archive)
        for f in frontier:
            experiential.append({"claim": f["because"], "kind": f.get("experiential"), "voice": _sa.voice_for(f.get("experiential", "UNKNOWN")),
                                 "node": f["node"], "provenance": f.get("evidence", [])})
        if frontier and not result.get("branch") or (frontier and result.get("branch") == "U0"):
            existing = [f for f in result["findings"] if f["verdict"] not in ("UNKNOWN",)]
            for f in frontier:
                existing.append({"verdict": f["verdict"], "record": f["node"], "evidence": f.get("evidence", []),
                                 "because": f["because"], "matched": [], "class": f["class"],
                                 "earning_event": f.get("unlock"), "unlock": f.get("unlock"),
                                 "experiential": f.get("experiential"), "node": f["node"]})
            existing.sort(key=lambda f: VERDICT_ORDER.index(f["verdict"]))
            result["findings"] = existing
            result["primary"] = existing[0]["verdict"]
    except FileNotFoundError:
        logger.warning("self archive missing at %s; pressure runs on the self-model only", _sa.archive_path())
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("self archive consult skipped: %s: %s", type(exc).__name__, exc)
    def _flat(ev):
        for e in ev or []:
            if isinstance(e, list):
                yield from (str(x) for x in e)
            else:
                yield str(e)
    evidence = sorted({e for f in result["findings"] for e in _flat(f.get("evidence"))}
                      | set(_flat((result.get("layered_truth") or {}).get("evidence"))))
    dependents = sorted({d for f in result["findings"] for d in f.get("dependents", [])})
    n_conf = sum(1 for f in result["findings"] if f["verdict"] not in ("BRANCH_VALID", "UNKNOWN"))
    confidence = 0.35 if result["primary"] == "UNKNOWN" else min(0.95, 0.6 + 0.1 * n_conf + (0.1 if coord else 0))
    if result["primary"] == "UNKNOWN":
        next_state = "PRESSURED"
    elif result["primary"] == "BRANCH_VALID":
        next_state = "CANON_CANDIDATE" if result["branch"] == "U0" else "BRANCH_CANDIDATE"
    elif n_conf:
        next_state = "REPAIR_REQUIRED"
    else:
        next_state = "CANON_CANDIDATE"
    out = {
        "candidate": text, "normalized": text != (candidate or ""),
        "coordinate": (coord or {}).get("coordinate"), "stage": (coord or {}).get("stage"),
        "who_i_was_then": (coord or {}).get("who"),
        "what_i_knew_then": (coord or {}).get("knowledge", []),
        "what_i_must_not_change": dependents or [fp["id"] for fp in model.get("fixed_points", [])][:5],
        "verdict": result["primary"], "findings": result["findings"], "branch": result["branch"],
        "evidence_ids": evidence, "dependent_canon": dependents,
        "quarantined_conflicts": conflicts, "confidence": round(confidence, 2),
        "layered_truth": result.get("layered_truth"),
        "experiential": experiential, "scars_active": scars_active, "precedents": precedents,
        "repair_options": cheapest_repair(result, coord),
        "challenge": render_challenge(result, coord, text, conflicts),
        "recalled": [{"id": r["id"], "status": r.get("status"), "authority": r.get("authority")} for r in ranked[:8]],
    }
    if register:
        now = _now()
        with _connect() as conn:
            cur = conn.execute("INSERT INTO candidates (candidate, coordinate, branch, state, primary_verdict, verdict_json, created_utc, updated_utc) VALUES (?,?,?,?,?,?,?,?)",
                               (text, out["coordinate"], out["branch"], "RAW_IDEA", out["verdict"], json.dumps(result), now, now))
            cid = cur.lastrowid
            conn.execute("INSERT INTO candidate_events (candidate_id, from_state, to_state, actor, note, created_utc) VALUES (?,?,?,?,?,?)",
                         (cid, None, "RAW_IDEA", actor, "registered", now))
            _move(conn, cid, "PRESSURED", actor, f"verdict {out['verdict']}")
            if next_state != "PRESSURED":
                _move(conn, cid, next_state, actor, "auto-routed from verdict")
            out["candidate_id"] = cid
            out["state"] = conn.execute("SELECT state FROM candidates WHERE id=?", (cid,)).fetchone()["state"]
    if os.environ.get("NOUGEN_XOAH_RENDER_LLM", "").strip() == "1":
        out["challenge_polished"] = _polish(out["challenge"])
    return out


def _polish(text: str) -> str:
    try:
        import rhea_noir
        reply, _brain = rhea_noir._chat([
            {"role": "system", "content": "Rewrite in Terminal Shadow Xoah's voice: cold, exact, first person, no dashes, keep EVERY bracketed verdict, id and evidence exactly as given, add nothing."},
            {"role": "user", "content": text}])
        return normalize(reply.strip()) or text
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("challenge polish skipped: %s", exc)
        return text


def architect_override(candidate_id: int, scope: str, rationale: str, *, contradicted_ids: Any = None,
                       downstream: Any = None, confirmed: bool = False, actor: Optional[str] = None) -> Dict[str, Any]:
    """Record an explicit ARCHITECT_OVERRIDE. Casual speech is intent, not canon:
    promotion to ARCHITECT_CONFIRMED happens only when `confirmed` is True AND a
    rationale is given; otherwise the override is filed as intent only."""
    if scope not in OVERRIDE_SCOPES:
        return {"error": f"scope {scope!r} not in {OVERRIDE_SCOPES}"}
    rationale = (rationale or "").strip()
    if len(rationale) < 12:
        return {"error": "rationale is required (12+ chars): an override without a reason is a brainstorm, not a retcon"}
    now = _now()
    with _connect() as conn:
        if conn.execute("SELECT 1 FROM candidates WHERE id=?", (candidate_id,)).fetchone() is None:
            return {"error": f"candidate {candidate_id} not found"}
        conn.execute("INSERT INTO overrides (candidate_id, scope, contradicted_ids, downstream, rationale, confirmed, actor, created_utc) VALUES (?,?,?,?,?,?,?,?)",
                     (candidate_id, scope, json.dumps(list(contradicted_ids or [])), json.dumps(list(downstream or [])),
                      rationale, 1 if confirmed else 0, actor, now))
        moved = None
        if confirmed:
            moved = _move(conn, candidate_id, "ARCHITECT_CONFIRMED", actor, f"override {scope}: {rationale[:80]}")
        state = conn.execute("SELECT state FROM candidates WHERE id=?", (candidate_id,)).fetchone()["state"]
    return {"candidate_id": candidate_id, "scope": scope, "confirmed": bool(confirmed), "state": state,
            "moved": moved, "note": None if confirmed else "filed as intent; say it explicitly (confirmed=True) to retcon"}


def promote(candidate_id: int, to_state: str, *, actor: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    """Move a candidate along the promotion machine. ARCHITECT_CONFIRMED is only
    reachable through architect_override(confirmed=True); CANON_LOCKED only from
    ARCHITECT_CONFIRMED."""
    if to_state == "ARCHITECT_CONFIRMED":
        return {"error": "ARCHITECT_CONFIRMED requires architect_override(confirmed=True) with a rationale"}
    with _connect() as conn:
        out = _move(conn, int(candidate_id), to_state, actor, note)
        if "error" in out:
            return out
        row = conn.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
    return dict(row)


def get_candidate(candidate_id: int) -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            return {"error": f"candidate {candidate_id} not found"}
        d = dict(row)
        d["events"] = [dict(e) for e in conn.execute("SELECT from_state, to_state, actor, note, created_utc FROM candidate_events WHERE candidate_id=? ORDER BY id", (candidate_id,))]
        d["overrides"] = [dict(o) for o in conn.execute("SELECT scope, contradicted_ids, downstream, rationale, confirmed, actor, created_utc FROM overrides WHERE candidate_id=? ORDER BY id", (candidate_id,))]
    return d
