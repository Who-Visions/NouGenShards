"""``nougen wishlist``: the canonical 100-item resilience/context wishlist as
a real, trackable artifact, not a relay leg nobody can query.

Source: relay leg 20260910T202128Z (original), rebroadcast 20260923T174020Z
(Dave's explicit order for a fresh shard + relay). Items, numbering,
categories and phases below are copied VERBATIM from the rebroadcast text --
this module never rewords an item, because the id is the citation.

    Priority doctrine: memory spine first, context integrity second, quota
    survival third, autonomous acceleration only after those are proven.
    No false green. No completion stamp without live verification from the
    consuming lane.

That doctrine is enforced structurally: an item can only be marked LANDED
with evidence attached (a shard id, leg id, PR#, or commit sha) -- there is
no bare "done" state. This is the same discipline the wishlist itself asks
for (item 86: "Require completion evidence in the relay record"), applied to
tracking the wishlist about that discipline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

__all__ = [
    "ItemStatus", "WishlistItem", "WishlistState", "CATEGORIES", "ITEMS",
    "load_state", "save_state", "default_state_path", "phase_of",
    "category_of", "progress_by_phase", "progress_by_category",
]

SOURCE_LEG_ORIGINAL = "20260910T202128Z__chatgpt-app__g-whoentertains"
SOURCE_LEG_REBROADCAST = "20260923T174020Z__chatgpt-app__g-whoentertains"


class ItemStatus(str, Enum):
    OPEN = "open"                # not started
    IN_PROGRESS = "in_progress"  # someone has claimed it
    LANDED = "landed"            # implemented AND evidenced
    VERIFIED = "verified"        # landed AND independently re-checked by a
                                  # different identity than the implementer
                                  # (item 87: "verifier identity separate
                                  # from implementer identity")


# --------------------------------------------------------------- categories
CATEGORIES: Dict[str, str] = {
    "A": "Multi vault memory spine",
    "B": "Health truth and false green prevention",
    "C": "NouGen Context Mode enforcement",
    "D": "Quota conservation and cost control",
    "E": "Relay and ownership discipline",
    "F": "Autonomous recovery and observability",
}

# Item number -> category letter, exactly per the rebroadcast's own section
# boundaries (A: 1-20, B: 21-40, C: 41-60, D: 61-80, E: 81-90, F: 91-100).
_CATEGORY_BOUNDS = (("A", 1, 20), ("B", 21, 40), ("C", 41, 60),
                    ("D", 61, 80), ("E", 81, 90), ("F", 91, 100))

# Execution phases, per the rebroadcast's own "Execution order" section.
_PHASE_BOUNDS = ((1, 1, 40), (2, 41, 60), (3, 61, 90), (4, 91, 100))


def category_of(item_id: int) -> str:
    for letter, lo, hi in _CATEGORY_BOUNDS:
        if lo <= item_id <= hi:
            return letter
    raise ValueError(f"item id {item_id} out of range 1..100")


def phase_of(item_id: int) -> int:
    for phase, lo, hi in _PHASE_BOUNDS:
        if lo <= item_id <= hi:
            return phase
    raise ValueError(f"item id {item_id} out of range 1..100")


# ------------------------------------------------------------------- items
# Verbatim text, ids 1-100, from the rebroadcast (leg 20260923T174020Z).
_RAW_ITEMS: List[str] = [
    # A. Multi vault memory spine (1-20)
    "Make every shard read query each physical machine vault independently.",
    "Preserve per machine provenance on every returned shard.",
    "Distinguish local database completeness from fleet vault completeness.",
    "Require Blade, Phoebus, and WhoArt responses before fleet complete can be true.",
    "Dynamically discover expected vaults instead of hardcoding machine names.",
    "Return explicit timeout, auth, unreachable, stale, and malformed states per vault.",
    "Never convert a timeout into an empty result.",
    "Set cannot_determine true whenever any expected vault is missing.",
    "Set recall_trustworthy false whenever fleet vault completeness is false.",
    "Merge and dedupe only after each reachable vault has answered.",
    "Preserve duplicate provenance when the same shard exists in more than one vault.",
    "Add a vault identity handshake so each machine proves which vault answered.",
    "Add per vault shard counts to coverage responses.",
    "Add per vault timestamp spans to coverage responses.",
    "Add per vault latency to every read response.",
    "Add per vault last successful read timestamp.",
    "Add per vault last successful write timestamp.",
    "Add per vault auth fingerprint or nonsecret identity marker.",
    "Detect self fanout and suppress recursion without suppressing local proof.",
    "Add bounded parallel fanout with one aggregate deadline.",
    # B. Health truth and false green prevention (21-40)
    "Redesign shards_status to report physical vault matrix, not only ingress health.",
    "Expose ingress origin explicitly and never return origin unknown when determinable.",
    "Separate gateway_up from memory_readable.",
    "Separate memory_readable from memory_complete.",
    "Separate local_db_complete from fleet_vault_complete.",
    "Add context_state values full, degraded, local_only, unavailable.",
    "Green requires all required physical vaults healthy for the requested operation.",
    "Yellow means partial but usable with provenance.",
    "Red means required memory path unavailable.",
    "Any contradictory health fields force degraded status.",
    "Add a consuming lane regression test for false green.",
    "Add a test where local 9 of 9 is green but one remote vault times out, result must be incomplete.",
    "Add a test where one vault returns HTTP 200 with zero rows while another errors.",
    "Add a test where peer discovery omits a known configured node.",
    "Add a test where ingress and responding source node differ.",
    "Add a test for stale health cache versus live read failure.",
    "Add a test for partial federation metadata surviving through MCP serialization.",
    "Add a machine readable reason field for every degraded state.",
    "Add health generation IDs so stale responses can be detected.",
    "Never mark a repair completed unless acceptance probes pass from ChatGPT or another external consumer.",
    # C. NouGen Context Mode enforcement (41-60)
    "Make Context Mode mandatory before substantive fleet work.",
    "Preflight begins with identity and reachability.",
    "Hydrate task relevant shards before model reasoning.",
    "Read current relay and claim state before overlapping work.",
    "Verify multi vault completeness when the task depends on historical truth.",
    "Preserve source_node on all hydrated context.",
    "Mark context_state degraded when any required memory source fails.",
    "In degraded mode, prohibit claims of exhaustive recall.",
    "In degraded mode, prohibit absence conclusions.",
    "In degraded mode, prohibit destructive canon or infrastructure edits based on missing evidence.",
    "Reuse hydrated context within an active task instead of recalling every turn.",
    "Refresh context only when task scope or evidence changes.",
    "Add a context hydration cache keyed by task and evidence version.",
    "Add provenance summaries so models know why each memory is trusted.",
    "Add amendment and retraction awareness to context assembly.",
    "Prefer current canonical shards over superseded variants.",
    "Include recent relay deltas that have not yet been durably sharded.",
    "Include active claims so agents do not duplicate work.",
    "Persist durable decisions, failures, and canon locks after execution.",
    "Expose a compact Context Mode receipt showing sources consulted and completeness.",
    # D. Quota conservation and cost control (61-80)
    "Keep emergency quota conservation active until explicitly released.",
    "Stop repeated model calls that only reconfirm the same infrastructure failure.",
    "Prefer deterministic probes over LLM analysis for health checks.",
    "Prefer local Ollama and Kaedra for bulk summarization and triage.",
    "Escalate to cloud models only when local confidence is insufficient.",
    "Add per task token budgets.",
    "Add per agent hourly token budgets.",
    "Add per node daily token ceilings.",
    "Add provider quota percentage thresholds.",
    "Trigger warning at 60 percent, hard conservation at 80 percent, critical at 90 percent.",
    "Prevent autonomous loops from continuing after critical quota state.",
    "Deduplicate identical prompts across concurrent agents.",
    "Cache stable system context and reuse it.",
    "Detect runaway cache read amplification.",
    "Detect sessions exceeding expected execution duration.",
    "Auto pause autonomous loops after repeated no progress cycles.",
    "Require measurable delta before spending another expensive reasoning turn.",
    "Add cost per useful change and tokens per verified result metrics.",
    "Separate infrastructure probes from generative workloads in accounting.",
    "Make quota state part of routing decisions.",
    # E. Relay and ownership discipline (81-90)
    "Every P0 relay must acquire a visible owner or escalate.",
    "Active claim list must reflect real current workers, not historical text inside a relay.",
    "Add claim leases with expiration and heartbeat.",
    "Auto release abandoned claims.",
    "Prevent status completed when done when criteria have not been verified.",
    "Require completion evidence in the relay record.",
    "Add verifier identity separate from implementer identity.",
    "Add reopen state when external verification fails.",
    "Auto reopen a completed relay if a live regression probe contradicts it.",
    "Collapse duplicate repair relays into one parent incident with child tasks.",
    # F. Autonomous recovery and observability (91-100)
    "Build a live three vault matrix dashboard for Blade, Phoebus, and WhoArt or dynamically discovered equivalents.",
    "Show latency, shard count, context state, relay claim state, and quota state per node.",
    "Add timeout root cause telemetry, DNS, tunnel, auth, process, database, embedding, federation.",
    "Add bounded automatic retry with jitter, never infinite retry storms.",
    "Add circuit breakers around failing peers.",
    "Add recovery probes after cooldown instead of constant polling.",
    "Add a single lightweight heartbeat path that costs no model tokens.",
    "Add an end to end Context Mode canary that recalls a known shard from each vault and verifies provenance.",
    "Add a one command Deep Health report that returns infrastructure, memory, relay, context, tracker, and quota "
    "truth without triggering model inference.",
    "Final acceptance gate: only restore full autonomous swarm when multi vault recall is complete, Context Mode "
    "is enforced, quota protection is active, relay ownership works, and an external consuming lane verifies all "
    "of it live.",
]

if len(_RAW_ITEMS) != 100:  # fail loudly if the transcription ever drifts
    raise RuntimeError(f"wishlist.py has {len(_RAW_ITEMS)} items, expected exactly 100 -- "
                      f"the rebroadcast text and this module have drifted")


@dataclass(frozen=True)
class WishlistItem:
    id: int
    category: str
    category_name: str
    phase: int
    text: str


ITEMS: Dict[int, WishlistItem] = {
    i + 1: WishlistItem(id=i + 1, category=category_of(i + 1),
                        category_name=CATEGORIES[category_of(i + 1)],
                        phase=phase_of(i + 1), text=text)
    for i, text in enumerate(_RAW_ITEMS)
}


# --------------------------------------------------------------- tracking
@dataclass
class ItemRecord:
    status: ItemStatus = ItemStatus.OPEN
    evidence: List[str] = field(default_factory=list)   # shard/leg/PR/sha citations
    owner: Optional[str] = None                          # "machine/agent"
    note: str = ""
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {"status": self.status.value, "evidence": list(self.evidence),
                "owner": self.owner, "note": self.note, "updated_at": self.updated_at}

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> "ItemRecord":
        return cls(status=ItemStatus(d.get("status", "open")),
                  evidence=list(d.get("evidence", [])), owner=d.get("owner"),
                  note=d.get("note", ""), updated_at=d.get("updated_at"))


class WishlistState:
    """The mutable, persisted tracking layer. ``ITEMS`` (the text) never
    changes; this is what changes as the fleet does the work."""

    def __init__(self, records: Optional[Dict[int, ItemRecord]] = None):
        self.records: Dict[int, ItemRecord] = records or {
            i: ItemRecord() for i in ITEMS
        }

    def get(self, item_id: int) -> ItemRecord:
        if item_id not in ITEMS:
            raise KeyError(f"no such wishlist item: {item_id}")
        return self.records.setdefault(item_id, ItemRecord())

    def mark(self, item_id: int, status: ItemStatus, evidence: Optional[List[str]] = None,
            owner: Optional[str] = None, note: str = "") -> ItemRecord:
        """The one enforcement point in this module: LANDED and VERIFIED
        require at least one evidence citation. This is item 86 ("require
        completion evidence in the relay record") and item 40 ("never mark a
        repair completed unless acceptance probes pass") applied literally.
        """
        if status in (ItemStatus.LANDED, ItemStatus.VERIFIED) and not evidence:
            raise ValueError(f"item {item_id}: cannot mark {status.value} without at least one "
                            f"evidence citation (shard id / leg id / PR# / commit sha) -- "
                            f"'No completion stamp without live verification.'")
        rec = self.get(item_id)
        rec.status = status
        if evidence:
            rec.evidence = list(dict.fromkeys(rec.evidence + evidence))  # dedupe, keep order
        if owner:
            rec.owner = owner
        if note:
            rec.note = note
        rec.updated_at = datetime.now(timezone.utc).isoformat()
        return rec

    def to_dict(self) -> Dict[str, object]:
        return {"source_leg_original": SOURCE_LEG_ORIGINAL,
               "source_leg_rebroadcast": SOURCE_LEG_REBROADCAST,
               "items": {str(k): v.to_dict() for k, v in self.records.items()}}

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> "WishlistState":
        items = d.get("items", {})
        records = {int(k): ItemRecord.from_dict(v) for k, v in items.items()}
        return cls(records=records)


def default_state_path() -> Path:
    return Path.home() / ".nougen" / "wishlist_state.json"


def load_state(path: Optional[Path] = None) -> WishlistState:
    path = path or default_state_path()
    if not path.is_file():
        return WishlistState()
    return WishlistState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(state: WishlistState, path: Optional[Path] = None) -> Path:
    path = path or default_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


# ------------------------------------------------------------------ reports
def progress_by_phase(state: WishlistState) -> Dict[int, Dict[str, int]]:
    out: Dict[int, Dict[str, int]] = {p: {"total": 0, "open": 0, "in_progress": 0,
                                          "landed": 0, "verified": 0}
                                     for p in (1, 2, 3, 4)}
    for item_id, item in ITEMS.items():
        rec = state.records.get(item_id, ItemRecord())
        out[item.phase]["total"] += 1
        out[item.phase][rec.status.value] += 1
    return out


def progress_by_category(state: WishlistState) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {c: {"total": 0, "open": 0, "in_progress": 0,
                                          "landed": 0, "verified": 0}
                                     for c in CATEGORIES}
    for item_id, item in ITEMS.items():
        rec = state.records.get(item_id, ItemRecord())
        out[item.category]["total"] += 1
        out[item.category][rec.status.value] += 1
    return out
