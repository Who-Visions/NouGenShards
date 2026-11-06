"""Distillation sidecar + the four retrieval moves wired through core:
atoms lane, graph lane, scenes/persona/layered read, scope + bi-temporal
filters, knapsack + delta packet. The model is a fake; everything else is real."""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards import core, distill  # noqa: E402


@pytest.fixture()
def vault(monkeypatch):
    d = Path(tempfile.mkdtemp())
    monkeypatch.setattr(core, "GLOBAL_DIR", d)
    monkeypatch.setattr(core, "get_db_path", lambda i: d / f"test_shards_{i}.db")
    monkeypatch.setenv("NOUGEN_EMBED_AT_CAPTURE", "0")
    monkeypatch.setenv("NOUGEN_QUERY_EMBED", "0")
    monkeypatch.delenv("NOUGEN_DISTILL_LANES", raising=False)
    core._INITIALIZED_DBS.clear()
    yield d
    core._INITIALIZED_DBS.clear()
    shutil.rmtree(d, ignore_errors=True)


def fake_llm(prompt, schema):
    if schema:
        if "Kestrel" in prompt:
            return json.dumps({
                "atoms": [{"type": "fact", "text": "The Kestrel relay runs on the WhoArt machine"},
                          {"type": "decision", "text": "Operator chose zephyrine caching for Kestrel"}],
                "entities": [{"name": "Kestrel", "kind": "project"}, {"name": "WhoArt", "kind": "machine"}],
                "relations": [{"src": "Kestrel", "rel": "runs on", "dst": "WhoArt"}]})
        return json.dumps({"atoms": [{"type": "fact", "text": "WhoArt hosts the local lane"}],
                           "entities": [{"name": "WhoArt", "kind": "machine"}], "relations": []})
    if prompt.startswith("Write a compact profile"):
        return "- builds a memory fleet"
    name = prompt.split("knows about ")[1].split(" (")[0]
    return f"{name} hosts the local lane and the relay"


def cap(title, content, tags=None, **kw):
    assert core.capture("KNOWLEDGE", title, content, tags=tags or ["via:claude-app/tester"], **kw) is not False
    for i in range(1, core.MAX_DB_COUNT + 1):
        p = core.get_db_path(i)
        if p.exists():
            row = core.get_connection(i).execute("SELECT id FROM shards WHERE title=?", (title,)).fetchone()
            if row:
                return distill.shard_key(i, row[0])
    raise AssertionError(f"captured shard {title!r} not found")


def test_scope_from_tags_is_deterministic():
    s = distill.scope_from_tags(["via:claude-app/g-whoentertains", "machine:blade"], "nougen")
    assert s == {"agent": "claude-app", "user": "g-whoentertains", "machine": "blade", "project": "nougen"}
    assert distill.scope_from_tags('["machine:whoart"]')["machine"] == "whoart"


def test_atoms_lane_finds_meaning_the_body_never_says(vault):
    a = cap("Relay notes", "Kestrel relay deployment details and rollout order for the fleet")
    conn = distill.connect()
    assert distill.distill_shard(conn, a, fake_llm) == "done"
    assert distill.distill_shard(conn, a, fake_llm) == "skip"
    hits = distill.atoms_lane("zephyrine caching", conn=conn)
    assert [f"{h['id']}@{h['_db_index']}" for h in hits] == [a]


def test_graph_lane_walks_one_hop(vault):
    a = cap("Relay notes", "Kestrel relay deployment details and rollout order for the fleet")
    b = cap("Box notes", "The workstation serves the resident gemma lane for the fleet")
    conn = distill.connect()
    distill.distill_shard(conn, a, fake_llm)
    distill.distill_shard(conn, b, fake_llm)
    keys = [f"{h['id']}@{h['_db_index']}" for h in distill.graph_lane("what is kestrel", conn=conn)]
    assert keys[0] == a and b in keys  # b reached through the Kestrel -runs_on-> WhoArt edge


def test_retrieve_fuses_atoms_lane_and_can_turn_it_off(vault, monkeypatch):
    a = cap("Relay notes", "Kestrel relay deployment details and rollout order for the fleet")
    distill.distill_shard(distill.connect(), a, fake_llm)
    found = [f"{r['id']}@{r['_db_index']}" for r in core.retrieve("zephyrine", limit=3, domain_key="*")]
    assert a in found
    monkeypatch.setenv("NOUGEN_DISTILL_LANES", "0")
    off = [f"{r['id']}@{r['_db_index']}" for r in core.retrieve("zephyrine", limit=3, domain_key="*")]
    assert a not in off


def test_scenes_persona_and_layered_read(vault):
    conn = distill.connect()
    for n in range(3):
        distill.distill_shard(conn, cap(f"Box note {n}", f"workstation note number {n} about the fleet lane"), fake_llm)
    assert distill.build_scenes(conn, fake_llm, min_shards=2) >= 1
    assert distill.build_persona(conn, fake_llm) == "- builds a memory fleet"
    assert conn.execute("SELECT scope FROM persona").fetchone()[0] == "tester"  # owner derived from tags
    ctx = distill.layered_context("WhoArt", lambda q, **kw: core.retrieve(q, limit=3, domain_key="*"), conn=conn)
    assert "L3 PERSONA (tester)" in ctx and "L2 SCENE: WhoArt" in ctx and "L1 ATOMS" in ctx
    assert distill.stats(conn)["scenes"] >= 1


def test_bitemporal_learned_and_event_filters(vault):
    cap("Old event", "harbourmaster ledger entry recorded late", original_timestamp="2020-05-01T00:00:00Z")
    row = next(core.get_connection(i).execute("SELECT learned_utc, timestamp FROM shards WHERE title='Old event'").fetchone()
               for i in range(1, core.MAX_DB_COUNT + 1)
               if core.get_db_path(i).exists() and core.get_connection(i).execute(
                   "SELECT 1 FROM shards WHERE title='Old event'").fetchone())
    assert row[0] and row[0] > row[1]  # learned now, happened in 2020

    def titles(**kw):
        return [r["title"] for r in core.retrieve("harbourmaster", limit=3, domain_key="*", **kw)]
    assert titles(as_of="2999-01-01") == ["Old event"]
    assert titles(as_of="2021-01-01") == []          # the vault did not know it yet in 2021
    assert titles(event_before="2021-01-01") == ["Old event"]
    assert titles(event_after="2021-01-01") == []


def test_scope_filter_uses_tags(vault):
    cap("Blade box", "quartermaster inventory list", tags=["via:claude-app/tester", "machine:blade"])
    cap("Art box", "quartermaster inventory list too", tags=["via:codex/tester", "machine:whoart"])
    got = [r["title"] for r in core.retrieve("quartermaster", limit=5, domain_key="*", scope={"machine": "blade"})]
    assert got == ["Blade box"]
    got = [r["title"] for r in core.retrieve("quartermaster", limit=5, domain_key="*", scope={"agent": "codex"})]
    assert got == ["Art box"]


def test_knapsack_packs_by_value_per_token_and_holds_sent():
    shards = [{"id": 1, "_db_index": 1, "title": "big", "content": "x" * 4000, "final_score": 0.9},
              {"id": 2, "_db_index": 1, "title": "small", "content": "y" * 200, "final_score": 0.8},
              {"id": 3, "_db_index": 1, "title": "held", "content": "z" * 200, "final_score": 0.7}]
    sent = []
    pkt = core.compile_recall_packet(shards, token_budget=300, strategy="knapsack", held={"3@1"}, included=sent)
    assert "[HELD] #3" in pkt and "RECORD #2" in pkt and "RECORD #1" not in pkt
    assert sent == ["2@1"] and "[BUDGET] 1" in pkt


def test_loose_relation_endpoints_become_entities_and_filenames_do_not(vault):
    a = cap("Paper notes", "notes on a paper about probes and interfaces for the fleet")

    def loose(prompt, schema):
        return json.dumps({"atoms": [{"type": "fact", "text": "LLMs hide answers from their interface"}],
                           "entities": [{"name": "Large language models", "kind": "concept"},
                                        {"name": "arxiv_cs_AI_2026_paper_notes.md", "kind": "concept"}],
                           "relations": [{"src": "LLMs", "rel": "hides from", "dst": "verbal interface"}]})
    conn = distill.connect()
    distill.distill_shard(conn, a, loose)
    names = {r[0] for r in conn.execute("SELECT norm FROM entities")}
    assert {"llms", "verbal interface", "large language models"} <= names
    assert not any(n.endswith(".md") for n in names)
    assert conn.execute("SELECT rel FROM edges").fetchone()[0] == "hides_from"


def test_sent_roundtrip(vault):
    distill.mark_sent("s1", ["1@1", "2@3"])
    assert distill.held_keys("s1") == {"1@1", "2@3"}
    assert distill.held_keys("other") == set()


def test_distill_structured_shard_for_twitch_and_stream_session(vault):
    twitch_body = (
        "SOURCE: https://dev.twitch.tv/docs/api/reference/#start-commercial\n"
        "ENDPOINT: POST https://api.twitch.tv/helix/channels/commercial\n"
        "SCOPES: channel:edit:commercial\n\n"
        "Start Commercial\n\n"
        "Starts a commercial on the specified channel.\n\n"
        "NOTE : Only partners and affiliates may run commercials and they must be streaming live at the time.\n"
    )
    tk = cap("Twitch Helix API: Start Commercial (POST /channels/commercial)", twitch_body,
             tags=["twitch", "twitch-api", "helix", "nougenstream"], domain_key="NouGenQtApp")
    session_body = (
        "# NouGenStream session 2026-11-06 01:00 (45 min)\n\n"
        "| | |\n|---|---|\n"
        "| Start / end (UTC) | 2026-11-06T06:00:00Z / 2026-11-06T06:45:00Z |\n"
        "| Duration | 45.0 min |\n"
        "| Peak viewers | 12 |\n"
        "| Frames encoded (live) | 81000 |\n"
        "| Average capture fps | 30.0 |\n"
        "| Encoder | h264_nvenc |\n"
        "| Recorded | yes |\n"
        "| Phone camera used | yes |\n\n"
        "## Network and governor\n"
        "Viewer backlog drops: 0. Lowest live bitrate: 3500 kbps. Lowest resolution: 100%.\n"
        "Policy decisions: 8 allowed, 1 queued for approval, 1 approved, 0 rejected, 0 denied.\n"
        "Privacy mask: on 2 time(s), 14 s total (triggers not recorded).\n\n"
        "## Resident AI\n"
        "Model: Yukiai:e2b. Tool calls: 5. Directed instructions: 2."
    )
    sk = cap("NouGenStream session 2026-11-06 01:00 (45m)", session_body,
             tags=["nougenstream", "session-summary", "stream-audit"], domain_key="stream:nougenstream")
    conn = distill.connect()
    assert distill.distill_structured_shard(conn, tk) == "done"
    assert distill.distill_structured_shard(conn, tk) == "skip"
    assert distill.distill_structured_shard(conn, sk) == "done"

    twitch_hits = [f"{h['id']}@{h['_db_index']}" for h in distill.atoms_lane("channel:edit:commercial commercial", conn=conn)]
    assert tk in twitch_hits
    session_hits = [f"{h['id']}@{h['_db_index']}" for h in distill.atoms_lane("h264_nvenc privacy mask", conn=conn)]
    assert sk in session_hits
    graph_hits = [f"{h['id']}@{h['_db_index']}" for h in distill.graph_lane("what uses NouGenStream", conn=conn)]
    assert tk in graph_hits and sk in graph_hits

    asset_body = (
        "# NouGenStream Premium Visual Asset Kit\n"
        "Palette: Purple Obsidian (#07050b void, #120b1c glass, #7b3fe4 accent, #e9e0ff text).\n"
        "- `assets/premium/icons/nougenstream-icon.svg`: Clean vector master (256x256 viewBox)\n"
        "- `assets/premium/overlays/privacy-mode.png`: 1920x1080 RGBA privacy shield overlay\n"
    )
    ak = cap("NouGenStream Premium Visual Asset Kit (argon/assets)", asset_body,
             tags=["nougenstream", "visual-pack", "assets"], domain_key="stream:nougenstream")
    assert distill.distill_structured_shard(conn, ak) == "done"
    asset_hits = [f"{h['id']}@{h['_db_index']}" for h in distill.atoms_lane("7b3fe4 privacy-mode.png", conn=conn)]
    assert ak in asset_hits


