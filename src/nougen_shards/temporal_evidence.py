"""Stopgap shim for nougen_shards.temporal_evidence.

WHY THIS EXISTS: core.py gained `from .temporal_evidence import
assess_temporal_evidence` (edit of 2026-09-06 08:43 on blade push-main, see
core.py.orig) but the module itself was never shipped to ANY checkout on blade
or whoart, nor to Who-Visions/NouGenShards main. Every capture whose payload
exercised the temporal branch then 500'd with ModuleNotFoundError -- the real
mechanism behind the "forward failed: HTTPError" intermittency (payload-
dependent, not auth). Deployed by whoart/outpost-1d 2026-09-06 ~19:00Z,
upgraded ~19:15Z after AttributeError showed the full contract.

CONTRACT (from core.py:820-847): assess_temporal_evidence(title, content,
metadata) -> object with .as_dict(), .trusted_event_timestamp, .status.value.

WHAT IT DOES: satisfies that contract with an honest no-op. It performs NO
temporal analysis: trusted_event_timestamp stays None (never fabricate trust)
and status reads UNASSESSED, so provenance queries can find and re-assess these
rows once the real implementation (legs 20260905T200528Z / 200820Z) ships.
Replace this file with the real module; the lazy import picks it up on the
next call without a restart.
"""


class _Status:
    value = "UNASSESSED"


class _NoopAssessment:
    status = _Status()
    trusted_event_timestamp = None

    def as_dict(self):
        return {
            "assessed": False,
            "assessor": "temporal_evidence-shim-20260906",
            "temporal_status": _Status.value,
            "trusted_event_timestamp": None,
            "note": "real temporal_evidence module not yet shipped; no assessment performed",
        }


def assess_temporal_evidence(title=None, content=None, metadata=None, **kwargs):
    return _NoopAssessment()
