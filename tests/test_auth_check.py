"""Validating stored keys against their providers, without ever seeing one.

A vault tells you what you once had, not what still works. Choosing NouGenQ's
OpenRouter secret meant picking from fifteen stored keys and the first one tried
returned 401 — setting it blind would have shipped a dead key into an inference
path, where it surfaces as a user-facing failure rather than a config error.
"""
import json
import urllib.error

import pytest

from nougen_shards import auth_check as A


class _Resp:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _urlopen(status=200, error=None):
    def fake(req, timeout=None):
        if error is not None:
            raise error
        return _Resp(status)
    return fake


# --- the property that matters --------------------------------------------

def test_a_secret_never_appears_in_a_result(monkeypatch):
    """The whole contract: check it, report on it, never expose it."""
    monkeypatch.setattr(A.urllib.request, "urlopen", _urlopen(200))
    secret = "hf_thisIsALiveLookingSecretValue123456"
    r = A.check_key("HUGGINGFACE_API_KEY", secret)
    blob = json.dumps(r.__dict__)
    assert secret not in blob
    assert secret[8:] not in blob


def test_a_secret_never_appears_in_the_report(monkeypatch):
    monkeypatch.setattr(A.urllib.request, "urlopen", _urlopen(200))
    secret = "sk-or-v1-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    out = A.format_report(A.check_all({"OPENROUTER_API_KEY": secret}))
    assert secret not in out and "sk-or-v1" not in out


def test_the_fingerprint_is_stable_and_not_reversible():
    a = A.fingerprint("some-secret")
    assert a == A.fingerprint("some-secret")
    assert a != A.fingerprint("some-secre")
    assert len(a) == 12 and "some" not in a


def test_each_key_is_sent_only_to_its_own_provider(monkeypatch):
    """A checker that leaked a key to the wrong host would be worse than none."""
    seen = []
    def fake(req, timeout=None):
        seen.append(req.full_url)
        return _Resp(200)
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    A.check_key("ANTHROPIC_API_KEY", "sk-ant-api03-x")
    assert seen == ["https://api.anthropic.com/v1/models"]


# --- verdicts -------------------------------------------------------------

@pytest.mark.parametrize("code", [401, 403])
def test_a_rejected_key_is_dead(monkeypatch, code):
    err = urllib.error.HTTPError("u", code, "no", {}, None)
    monkeypatch.setattr(A.urllib.request, "urlopen", _urlopen(error=err))
    assert A.check_key("OPENAI_API_KEY", "sk-x").status == A.DEAD


def test_rate_limited_is_live_not_dead(monkeypatch):
    """429 means the key was RECOGNISED and throttled. Calling that dead would
    send someone rotating a credential that works."""
    err = urllib.error.HTTPError("u", 429, "slow down", {}, None)
    monkeypatch.setattr(A.urllib.request, "urlopen", _urlopen(error=err))
    r = A.check_key("OPENROUTER_API_KEY", "sk-or-v1-x")
    assert r.status == A.LIVE and "429" in r.detail


@pytest.mark.parametrize("code", [500, 502, 503])
def test_a_provider_outage_is_unknown_not_dead(monkeypatch, code):
    err = urllib.error.HTTPError("u", code, "boom", {}, None)
    monkeypatch.setattr(A.urllib.request, "urlopen", _urlopen(error=err))
    assert A.check_key("OPENAI_API_KEY", "sk-x").status == A.UNKNOWN


def test_no_network_is_unknown_not_dead(monkeypatch):
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        _urlopen(error=urllib.error.URLError("offline")))
    r = A.check_key("GOOGLE_API_KEY", "AIzaX")
    assert r.status == A.UNKNOWN and not r.actionable


def test_an_empty_stored_value_is_dead_without_a_request(monkeypatch):
    called = []
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        lambda *a, **k: called.append(1) or _Resp(200))
    assert A.check_key("OPENAI_API_KEY", "   ").status == A.DEAD
    assert called == [], "an empty value must not be sent anywhere"


def test_a_key_with_no_probe_is_not_reported_as_dead(monkeypatch):
    r = A.check_key("NGS_CLOUD_CREDENTIALS", "url,token")
    assert r.status == A.NO_PROBE and not r.actionable


# --- only DEAD is actionable ----------------------------------------------

def test_only_dead_keys_are_actionable():
    assert A.Result("k", "l", A.DEAD, "", "f").actionable
    for status in (A.LIVE, A.UNKNOWN, A.NO_PROBE):
        assert not A.Result("k", "l", status, "", "f").actionable


def test_dead_keys_sort_first(monkeypatch):
    def fake(req, timeout=None):
        if "openai" in req.full_url:
            raise urllib.error.HTTPError("u", 401, "no", {}, None)
        return _Resp(200)
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    results = A.check_all({"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "b",
                           "HUGGINGFACE_API_KEY": "c"})
    assert results[0].status == A.DEAD


def test_an_empty_vault_is_not_an_error():
    assert A.check_all({}) == []
    assert "No keys" in A.format_report([])


def test_the_report_distinguishes_unverified_from_dead(monkeypatch):
    def fake(req, timeout=None):
        if "openai" in req.full_url:
            raise urllib.error.HTTPError("u", 401, "no", {}, None)
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(A.urllib.request, "urlopen", fake)
    out = A.format_report(A.check_all({"OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b"}))
    assert "1 dead" in out and "1 unverified" in out
    assert "Unverified is not dead" in out


def test_json_output_is_machine_readable(monkeypatch):
    monkeypatch.setattr(A.urllib.request, "urlopen", _urlopen(200))
    parsed = json.loads(A.format_report(A.check_all({"OPENAI_API_KEY": "x"}), as_json=True))
    assert parsed[0]["status"] == A.LIVE and "fingerprint" in parsed[0]


def test_every_probe_targets_https():
    for key, probe in A.PROBES.items():
        assert probe.url.startswith("https://"), f"{key} probe is not TLS"
