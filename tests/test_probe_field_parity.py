"""The which-node-answered decision. Each case names the deployment it protects.

Hermetic by construction: compare_identity() is pure, so the suite exercises the
verdict without touching a tunnel, a Worker, or the network.
"""
import importlib.util
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "probe_field_parity.py"
_spec = importlib.util.spec_from_file_location("probe_field_parity", _TOOL)
parity = importlib.util.module_from_spec(_spec)
sys.modules["probe_field_parity"] = parity
_spec.loader.exec_module(parity)


def ok(url="https://example.invalid/health", worker=None, **fields):
    return {"url": url, "ok": True, "status": 200, "fields": fields,
            "worker_header": worker, "error": None}


def dead(url="https://example.invalid/health", error="URLError: refused"):
    return {"url": url, "ok": False, "status": None, "fields": {},
            "worker_header": None, "error": error}


def verdict(public, direct):
    return parity.compare_identity(public, direct)["verdict"]


# --- the incident this tool exists for -------------------------------------

def test_shadowed_hostname_reads_as_mismatch():
    """2026-09-01: ngs.nougenai.com was CNAME'd to phoebus's healthy tunnel and
    answered by blade/the Space anyway, because a Worker route outranks DNS at
    the edge. Both sides were 200 -- only the fields told the truth."""
    public = ok(deploy_sha="5860a5de", storage="/data", persistent_storage=True,
                worker="space")
    direct = ok(deploy_sha=None, storage="default", persistent_storage=False)
    assert verdict(public, direct) == "MISMATCH"


def test_mismatch_carries_the_evidence_not_just_the_conclusion():
    """An operator who cannot see WHICH field diverged re-derives the diff by
    hand, which is how the two weeks of shadowing went unnoticed."""
    public = ok(storage="/data")
    direct = ok(storage="default")
    result = parity.compare_identity(public, direct)
    assert ("storage", "/data", "default") in result["differences"]


def test_dedicated_hostname_reads_as_match():
    """phoebus.nougenai.com after the fix: same node, so the same identity."""
    node = dict(deploy_sha=None, storage="default", persistent_storage=False)
    assert verdict(ok(**node), ok(**node)) == "MATCH"


# --- absent is not null ----------------------------------------------------

def test_absent_field_never_equals_a_null_field():
    """deploy_sha is legitimately null on an undeployed node. A side that omits
    the key entirely is a different answer, and collapsing the two would let a
    stripped-down proxy response pass as the origin."""
    public = ok(storage="default")                       # deploy_sha omitted
    direct = ok(storage="default", deploy_sha=None)      # deploy_sha present
    assert verdict(public, direct) == "MISMATCH"


def test_fields_absent_from_both_sides_are_not_a_difference():
    assert verdict(ok(storage="default"), ok(storage="default")) == "MATCH"


# --- unreachable is its own answer -----------------------------------------

def test_unreadable_public_is_not_reported_as_a_mismatch():
    """The probe cannot prove a mismatch it never observed. Reporting one would
    send an operator to fix routing that may be fine."""
    assert verdict(dead(), ok(storage="default")) == "UNREACHABLE"


def test_unreadable_direct_is_not_reported_as_a_match():
    """The dangerous direction: a green verdict here would vouch for an origin
    that was never actually read."""
    assert verdict(ok(storage="default"), dead()) == "UNREACHABLE"


def test_unreachable_names_which_side_failed_and_why():
    result = parity.compare_identity(dead(error="TimeoutError: timed out"),
                                     ok(storage="default"))
    assert any("timed out" in note for note in result["notes"])


def test_unreachable_does_not_exit_zero():
    """Exit 0 from a probe that read nothing is the false green in miniature."""
    assert parity.EXIT_CODES["UNREACHABLE"] != 0
    assert parity.EXIT_CODES["MATCH"] == 0
    assert parity.EXIT_CODES["MISMATCH"] == 1


# --- an intermediary is worth saying out loud ------------------------------

def test_worker_in_the_public_path_is_reported_even_when_fields_agree():
    """Parity through a proxy is still parity, but the caller should know the
    identity was relayed rather than served -- the Worker chose the origin, and
    it can choose a different one on the next call."""
    public = ok(storage="default", worker="blade")
    direct = ok(storage="default")
    result = parity.compare_identity(public, direct)
    assert result["verdict"] == "MATCH"
    assert any("Worker is in the public path" in note for note in result["notes"])
