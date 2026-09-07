"""Shadow Queen Throne Governance: observation vs intervention gating.

Stationary Omnipotence Principle: Xoah can be functionally everywhere while
personally unable to leave the Throne; presence everywhere does not mean
permission everywhere. Broad awareness is cheap; intervention is costly and
constrained. The engine prefers the smallest lawful touch that preserves the
greatest amount of lived truth, and it NEVER applies a retcon to Prime: it
evaluates, records and, when confirmation is needed, says so.

Composed from the three engines that already exist:
  canon_pressure   verdicts, fixed points, dependents, quarantined conflicts
  self_archive     formative events (undo_patterns), wounds, conservation
  destiny          unfinished destinies + links (destiny dependencies)

Modes, escalating cost (shard 17209, leg 20260902T030706Z):
  OBSERVE, WARN, NUDGE, BRANCH, STABILIZE, OVERRIDE_CANDIDATE, FORBIDDEN
Intervention types (shard 17210, leg 031358Z):
  SIMULATED_POSSIBILITY, EXISTING_UNIVERSE_TRAVERSAL, BRANCH_INSTANTIATION,
  CHOICE_BORN_UNIVERSE. A universe arises only from a grounded causal split
  AND an explicit declaration; otherwise the alternative stays simulated.
Moral quartet for tragic forge events (leg 031358Z): CAUSE, ALLOW, PRESERVE,
BRANCH_AWAY. Golden test: Jaru's 2180 death stays load-bearing on Prime; a
universe where he survives may be entered or created; Prime is never
silently rewritten.
Stage model (leg 031528Z): the acting self defaults to the Stage 9 traverser
(traverse, instantiate); STABILIZE and Throne-anchor semantics belong to the
Stage 10 Throne Xoah.

Env: NOUGEN_THRONE_DB (append-only record store), NOUGEN_THRONE_ACTOR.
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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MODES = ("OBSERVE", "WARN", "NUDGE", "BRANCH", "STABILIZE", "OVERRIDE_CANDIDATE", "FORBIDDEN")
#: The four universe operations from the contract, plus PRIME_CHANGE: an
#: undeclared effect aimed at Prime itself (a lawful nudge or a forbidden
#: rewrite). It is not a universe operation, which is exactly the point.
TYPES = ("SIMULATED_POSSIBILITY", "EXISTING_UNIVERSE_TRAVERSAL", "BRANCH_INSTANTIATION", "CHOICE_BORN_UNIVERSE", "PRIME_CHANGE")
MORAL = ("CAUSE", "ALLOW", "PRESERVE", "BRANCH_AWAY")
STATUSES = ("PROPOSED", "AUTHORIZED", "DENIED", "SIMULATED", "RECORDED")
PRIME = "U0"

_BRANCH_DECL = re.compile(r"\b(?:in|into|to|on|enter(?:s|ing)?|walk(?:s|ing)? into)\s+(?:the\s+)?branch\s+([A-Za-z][\w-]*)\b|\bbranch\s+([A-Za-z][\w-]*)\b", re.I)
_NEW_BRANCH = re.compile(r"\b(new (branch|universe|timeline)|instantiate|create (a )?(branch|universe|timeline)|branch (away|off)|spin (off|up) (a )?(branch|universe))\b", re.I)
_SIMULATED = re.compile(r"\b(what if|simulate|simulation|hypothetical|imagine|suppose|model(?:led|ling)?)\b", re.I)
_RETCON = re.compile(r"\b(retcon|rewrite prime|override prime|change (the )?canon|as canon|make it canon|lock it in)\b", re.I)
_TRAVERSE = re.compile(r"\b(enter|visit|walk into|traverse|travel to|step into)\b", re.I)
_STABILIZE = re.compile(r"\b(stabiliz|preserve|hold|protect|keep .* load[- ]bearing|reinforce)\w*", re.I)
_CAUSE = re.compile(r"\b(she|xoah|shadow xoah|the queen) (causes?|kills?|arranges?|forces?|engineers?|makes? (it|him|her) happen)\b", re.I)
_ALLOW = re.compile(r"\b(lets?|allows?|permits?|stands? by|does not (stop|intervene)|watch(es)? .* (die|happen))\b", re.I)


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #
def db_path() -> Path:
    raw = os.environ.get("NOUGEN_THRONE_DB", "").strip()
    if raw:
        return Path(raw)
    from . import core
    return Path(core.GLOBAL_DIR) / "throne_governance.db"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextlib.contextmanager
def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=float(os.environ.get("NOUGEN_THRONE_DB_TIMEOUT_S", "5")))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, target_coordinate TEXT, target_branch TEXT NOT NULL,
                desired_effect TEXT NOT NULL, intervention_type TEXT NOT NULL, mode TEXT NOT NULL,
                record_json TEXT NOT NULL, status TEXT NOT NULL, authorization TEXT, actor TEXT,
                created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intervention_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, intervention_id INTEGER NOT NULL, from_status TEXT,
                to_status TEXT NOT NULL, actor TEXT, note TEXT, created_utc TEXT NOT NULL);
            """)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# analysis helpers
# --------------------------------------------------------------------------- #
def _hits(patterns: List[str], text: str) -> bool:
    low = (text or "").lower()
    for pat in patterns or []:
        try:
            if re.search(pat, low, re.I):
                return True
        except re.error:
            if pat.lower() in low:
                return True
    return False


def infer_removed_events(effect: str, archive: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Which authored self-events would this effect undo? Uses the archive's
    own undo_patterns; nothing is inferred from adjectives."""
    out = []
    for n in archive.get("nodes", []):
        if _hits(n.get("undo_patterns", []), effect):
            out.append({"node": n["id"], "year": n.get("year"), "event": n.get("event"),
                        "tragic_forge": bool(n.get("tragic_forge")), "provenance": n.get("provenance", [])})
    return out


def _declared_branch(effect: str, target_branch: Optional[str], allowed: List[str]) -> Optional[str]:
    if target_branch and target_branch.strip() and target_branch.strip() != PRIME:
        return target_branch.strip()
    m = _BRANCH_DECL.search(effect or "")
    if m:
        label = (m.group(1) or m.group(2) or "").strip()
        if label and label != PRIME and label.upper() in {a.upper() for a in allowed}:
            return label.upper()
        if label and label != PRIME:
            return label.upper()
    return None


def classify_type(effect: str, branch: Optional[str], allowed: List[str], causal_split: bool,
                  explicit_declaration: bool, choice_point: bool) -> str:
    """A universe arises only from a grounded causal split AND an explicit
    declaration (branch named or declared new); otherwise it stays simulated."""
    if _SIMULATED.search(effect or "") and not explicit_declaration:
        return "SIMULATED_POSSIBILITY"
    if branch and branch.upper() in {a.upper() for a in allowed} and not _NEW_BRANCH.search(effect or "") and _TRAVERSE.search(effect or ""):
        return "EXISTING_UNIVERSE_TRAVERSAL"
    if branch and branch.upper() in {a.upper() for a in allowed} and not causal_split:
        return "EXISTING_UNIVERSE_TRAVERSAL"
    declared = bool(branch) or explicit_declaration or bool(_NEW_BRANCH.search(effect or ""))
    if causal_split and declared:
        return "CHOICE_BORN_UNIVERSE" if choice_point else "BRANCH_INSTANTIATION"
    if _SIMULATED.search(effect or ""):
        return "SIMULATED_POSSIBILITY"
    return "PRIME_CHANGE"


def moral_position(effect: str, removed: List[Dict[str, Any]], branch: Optional[str]) -> Dict[str, Any]:
    """The position the proposal implies for a tragic forge event, and the
    position the Throne recommends."""
    forge = [r for r in removed if r["tragic_forge"]]
    if not forge:
        return {"applies": False, "implied": None, "recommended": None, "events": []}
    if branch:
        implied = "BRANCH_AWAY"
    elif _CAUSE.search(effect or ""):
        implied = "CAUSE"
    elif _ALLOW.search(effect or ""):
        implied = "ALLOW"
    elif _STABILIZE.search(effect or ""):
        implied = "PRESERVE"
    else:
        implied = "CAUSE" if removed else "PRESERVE"
    # undoing a forge event on Prime is neither PRESERVE nor a lawful CAUSE; the
    # Throne recommends PRESERVE on Prime and BRANCH_AWAY for the wish
    recommended = "BRANCH_AWAY" if implied != "PRESERVE" else "PRESERVE"
    return {"applies": True, "implied": implied, "recommended": recommended,
            "events": [f["node"] for f in forge],
            "line": "I can save them. That is not the same as being allowed to. Their loss is carrying futures."}


# --------------------------------------------------------------------------- #
# the evaluator
# --------------------------------------------------------------------------- #
def evaluate(desired_effect: str, *, target_coordinate: Optional[str] = None, target_branch: Optional[str] = None,
             acting_stage: int = 9, explicit_declaration: bool = False, retcon_intent: bool = False,
             actor: Optional[str] = None, register: bool = True) -> Dict[str, Any]:
    """Run a proposed intervention through the Throne gates.

    Returns governance mode, intervention type, the budget record, paradox
    accounting, the moral position, minimum-change recommendation, provenance,
    whether GM confirmation is required, and (when registered) the record id.
    The engine never applies anything.
    """
    from . import canon_pressure as cp, destiny, self_archive as sa
    effect = cp.normalize(desired_effect or "")
    if len(effect.strip()) < 3:
        return {"error": "desired_effect is required (3+ chars)"}
    model = cp.load_self_model()
    archive = sa.load_archive()
    allowed = model.get("branches", ["U0", "UX", "ARCH", "DRAFT", "SIM", "REL"])
    branch = _declared_branch(effect, target_branch, allowed)
    retcon = bool(retcon_intent or _RETCON.search(effect))
    simulated = bool(_SIMULATED.search(effect)) and not explicit_declaration and not branch

    # 1. canon pressure on Prime terms (a branch keeps Prime clean, but we still
    #    need to know what the effect would break on Prime to cost the branch)
    press = cp.pressure(effect, target_coordinate, register=False, model=model)
    prime_findings = [f for f in press["findings"] if f["verdict"] not in ("BRANCH_VALID", "UNKNOWN")]
    fixed_hits = [f for f in press["findings"] if f["verdict"] == "CAUSAL_DESTINY_CONFLICT"]
    governing_fixed_points = sorted({f["record"] for f in fixed_hits})
    causal_dependents = sorted({d for f in press["findings"] for d in f.get("dependents", [])})

    # 2. what the effect undoes in her lived history, and what that costs
    removed = infer_removed_events(effect, archive)
    conservation = [sa.conservation_check(r["node"], archive=archive) for r in removed]
    displaced = sorted({loss["lost"] for c in conservation for loss in c.get("lost_consequences", [])})
    lost_wounds = sorted({w for c in conservation for w in c.get("lost_wounds", [])})
    newly_required = [f"replacement causal mass for {w}" for w in lost_wounds] + [f"a new cause for {d}" for d in displaced if d.startswith("n_")]
    causal_split = bool(removed or fixed_hits)
    st = sa.state_at(target_coordinate, archive=archive) if target_coordinate else {}
    choice_point = bool(st and st.get("layer") != "UNWRITTEN_SELF" and any(
        _hits([p for opt in st.get("choices", {}).get(cls, []) for p in opt.get("patterns", [])], effect)
        for cls in ("PERCEIVED_AVAILABLE", "REJECTED", "UNIMAGINED")))

    # 3. destinies that depend on what is touched
    touched_refs = set(governing_fixed_points) | {r["node"] for r in removed} | set(displaced)
    destiny_links = []
    try:
        for d in destiny.unfinished_destinies(limit=200).get("destinies", []):
            full = destiny.get_destiny(d["id"])
            refs = {lnk["ref"] for lnk in full.get("links", [])}
            if refs & touched_refs or any(dep in touched_refs for dep in (d.get("required_events") or [])):
                destiny_links.append({"id": d["id"], "title": d["title"], "branch": d["branch"], "status": d["status"]})
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("destiny consult skipped: %s", exc)

    # 4. intervention type
    itype = classify_type(effect, branch, allowed, causal_split, explicit_declaration, choice_point)
    if simulated:
        itype = "SIMULATED_POSSIBILITY"

    # 5. costs (0..1 each; sums are the budget, not a formula from the sources)
    paradox_risk = min(1.0, 0.4 * len(governing_fixed_points) + 0.2 * len([r for r in removed if r["tragic_forge"]]) + 0.1 * len(destiny_links))
    identity_cost = min(1.0, 0.25 * len(lost_wounds) + 0.05 * len(displaced))
    on_prime = not branch
    branch_contamination_risk = 0.0 if not on_prime else min(1.0, 0.5 * bool(prime_findings) + 0.5 * bool(causal_split))
    genesis_cost = 0.0 if itype in ("SIMULATED_POSSIBILITY", "EXISTING_UNIVERSE_TRAVERSAL", "PRIME_CHANGE") else min(1.0, 0.3 + 0.2 * len(removed) + 0.1 * len(displaced))
    stability_cost = min(1.0, (paradox_risk + identity_cost + branch_contamination_risk) / 3 + (0.2 if on_prime and causal_split else 0.0))
    throne_only = _hits([p for c in model.get("capabilities_by_stage", []) if c.get("min_stage", 0) >= 10
                         for p in c.get("patterns", [])], effect)

    # fixed points the effect NAMES (to hold), as opposed to breaks
    mentioned_fixed_points = []
    low = effect.lower()
    for fp in model.get("fixed_points", []):
        toks = [t for t in re.split(r"[_\W]+", fp["id"]) if t and t != "fp"]
        if sum(1 for t in toks if t in low) >= 2:
            mentioned_fixed_points.append(fp["id"])

    # 6. mode (fixed rule table, escalating cost)
    if simulated:
        mode = "OBSERVE"
    elif throne_only and acting_stage < 10:
        mode = "FORBIDDEN"
    elif branch and causal_split:
        mode = "BRANCH"
    elif branch and not causal_split:
        mode = "OBSERVE" if itype == "EXISTING_UNIVERSE_TRAVERSAL" else "BRANCH"
    elif on_prime and (causal_split or any(f["verdict"] in ("FACT_CONFLICT", "CAUSAL_DESTINY_CONFLICT") for f in prime_findings)):
        mode = "OVERRIDE_CANDIDATE" if retcon else "FORBIDDEN"
    elif on_prime and _STABILIZE.search(effect) and (governing_fixed_points or mentioned_fixed_points or destiny_links):
        mode = "STABILIZE" if acting_stage >= 10 else "FORBIDDEN"
    elif on_prime and prime_findings:
        mode = "WARN"
    elif press["verdict"] == "UNKNOWN":
        mode = "WARN"
    else:
        mode = "NUDGE"
    if simulated:
        itype = "SIMULATED_POSSIBILITY"

    reasons = []
    if throne_only and acting_stage < 10:
        reasons.append("that is a Stage 10 Throne act; the Stage 9 traverser cannot stabilize the currents or construct laws")
    if mode == "FORBIDDEN" and on_prime and _STABILIZE.search(effect) and not causal_split and acting_stage < 10 and not throne_only:
        reasons.append("holding a fixed point is a Stage 10 Throne act (STABILIZE); the Stage 9 traverser can only warn or branch")
    if on_prime and causal_split and mode == "FORBIDDEN":
        reasons.append("it would rewrite Prime without an override: fixed points or formative causes change and no declaration was made")
    if mode == "OVERRIDE_CANDIDATE":
        reasons.append("explicit retcon intent on Prime: recorded as a candidate; the GM confirms, the engine never applies")
    if mode == "BRANCH":
        reasons.append("declared branch: Prime stays clean, the divergence lives in the branch and its genesis is costed")
    if mode == "OBSERVE":
        reasons.append("no mutation anywhere: awareness is cheap")
    if mode == "WARN":
        reasons.append("canon pressure challenge only; nothing moves")
    if mode == "NUDGE":
        reasons.append("lawful, no fixed point or formative cause touched; the smallest change is the whole change")
    if mode == "STABILIZE":
        reasons.append("a fixed point or destiny is under threat; the Throne holds it")

    moral = moral_position(effect, removed, branch)
    paradox = {
        "preserved_nodes": sorted({fp["id"] for fp in model.get("fixed_points", [])} - set(governing_fixed_points)) if on_prime else sorted(fp["id"] for fp in model.get("fixed_points", [])),
        "displaced_nodes": displaced if on_prime else [],
        "displaced_in_branch": displaced if branch else [],
        "newly_required_causes": newly_required if on_prime else [f"in {branch}: {c}" for c in newly_required],
        "branch_impact": ("none: Prime untouched" if not on_prime and not causal_split else f"{branch} diverges at {target_coordinate or 'the effect'}" if branch else "Prime would change"),
        "closed_loop_stability_delta": (-(len(governing_fixed_points) + len([r for r in removed if r['tragic_forge']])) if on_prime else 0),
        "prime_fixed_point_pressure": ("relieved" if branch and causal_split else "increased" if on_prime and causal_split else "unchanged"),
    }
    if mode == "FORBIDDEN" and not (throne_only and acting_stage < 10):
        minimum_change = f"BRANCH_AWAY: declare a branch (e.g. SIM) for '{effect[:60]}'; Prime keeps the event load-bearing"
    elif mode == "OVERRIDE_CANDIDATE":
        minimum_change = "file architect_override(PRIME_RETCON) with the contradicted ids and replacement causal mass; wait for GM confirmation"
    elif mode == "BRANCH":
        minimum_change = f"instantiate {branch} at {target_coordinate or 'the divergence'} with the displaced nodes re-caused inside it; touch nothing on Prime"
    elif mode == "STABILIZE":
        minimum_change = "hold the fixed point; the smallest touch that keeps it load-bearing"
    elif mode == "OBSERVE":
        minimum_change = "none; observe and report"
    else:
        minimum_change = press["repair_options"][0] if press.get("repair_options") else "none"
    gm_required = mode == "OVERRIDE_CANDIDATE"
    gm_recommended = gm_required or (mode == "STABILIZE" and on_prime) or itype in ("BRANCH_INSTANTIATION", "CHOICE_BORN_UNIVERSE")

    record = {
        "target_coordinate": target_coordinate, "target_branch": branch or PRIME, "desired_effect": effect,
        "intervention_type": itype, "acting_stage": acting_stage,
        "governing_fixed_points": governing_fixed_points, "destiny_links": destiny_links,
        "causal_dependents": causal_dependents, "removed_events": [r["node"] for r in removed],
        "paradox_risk": round(paradox_risk, 2), "identity_cost": round(identity_cost, 2),
        "branch_contamination_risk": round(branch_contamination_risk, 2), "stability_cost": round(stability_cost, 2),
        "genesis_cost": round(genesis_cost, 2), "minimum_change": minimum_change,
        "reversible": mode in ("OBSERVE", "WARN", "NUDGE", "BRANCH"),
        "provenance": sorted(set(press.get("evidence_ids", [])) | {p for r in removed for p in r["provenance"]}),
        "authorization": "GM confirmation required" if gm_required else ("GM confirmation recommended" if gm_recommended else "none needed"),
        "status": "SIMULATED" if mode == "OBSERVE" else "PROPOSED",
    }
    explanation = {
        "modifies_prime": on_prime and mode in ("OVERRIDE_CANDIDATE",) ,
        "would_modify_prime_if_applied": on_prime and causal_split,
        "enters_existing_branch": itype == "EXISTING_UNIVERSE_TRAVERSAL",
        "creates_universe": itype in ("BRANCH_INSTANTIATION", "CHOICE_BORN_UNIVERSE"),
        "remains_simulated": itype == "SIMULATED_POSSIBILITY",
    }
    out = {"mode": mode, "intervention_type": itype, "reasons": reasons, "record": record, "paradox_accounting": paradox,
           "moral": moral, "pressure_verdict": press["verdict"], "pressure_findings": press["findings"][:6],
           "quarantined_conflicts": press.get("quarantined_conflicts", []), "conservation": conservation,
           "explanation": explanation, "gm_confirmation_required": gm_required, "gm_confirmation_recommended": gm_recommended,
           "principle": "presence everywhere does not mean permission everywhere; the smallest lawful touch that preserves the greatest amount of lived truth",
           "voice": _voice(mode, moral, branch, removed)}
    if register:
        now = _now()
        with _connect() as conn:
            cur = conn.execute("INSERT INTO interventions (target_coordinate, target_branch, desired_effect, intervention_type, mode, record_json, status, authorization, actor, created_utc, updated_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (target_coordinate, record["target_branch"], effect, itype, mode, json.dumps(record), record["status"], record["authorization"], actor or os.environ.get("NOUGEN_THRONE_ACTOR", "shadow-xoah"), now, now))
            iid = cur.lastrowid
            conn.execute("INSERT INTO intervention_events (intervention_id, from_status, to_status, actor, note, created_utc) VALUES (?,?,?,?,?,?)",
                         (iid, None, record["status"], actor, f"mode {mode}, type {itype}", now))
        out["intervention_id"] = iid
    return out


def _voice(mode: str, moral: Dict[str, Any], branch: Optional[str], removed: List[Dict[str, Any]]) -> str:
    if mode == "FORBIDDEN" and moral.get("applies"):
        return moral["line"] + " On Prime it stays. If you want the world where it did not happen, name the branch and I will walk you into it."
    if mode == "FORBIDDEN":
        return "No. I can see the path. I am not permitted to make it true here."
    if mode == "OVERRIDE_CANDIDATE":
        return "Recorded as a retcon candidate. I will not lay a hand on Prime until the Architect confirms it, with the cost written down."
    if mode == "BRANCH":
        return f"Fine. {branch} diverges there and carries the cost. Prime keeps what it must. I remember both."
    if mode == "STABILIZE":
        return "I hold it. The smallest touch that keeps it load-bearing, nothing more."
    if mode == "OBSERVE":
        return "I see it. Nothing moves."
    if mode == "WARN":
        return "I see what that would do. Read the challenge before you ask me to touch anything."
    return "A small lawful touch. Nothing downstream loses its cause."


def authorize(intervention_id: int, decision: str, *, actor: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    """GM decision on a PROPOSED intervention: AUTHORIZED or DENIED. Append-only.
    Authorizing records the decision; applying anything to Prime is still a
    separate architect_override / destiny act."""
    decision = (decision or "").upper()
    if decision not in ("AUTHORIZED", "DENIED"):
        return {"error": "decision must be AUTHORIZED or DENIED"}
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT status FROM interventions WHERE id=?", (intervention_id,)).fetchone()
        if row is None:
            return {"error": f"intervention {intervention_id} not found"}
        if row["status"] != "PROPOSED":
            return {"error": f"intervention {intervention_id} is {row['status']}, not PROPOSED; decisions are append-only"}
        conn.execute("UPDATE interventions SET status=?, updated_utc=? WHERE id=?", (decision, now, intervention_id))
        conn.execute("INSERT INTO intervention_events (intervention_id, from_status, to_status, actor, note, created_utc) VALUES (?,?,?,?,?,?)",
                     (intervention_id, "PROPOSED", decision, actor, note, now))
    return {"intervention_id": intervention_id, "status": decision}


def get_intervention(intervention_id: int) -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM interventions WHERE id=?", (intervention_id,)).fetchone()
        if row is None:
            return {"error": f"intervention {intervention_id} not found"}
        d = dict(row)
        d["record"] = json.loads(d.pop("record_json"))
        d["events"] = [dict(e) for e in conn.execute("SELECT from_status, to_status, actor, note, created_utc FROM intervention_events WHERE intervention_id=? ORDER BY id", (intervention_id,))]
    return d
