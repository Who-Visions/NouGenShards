"""The evidence taxonomy, and the refusal that makes it work."""

import pytest

from nougen_shards import evidence


def test_classify_finds_the_class_anywhere_in_the_tags():
    assert evidence.classify(["phoebus", "evidence:measured", "x"]) == "measured"


def test_classify_is_case_and_whitespace_tolerant():
    assert evidence.classify(["  Evidence:Verified "]) == "verified"


def test_classify_ignores_unknown_classes():
    """An invented class must not pass as a real one.

    'evidence:probably' reads authoritative and means nothing; treating it as
    valid would let any word through the one check that exists.
    """
    assert evidence.classify(["evidence:probably"]) is None


def test_require_refuses_a_capture_with_no_evidence_class():
    with pytest.raises(ValueError) as exc:
        evidence.require("credentials", "phoebus")
    message = str(exc.value)
    assert "evidence:measured" in message
    assert "reads as a measurement forever" in message


def test_require_passes_tags_through_unchanged():
    tags = evidence.require("evidence:reported", "blade", "relay")
    assert tags == ["evidence:reported", "blade", "relay"]


def test_there_is_no_default_class():
    """Defaulting would label exactly the captures that thought least about it.

    A silent default is worse than no label at all, because it looks
    deliberate to the reader.
    """
    for attr in dir(evidence):
        assert "DEFAULT" not in attr.upper()


def test_verified_requires_a_different_method_not_a_repeat():
    """The distinction that the whole fleet failure turned on."""
    text = evidence.describe("verified")
    assert "different" in text.lower()
    assert "blind spot" in text.lower()


def test_every_class_is_documented():
    for name in evidence.CLASSES:
        assert len(evidence.describe(name)) > 40
