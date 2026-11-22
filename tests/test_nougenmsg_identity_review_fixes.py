"""Review fixes on #1190: registry keys, untitled matches, non-finite times."""
import json

from nougen_shards import nougenmsg as m


def _no_stores(monkeypatch):
    monkeypatch.setattr(m, "_discover_session_stores", lambda: [])
    monkeypatch.setattr(m, "_tenant_scope", lambda: False)
    monkeypatch.delenv("NOUGEN_SESSION_TITLE", raising=False)


def test_registry_keyed_by_session_id_is_found(tmp_path, monkeypatch):
    _no_stores(monkeypatch)
    reg = tmp_path / "cc.json"
    reg.write_text(json.dumps({"sessions": {"sid-abc": {"title": "Known title"}}}))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(reg))
    assert m.resolve_session_title("sid-abc") == "Known title"


def test_title_discovery_continues_past_untitled_match(tmp_path, monkeypatch):
    _no_stores(monkeypatch)
    monkeypatch.setattr(m, "_discover_session_stores", lambda: ["s"])
    monkeypatch.setattr(m, "_iter_store_records",
                        lambda store: iter([({"session_id": "sid-x"}, "p1")]))
    reg = tmp_path / "cc.json"
    reg.write_text(json.dumps({"sid-x": {"name": "Later title"}}))
    monkeypatch.setenv("NOUGEN_CC_SESSIONS", str(reg))
    assert m.resolve_session_title("sid-x") == "Later title"


def test_non_finite_start_times_are_rejected():
    for bad in ("nan", "inf", "-inf", float("nan"), float("inf"), 10 ** 400, "1e400", True):
        assert m._parse_time(bad) is None
        assert m.format_session_age(bad) == ""
