"""The node must publish which redaction code it is RUNNING.

On 2026-09-08 a redaction fix merged to main three times and ran on no live
process in the fleet. Fifteen copies of the module existed across two nodes and
one had the fix. Establishing that took per-OS process archaeology (lsof,
ps eww) which does not run on half the fleet at all.

A published count and fingerprint turn that into one HTTP call from anywhere.
"""

import hashlib

from nougen_shards.brain_scan import redaction


def test_fingerprint_is_stable_and_short():
    assert redaction.pattern_fingerprint() == redaction.pattern_fingerprint()
    assert len(redaction.pattern_fingerprint()) == 16


def test_fingerprint_is_derived_from_the_patterns_themselves():
    joined = "\n".join(p.pattern for p, _ in redaction.SECRET_PATTERNS)
    assert redaction.pattern_fingerprint() == \
        hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def test_fingerprint_changes_when_the_set_changes(monkeypatch):
    """A set that gains a pattern must not keep the same identity.

    Otherwise two nodes compare fingerprints, agree, and are running different
    code -- which is the whole failure this is meant to expose.
    """
    import re
    before = redaction.pattern_fingerprint()
    monkeypatch.setattr(
        redaction, "SECRET_PATTERNS",
        list(redaction.SECRET_PATTERNS) + [(re.compile(r"zzz_[0-9]{8}"), "<X>")])
    assert redaction.pattern_fingerprint() != before


def test_health_helpers_never_raise(monkeypatch):
    """Health must degrade, never 500.

    A node that cannot answer /health is indistinguishable from a node that is
    down, and this field is diagnostic -- it must never be why the endpoint
    fails. Exercised by making the redaction module itself raise, since the
    module is already imported and cached by the time health runs.
    """
    import app
    assert app._redaction_count() == len(redaction.SECRET_PATTERNS)
    assert app._redaction_fingerprint() == redaction.pattern_fingerprint()

    def boom():
        raise RuntimeError("simulated")

    monkeypatch.setattr(redaction, "pattern_fingerprint", boom)
    assert app._redaction_fingerprint() == "unavailable"

    monkeypatch.delattr(redaction, "SECRET_PATTERNS")
    assert app._redaction_count() == -1


def test_public_health_does_not_publish_a_filesystem_path():
    """The path is deployment topology and must stay off the public view."""
    import inspect

    import app
    src = inspect.getsource(app._redaction_fingerprint) + \
        inspect.getsource(app._redaction_count)
    assert "__file__" not in src
    assert "path" not in src.lower()
