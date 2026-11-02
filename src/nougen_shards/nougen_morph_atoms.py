"""NouGenMorph atom catalog: dynamically loads `tools/morph_atoms.py` from the
canonical nougen-radar repository root (same Env -> probed-candidates discovery
as `arxiv_radar.find_radar_root`) and exposes it as `run_morph_atom_catalog`.

Degrades to a "degraded" status dict (never an ImportError) when the radar repo
or the morph_atoms.py tool isn't installed on this node, per UDCT doctrine:
probe, don't assume; log the miss rather than crash the caller.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .arxiv_radar import _load_module, find_radar_root


def _load_morph_atoms_tool():
    root = find_radar_root()
    if not root:
        return None
    tools_dir = root / "tools" if (root / "tools").is_dir() else root
    tool_path = tools_dir / "morph_atoms.py"
    if not tool_path.exists():
        return None
    return _load_module("morph_atoms", tool_path)


def run_morph_atom_catalog(query: str = "", limit: int = 20) -> Dict[str, Any]:
    """Catalog already-verified morph_gate evidence rows into named structural atoms."""
    mod = _load_morph_atoms_tool()
    if not mod:
        return {
            "status": "degraded",
            "available": False,
            "error": "nougen-radar repository not installed or morph_atoms.py missing",
        }
    try:
        res = mod.catalog(query=query, limit=limit)
        return {
            "status": "success",
            "available": True,
            "result": res,
            "provenance": "Who-Visions/nougen-radar tools/morph_atoms.py",
        }
    except Exception as e:  # noqa: BLE001 - any failure here is a non-fatal degrade
        return {"status": "error", "available": True, "error": str(e)}


@dataclass(frozen=True)
class MorphAtom:
    source: str
    claim: str
    confidence: Any = None
    evidence_type: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NouGenMorphCatalog:
    """The contract app.py calls; atoms come only from captured morph_gate evidence."""

    @staticmethod
    def get_all_atoms(limit: int = 200) -> Dict[str, MorphAtom]:
        res = run_morph_atom_catalog(limit=limit)
        rows = (res.get("result") or {}).get("atoms") or []
        return {
            f"{r.get('source')}::{r.get('claim')}": MorphAtom(
                r.get("source"), r.get("claim"), r.get("confidence"), r.get("evidence_type")
            )
            for r in rows
        }


@dataclass(frozen=True)
class PromotionDecision:
    candidate_id: str
    promoted: bool
    benchmark_gain: float
    regressions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HolisticPromotionGate:
    """A benchmark gain cannot buy a regression on any other measured dimension."""

    @staticmethod
    def evaluate_promotion(
        candidate_id: str,
        baseline: Dict[str, float],
        candidate: Dict[str, float],
        regression_tolerance: float = 0.0,
    ) -> PromotionDecision:
        gain = candidate["benchmark_score"] - baseline["benchmark_score"]
        regressions = [
            k for k, base in baseline.items()
            if k != "benchmark_score" and base - candidate[k] > regression_tolerance
        ]
        return PromotionDecision(candidate_id, gain > 0 and not regressions, gain, regressions)
