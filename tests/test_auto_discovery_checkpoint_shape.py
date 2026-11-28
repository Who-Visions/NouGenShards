"""EvidenceLedger.load_checkpoint skips unreadable entries instead of aborting the load."""

import json

import pytest

from nougen_shards.auto_discovery import CapabilityDomain, EvidenceLedger


def _entry(key, domain="runtime"):
    return {
        "entry_id": f"{domain}:{key}",
        "domain": domain,
        "key": key,
        "value": {"v": key},
        "confidence": 0.9,
        "fingerprint": "fp-" + key,
        "source": "test",
        "discovered_utc": "2026-11-28T00:00:00+00:00",
        "ttl_seconds": 0,  # never expires, so get() reflects the load alone
    }


def _missing_field():
    e = _entry("broken")
    del e["fingerprint"]
    return e


BAD_ENTRIES = [
    _entry("future", domain="gpu"),  # domain added by a newer node
    _missing_field(),
    "not-an-object",
    None,
    ["a", "list"],
]


@pytest.mark.parametrize("bad", BAD_ENTRIES, ids=lambda b: type(b).__name__ + ":" + str(b)[:20])
def test_bad_entry_does_not_drop_later_entries(tmp_path, bad):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps({"version": "1.0", "entries": [_entry("a"), bad, _entry("b")]}))

    ledger = EvidenceLedger(checkpoint_path=ckpt)
    assert ledger.load_checkpoint() == 2
    assert ledger.get("runtime:a") is not None
    assert ledger.get("runtime:b") is not None
    assert ledger.get("runtime:b").domain is CapabilityDomain.RUNTIME


@pytest.mark.parametrize("payload", [[], "x", 3, {"entries": "nope"}, {"entries": None}, {}])
def test_wrong_shape_checkpoint_loads_nothing(tmp_path, payload):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text(json.dumps(payload))
    assert EvidenceLedger(checkpoint_path=ckpt).load_checkpoint() == 0


def test_corrupt_json_loads_nothing(tmp_path):
    ckpt = tmp_path / "ckpt.json"
    ckpt.write_text("{not json")
    assert EvidenceLedger(checkpoint_path=ckpt).load_checkpoint() == 0
