"""arxiv_radar must run against the real radar API, and preview must not write.

2026-10-01: the ChatGPT lane called arxiv_radar(channels=["cs.AR"], mode="preview",
limit=5, commit=False) and got "module 'arxiv_rss_radar' has no attribute
'run_radar_cycle'". The wrapper called a function the radar never had, and
`load_route_recipe()` takes no argument. tests/test_mcp_arxiv_radar.py mocks
run_arxiv_radar itself, so nothing ever touched the real module and the drift
went unseen. These tests stand in a module with the radar's REAL function names
and signatures, make every mutating function explode, and add a contract check
against the real nougen-radar checkout when one is present.
"""
import json
import types

import pytest

from nougen_shards import arxiv_radar as wrapper

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>cs.AR updates</title><pubDate>Thu, 01 Oct 2026 00:00:00 -0400</pubDate>
<item><title>Alpha accelerator for agent memory</title><link>https://arxiv.org/abs/2609.00001</link></item>
<item><title>Beta cache hierarchy</title><link>https://arxiv.org/abs/2609.00002</link></item>
<item><title>Gamma interconnect</title><link>https://arxiv.org/abs/2609.00003</link></item>
<item><title>Delta scheduler</title><link>https://arxiv.org/abs/2609.00004</link></item>
</channel></rss>"""


def _explode(name):
    def boom(*_a, **_k):
        raise AssertionError(f"preview must not call {name}")
    return boom


def make_radar(calls):
    """A radar stand-in with the real module's names and signatures."""
    ns = types.SimpleNamespace()

    def fetch_arxiv_rss_conditional(channel="cs", cursor=None):
        calls.append(("fetch", channel, cursor))
        return RSS, {"status": 200}

    def parse_arxiv_item(item):
        title = item.find("title").text
        return {"id": item.find("link").text.rsplit("/", 1)[-1], "title": title,
                "primary_category": "cs.AR", "authors": ["A"], "abstract": title}

    def compute_percentiles(papers):
        return [dict(p, priority_pct=round(99.9 - i, 1), reason_codes=["usable_artifact"])
                for i, p in enumerate(papers)]

    def route_papers(papers, recipe):
        return {"beacon": papers[:1], "review": papers[1:3], "shard": papers[3:]}

    def load_route_recipe():
        return {"lanes": {"beacon": {"min_percentile": 99.5}}}

    def run_pipeline(mode="reconcile", channels=None, broadcast_target="all"):
        print("📊 Processing 4 papers ...")          # the real one prints; stdout must not leak
        calls.append(("run_pipeline", mode, channels, broadcast_target))
        return {"status": "ok", "papers_count": 4}

    for fn in (fetch_arxiv_rss_conditional, parse_arxiv_item, compute_percentiles,
               route_papers, load_route_recipe, run_pipeline):
        setattr(ns, fn.__name__, fn)
    for name in ("save_cursor", "ingest_lane_to_substrate", "broadcast_beacon", "load_cursor"):
        setattr(ns, name, _explode(name))
    return ns


@pytest.fixture
def radar(monkeypatch):
    calls = []
    ns = make_radar(calls)
    monkeypatch.setattr(wrapper, "get_radar_tools", lambda: {"radar": ns, "root": "x"})
    return ns, calls


# --- read-only preview -------------------------------------------------------

def test_preview_runs_against_the_real_api_and_writes_nothing(radar):
    _ns, calls = radar
    res = wrapper.run_arxiv_radar(channels=["cs.AR"], mode="preview", limit=5, commit=False)
    assert res["status"] == "success", res
    assert res["mutated"] is False and res["mode"] == "preview"
    assert [c[0] for c in calls] == ["fetch"]                    # no run_pipeline, no cursor/ingest/broadcast
    assert calls[0][2] in ({}, None)                              # empty cursor: full fetch, nothing persisted
    lanes = res["result"]["lanes"]
    assert {k: v["count"] for k, v in lanes.items()} == {"beacon": 1, "review": 2, "shard": 1}
    assert lanes["beacon"]["top"][0]["title"] == "Alpha accelerator for agent memory"
    assert lanes["beacon"]["top"][0]["reason_codes"] == ["usable_artifact"]
    assert res["result"]["papers_count"] == 4


def test_preview_limit_caps_each_lane(radar):
    res = wrapper.run_arxiv_radar(channels=["cs.AR"], mode="preview", limit=1, commit=False)
    assert all(len(v["top"]) <= 1 for v in res["result"]["lanes"].values())


def test_sweep_without_commit_is_a_preview_not_a_write(radar):
    _ns, calls = radar
    res = wrapper.run_arxiv_radar(channels=["cs.AR"], mode="sweep", commit=False)
    assert res["status"] == "success" and res["mutated"] is False
    assert "commit=true" in res["note"]
    assert all(c[0] != "run_pipeline" for c in calls)


def test_default_call_is_read_only(radar):
    _ns, calls = radar
    res = wrapper.run_arxiv_radar()
    assert res["status"] == "success" and res["mutated"] is False
    assert calls[0][:2] == ("fetch", "cs")


def test_a_failing_channel_is_reported_not_raised(radar, monkeypatch):
    ns, _calls = radar

    def fetch(channel="cs", cursor=None):
        raise OSError("network down")
    ns.fetch_arxiv_rss_conditional = fetch
    res = wrapper.run_arxiv_radar(channels=["cs.AR"], mode="preview")
    assert res["status"] == "error"
    assert "network down" in res["result"]["errors"]["cs.AR"]
    assert res["mutated"] is False


# --- commit path -------------------------------------------------------------

def test_commit_runs_the_pipeline_without_fleet_broadcast_and_keeps_stdout_clean(radar, capsys):
    _ns, calls = radar
    res = wrapper.run_arxiv_radar(channels=["cs.AR"], mode="sweep", commit=True)
    assert res["status"] == "success" and res["mutated"] is True
    assert ("run_pipeline", "sweep", ["cs.AR"], "local") in calls
    assert capsys.readouterr().out == ""                          # a print here would corrupt an MCP stdio stream
    assert "Processing 4 papers" in res["log_tail"]


def test_commit_requires_a_cadence_mode(radar):
    res = wrapper.run_arxiv_radar(mode="preview", commit=True)
    assert res["status"] == "error" and "sweep" in res["error"]


def test_custom_recipe_is_preview_only(radar, tmp_path, monkeypatch):
    monkeypatch.setattr(wrapper, "allowed_recipe_dirs", lambda _r=None: [tmp_path])
    recipe = tmp_path / "route-v1.json"
    recipe.write_text(json.dumps({"lanes": {"beacon": {"min_percentile": 90}}}), encoding="utf-8")
    res = wrapper.run_arxiv_radar(mode="sweep", commit=True, recipe_path=str(recipe))
    assert res["status"] == "error" and "preview" in res["error"]


# --- validation --------------------------------------------------------------

@pytest.mark.parametrize("bad", ["cs/../etc", "cs.AR?x=1", "http://evil", "", "cs AR", "1cs", "cs.AR.extra"])
def test_channel_names_cannot_inject_into_the_feed_url(radar, bad):
    res = wrapper.run_arxiv_radar(channels=[bad])
    assert res["status"] == "error" and "channel" in res["error"]


def test_too_many_channels_and_bad_limits_and_modes(radar):
    assert wrapper.run_arxiv_radar(channels=["cs"] * (wrapper.MAX_CHANNELS + 1))["status"] == "error"
    assert wrapper.run_arxiv_radar(limit=0)["status"] == "error"
    assert wrapper.run_arxiv_radar(limit=wrapper.MAX_LIMIT + 1)["status"] == "error"
    assert wrapper.run_arxiv_radar(limit=True)["status"] == "error"
    assert wrapper.run_arxiv_radar(mode="nuke")["status"] == "error"


def test_recipe_path_outside_the_radar_dirs_is_refused(radar, tmp_path, monkeypatch):
    monkeypatch.setattr(wrapper, "allowed_recipe_dirs", lambda _r=None: [tmp_path / "ok"])
    secret = tmp_path / "secret.json"
    secret.write_text('{"lanes": {"leak": "TOPSECRET"}}', encoding="utf-8")
    res = wrapper.run_arxiv_radar(mode="preview", recipe_path=str(secret))
    assert res["status"] == "error" and "TOPSECRET" not in json.dumps(res)


def test_recipe_inside_the_radar_dirs_is_used(radar, tmp_path, monkeypatch):
    monkeypatch.setattr(wrapper, "allowed_recipe_dirs", lambda _r=None: [tmp_path])
    recipe = tmp_path / "route-v1.json"
    recipe.write_text(json.dumps({"lanes": {"beacon": {"min_percentile": 50}}}), encoding="utf-8")
    seen = []
    ns, _ = radar
    ns.route_papers = lambda papers, rc: seen.append(rc) or {"beacon": [], "review": [], "shard": papers}
    res = wrapper.run_arxiv_radar(mode="preview", recipe_path=str(recipe))
    assert res["status"] == "success" and seen[0]["lanes"]["beacon"]["min_percentile"] == 50


# --- drift guard -------------------------------------------------------------

def test_a_radar_missing_a_function_degrades_with_the_names(monkeypatch):
    ns = make_radar([])
    del ns.run_pipeline
    del ns.route_papers
    monkeypatch.setattr(wrapper, "get_radar_tools", lambda: {"radar": ns, "root": "x"})
    res = wrapper.run_arxiv_radar(mode="preview")
    assert res["status"] == "degraded" and res["available"] is True
    assert "run_pipeline" in " ".join(res["missing_symbols"]) and "route_papers" in " ".join(res["missing_symbols"])


def test_a_renamed_parameter_is_caught(monkeypatch):
    ns = make_radar([])
    ns.run_pipeline = lambda mode="reconcile", channel_list=None, target="all": {}
    monkeypatch.setattr(wrapper, "get_radar_tools", lambda: {"radar": ns, "root": "x"})
    res = wrapper.run_arxiv_radar(mode="preview")
    assert res["status"] == "degraded"
    assert any("channels" in p for p in res["missing_symbols"])


def test_the_symbol_the_old_wrapper_invented_is_not_required():
    ns = make_radar([])
    assert not hasattr(ns, "run_radar_cycle")
    assert wrapper.radar_contract_problems(ns) == []


def test_real_radar_checkout_satisfies_the_contract():
    """Catches drift in a dev environment; skipped where nougen-radar is not installed (CI)."""
    root = wrapper.find_radar_root()
    if root is None:
        pytest.skip("nougen-radar repository not installed in environment (expected in CI runner)")
    tools = wrapper.get_radar_tools()
    assert wrapper.radar_contract_problems(tools["radar"]) == []


# --- the MCP tool passes the new parameters through ----------------------------

def test_mcp_tool_accepts_and_forwards_the_chatgpt_call_shape(monkeypatch):
    from nougen_shards import mcp
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return {"status": "success", "mutated": False}
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_arxiv_radar", fake)
    out = json.loads(mcp.arxiv_radar(channels=["cs.AR"], mode="preview", limit=5, commit=False))
    assert out["status"] == "success"
    assert seen == {"channels": ["cs.AR"], "mode": "preview", "limit": 5, "commit": False, "recipe_path": None}


def test_mcp_tool_default_is_a_read_only_preview(monkeypatch):
    from nougen_shards import mcp
    seen = {}
    monkeypatch.setattr("nougen_shards.arxiv_radar.run_arxiv_radar", lambda **kw: seen.update(kw) or {"status": "success"})
    mcp.arxiv_radar()
    assert seen["mode"] == "preview" and seen["commit"] is False
