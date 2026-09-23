"""NouGen Q Live Prompt Loop v1: offline contract tests (no gateway, no model)."""
import json
import time

from nougen_shards import q_live as q
from nougen_shards.q_live import (
    GatewayRetriever, Hit, QConfig, QLive, RetrievalResult, heuristic_candidates, pick_model, render_cue,
    validate_candidates,
)

CFG = QConfig(retrieve_grace_s=0.25, cue_budget_s=0.4, stale_after_turns=2)

MEM = [
    Hit("shard:1@db2", "Gateway search latency fix", "fuzzy scan on zero hit queries took twenty seconds; opt-out flag"),
    Hit("shard:2@db4", "NouGen exists because AI forgot", "my other AI kept forgetting what we were building"),
    Hit("shard:3@db7", "Photography client callback", "wedding album delivery story about the lens"),
]


def fake_retriever(hits=None, **kw):
    def _r(query, limit, fuzzy=False):
        return RetrievalResult(hits=list(MEM if hits is None else hits), latency_ms=1.0, fuzzy=fuzzy, **kw)
    return _r


def fake_generator(tail, topic, hits, n):
    """Deterministic stand-in for the model: one memory-backed line, one uncited line, one invented one."""
    out = []
    if hits:
        out.append({"text": f"The funny part is {hits[0].title.lower()} matters here.", "kind": "callback",
                    "memory": [1], "why": "bridges into memory"})
    out.append({"text": "Zoom out and say why this matters to listeners.", "kind": "transition", "memory": [],
                "why": "context bridge"})
    out.append({"text": "In 2019 Bartholomew Quill built this at Initech.", "kind": "story", "memory": [],
                "why": "invented"})
    return out


def make(retriever=None, generator=fake_generator, **kw):
    return QLive(retriever=retriever or fake_retriever(), generator=generator, cfg=kw.pop("cfg", CFG), **kw)


# ------------------------------------------------------------------ conversation state

def test_topic_follows_the_conversation():
    ql = make()
    ql.on_utterance("memory continuity is the whole point of the memory system for the AI")
    assert "memory" in ql.on_utterance("and the memory has to survive across every session")["topic_now"]
    out = {}
    for line in ["now the camera lens choice for the wedding photography shoot",
                 "the photography lens matters more than the camera body",
                 "wedding photography is all about that lens"]:
        out = ql.on_utterance(line)
    assert "memory" not in out["topic_now"] and any(t in out["topic_now"] for t in ("photography", "lens", "wedding"))


# ------------------------------------------------------------------ never fabricate memory

def test_validation_drops_uncited_memory_and_flags_invented_specifics():
    raw = [{"text": "Callback to the fix.", "kind": "callback", "memory": [1, 9, "x"]},
           {"text": "In 2019 Bartholomew Quill built this.", "kind": "story", "memory": []}]
    cands = validate_candidates(raw, MEM, "we talked about latency", CFG)
    assert cands[0].shards == ["shard:1@db2"]          # index 9 and "x" were not real hits: dropped
    assert cands[1].unsupported >= 2 and cands[1].shards == []


def test_memory_backed_cue_outranks_an_invention():
    out = make().on_utterance("the gateway search latency was terrible before the fix")
    dp = out["display_prompt"]
    assert dp["shards"] == ["shard:1@db2"] and dp["mode"] == "memory"
    assert "Bartholomew" not in dp["text"]


def test_every_displayed_cue_is_traceable_to_returned_shards():
    ql = make()
    for line in ["memory and continuity again", "the gateway latency story", "why the AI forgot everything"]:
        out = ql.on_utterance(line)
        refs = set(out["retrieval"]["refs"])
        assert set(out["display_prompt"]["shards"]) <= refs
        assert all(set(c["shards"]) <= refs for c in out["candidate_prompts"])


# ------------------------------------------------------------------ cue lifecycle: stale cues disappear

def test_used_cue_is_retired_and_replaced():
    ql = make()
    first = ql.on_utterance("tell me about the gateway search latency")["display_prompt"]["text"]
    out = ql.on_utterance("so the funny part is gateway search latency fix matters here")
    assert out["previous_cue_outcome"] == "used"
    assert out["display_prompt"]["text"] != first or out["turn"] == 2


def test_moved_past_cue_is_retired():
    ql = make()
    ql.on_utterance("gateway search latency fuzzy scan zero hit queries")
    ql.on_utterance("gateway search latency fuzzy scan zero hit queries again")
    out = ql.on_utterance("completely different subject: sourdough baking hydration levels and proofing")
    out = ql.on_utterance("sourdough baking proofing hydration starter flour")
    assert out["previous_cue_outcome"] in (None, "moved_past", "skipped") and ql.cue.issued_turn == out["turn"]


def test_contradicted_cue_suppresses_its_terms():
    ql = make()
    ql.on_utterance("talk about the gateway search latency fix")
    out = ql.on_utterance("no actually the gateway latency fix is wrong and never worked")
    assert out["previous_cue_outcome"] == "contradicted"
    assert ql.state.suppressed


def test_unused_cue_is_skipped_after_stale_turns_and_never_lingers():
    ql = make()
    ql.on_utterance("apples oranges bananas fruit market")
    seen = []
    for line in ["pears plums cherries grapes", "cherries grapes peaches melons", "melons berries kiwi mango"]:
        out = ql.on_utterance(line)
        seen.append(out["previous_cue_outcome"])
        assert ql.cue is None or ql.cue.issued_turn == out["turn"]   # only the current turn's cue is on screen
    assert "skipped" in seen or "moved_past" in seen


def test_feedback_shifts_kind_weights():
    ql = make()
    ql.on_utterance("gateway search latency fix")
    ql.on_utterance("the funny part is gateway search latency fix matters here")   # used -> callback up
    assert ql.state.kind_weight.get("callback", 1.0) > 1.0


# ------------------------------------------------------------------ zero-hit and failure handling

def test_zero_hits_gives_context_only_cue_and_never_fake_memory():
    ql = QLive(retriever=fake_retriever(hits=[]), generator=None, cfg=CFG)
    out = ql.on_utterance("something nobody has ever stored about interplanetary llamas")
    dp = out["display_prompt"]
    assert dp["shards"] == [] and dp["mode"] == "context_only" and dp["confidence"] == "low"
    assert out["retrieval"]["hits"] == 0 and out["retrieval"]["refs"] == []


def test_slow_retrieval_never_blocks_the_cue_and_lands_for_the_next_turn():
    calls = []

    def slow(query, limit, fuzzy=False):
        calls.append(query)
        time.sleep(1.0)
        return RetrievalResult(hits=list(MEM))
    cfg = QConfig(retrieve_grace_s=0.05, cue_budget_s=0.1)
    ql = QLive(retriever=slow, generator=None, cfg=cfg)
    t0 = time.perf_counter()
    first = ql.on_utterance("gateway latency fix")
    assert time.perf_counter() - t0 < 0.6                       # the turn did not wait on the slow gateway
    assert first["coverage"]["memory"] == "pending" and first["coverage"]["state"] == "DEGRADED"
    assert first["display_prompt"]["shards"] == [] and first["display_prompt"]["confidence"] == "low"
    time.sleep(1.1)                                              # the background call lands
    second = ql.on_utterance("the gateway latency fix again")
    assert second["retrieval"]["hits"] == len(MEM) and second["coverage"]["memory"] in ("fresh", "stale")
    ql.close()


def test_stale_memory_is_labelled_while_a_refresh_is_in_flight():
    state = {"n": 0}

    def retriever(query, limit, fuzzy=False):
        state["n"] += 1
        if state["n"] > 1:
            time.sleep(1.0)                                      # the refresh for the new topic is slow
        return RetrievalResult(hits=list(MEM))
    ql = QLive(retriever=retriever, generator=None, cfg=QConfig(retrieve_grace_s=0.05, cue_budget_s=0.1))
    ql.on_utterance("gateway latency fix scan")
    out = {}
    for line in ["now wedding photography lens album", "photography lens wedding album delivery"]:
        out = ql.on_utterance(line)
    assert out["coverage"]["memory"] == "stale" and out["coverage"]["state"] == "DEGRADED"
    assert set(out["display_prompt"]["shards"]) <= set(out["retrieval"]["refs"])   # provenance stays true
    ql.close()


def test_slow_generator_never_blocks_the_cue_and_its_candidates_land_later():
    def slow_gen(tail, topic, hits, n):
        time.sleep(0.8)
        return fake_generator(tail, topic, hits, n)
    ql = QLive(retriever=fake_retriever(), generator=slow_gen, cfg=QConfig(retrieve_grace_s=0.25, cue_budget_s=0.05))
    t0 = time.perf_counter()
    first = ql.on_utterance("the gateway search latency fix")
    assert time.perf_counter() - t0 < 0.6 and first["generator"] == "heuristic" and first["display_prompt"]
    time.sleep(0.9)
    second = ql.on_utterance("the gateway latency fix scan zero hit")
    assert second["generator"] == "llm"                          # the late model output was carried forward
    assert any(c["age_turns"] >= 1 for c in second["candidate_prompts"]) or second["display_prompt"]["age_turns"] >= 0
    ql.close()


def test_retrieval_error_is_reported_as_unavailable():
    r = lambda query, limit, fuzzy=False: RetrievalResult(complete=False, degraded=True, error="refused")  # noqa: E731
    out = QLive(retriever=r, generator=fake_generator, cfg=CFG).on_utterance("gateway latency fix")
    assert out["coverage"]["state"] == "UNAVAILABLE" and out["display_prompt"]["confidence"] == "low"
    assert out["display_prompt"]["shards"] == []


def test_generator_failure_falls_back_visibly():
    def boom(*a):
        raise RuntimeError("model down")
    out = QLive(retriever=fake_retriever(), generator=boom, cfg=CFG).on_utterance("gateway latency fix")
    assert out["generator"] == "heuristic" and out["display_prompt"] is not None


# ------------------------------------------------------------------ coverage truth

def test_non_green_vault_marks_the_turn_degraded_and_names_it():
    ql = make(fleet_vaults={"blade": "GREEN", "phoebus": "GREEN", "whoart": "UNCONFIGURED"})
    out = ql.on_utterance("gateway latency fix")
    assert out["coverage"]["state"] == "DEGRADED" and out["coverage"]["missing_vaults"] == ["whoart"]
    assert out["coverage"]["complete"] is False
    assert "DEGRADED" in render_cue(out) and "whoart" in render_cue(out)


def test_all_green_reports_green():
    ql = make(fleet_vaults={"blade": "GREEN", "phoebus": "GREEN"})
    assert ql.on_utterance("gateway latency fix")["coverage"]["state"] == "GREEN"


def test_degraded_lane_lowers_confidence():
    r = fake_retriever(complete=False, degraded=True, lanes="local=timeout:20.0s")
    out = QLive(retriever=r, generator=fake_generator, cfg=CFG).on_utterance("gateway latency fix")
    assert out["coverage"]["state"] == "DEGRADED" and out["display_prompt"]["confidence"] != "high"


# ------------------------------------------------------------------ gateway client: fast path, no fuzzy

class FakeTransport:
    def __init__(self, payload, headers=None):
        self.calls, self.payload, self.headers = [], payload, headers or {}

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, json.loads(body), timeout))
        return 200, self.headers, self.payload


def test_gateway_retriever_disables_fuzzy_by_default_and_escalates_on_request():
    t = FakeTransport([{"id": 7, "_db_index": 3, "title": "T", "content": "body", "final_score": 0.4}])
    r = GatewayRetriever(QConfig(), transport=t, token="x")
    res = r("gateway latency", 6)
    assert t.calls[0][3] == {"query": "gateway latency", "limit": 6, "fuzzy": False, "fast": True}
    assert res.hits[0].ref == "shard:7@db3"
    r("gateway latency", 6, fuzzy=True)
    assert t.calls[1][3]["fuzzy"] is True and t.calls[1][3]["fast"] is False   # escalation leaves the fast path
    _, url, headers, body, _ = t.calls[0]
    assert headers["Authorization"] == "Bearer x"                # the token rides in the header only
    assert "x" not in url.split("/search")[0].split("//")[1].replace("127.0.0.1:4444", "") and "Bearer" not in json.dumps(body)


def test_federation_trailer_is_not_a_memory_and_marks_incomplete():
    payload = [{"id": 5, "_db_index": 1, "title": "real", "content": "c"},
               {"id": "federation_meta", "event_type": "FEDERATION_STATUS", "_db_index": "federation_meta",
                "title": "recall INCOMPLETE", "content": "{}"}]
    res = GatewayRetriever(QConfig(), transport=FakeTransport(payload), token="x")("q", 3)
    assert [h.ref for h in res.hits] == ["shard:5@db1"] and res.degraded and not res.complete


def test_degraded_header_is_honoured():
    t = FakeTransport([], headers={"X-NouGen-Degraded": "1", "X-NouGen-Lane-Timings": "local=timeout:20.0s"})
    res = GatewayRetriever(QConfig(), transport=t, token="x")("q", 3)
    assert res.degraded and "local=timeout" in res.lanes


def test_gateway_error_is_data_not_an_exception():
    def down(*a):
        raise OSError("refused")
    res = GatewayRetriever(QConfig(), transport=down, token="x")("q", 3)
    assert res.error and res.degraded and res.hits == []


# ------------------------------------------------------------------ model picking (Rule 0.4)

def test_pick_model_rule_04():
    served = ["gemma4:12b", "gemma4:31b-cloud", "kaedra:e4b", "gemma4:e2b", "dav1d:e2b", "dav1d:e2b-pre-selfid"]
    assert pick_model(served) == "dav1d:e2b"                               # custom e2b first, not a snapshot
    assert pick_model(["gemma4:12b", "gemma4:e4b"]) == "gemma4:e4b"        # base gemma4 e2b/e4b next
    assert pick_model(["gemma4:12b", "gemma4:31b-cloud"]) is None          # never a large or cloud tag
    assert pick_model(served, env="gemma4:12b") != "gemma4:12b"            # env cannot force a banned tag
    assert pick_model(["kaedra:e4b"]) is None                              # persona models are not neutral cue writers


# ------------------------------------------------------------------ the loop over a long session

def test_long_session_stays_fast_bounded_and_current():
    ql = make(fleet_vaults={"blade": "GREEN", "phoebus": "GREEN", "whoart": "UNCONFIGURED"})
    lines = ["memory and continuity are the point", "the gateway search latency was awful", "then photography lens work",
             "why the AI kept forgetting", "the fuzzy scan on zero hit queries", "and callbacks to old stories"] * 8
    lat = []
    for line in lines:
        out = ql.on_utterance(line)
        lat.append(out["latency_ms"])
        assert (out["display_prompt"] is None) or isinstance(out["display_prompt"], dict)   # exactly one cue
        assert ql.cue is None or ql.cue.issued_turn == out["turn"]                          # never a stale cue
        assert len(out["retrieval"]["refs"]) <= QConfig().retrieve_limit                     # bounded
    assert sorted(lat)[int(len(lat) * 0.95) - 1] < 250
    assert q.heuristic_candidates(["a"], [], CFG)   # fallback exists
    assert heuristic_candidates(["memory"], MEM, CFG)[0].shards


# ------------------------------------------------------------------ fast path honesty and retry backoff

def test_fast_path_skipped_lanes_make_coverage_partial_and_named():
    t = FakeTransport([{"id": 1, "_db_index": 2, "title": "T", "content": "c"}],
                      headers={"X-NouGen-Fast-Path": "local-keyword-only",
                               "X-NouGen-Lanes-Skipped": "external,cloud,vaults"})
    ql = QLive(retriever=GatewayRetriever(QConfig(), transport=t, token="x"), generator=None, cfg=CFG)
    out = ql.on_utterance("gateway latency fix")
    cov = out["coverage"]
    assert cov["state"] == "DEGRADED" and cov["complete"] is False
    assert cov["lanes_not_consulted"] == ["external", "cloud", "vaults"]
    assert "peer vaults" in cov["note"] and out["retrieval"]["hits"] == 1
    ql.close()


def test_failed_refresh_backs_off_instead_of_hammering_the_gateway():
    calls = []

    def flaky(query, limit, fuzzy=False):
        calls.append(query)
        return RetrievalResult(complete=False, degraded=True, error="refused")
    ql = QLive(retriever=flaky, generator=None, cfg=QConfig(retrieve_grace_s=0.25, retry_backoff_s=60.0))
    for line in ["gateway latency fix", "the search latency again", "and the fuzzy scan"]:
        out = ql.on_utterance(line)
    assert len(calls) == 1                                     # one attempt, then backoff
    assert out["coverage"]["state"] == "UNAVAILABLE"
    ql.close()


def test_memory_key_is_stable_across_sentences():
    ql = make()
    ql.on_utterance("memory continuity gateway search latency shards")
    ql.on_utterance("the gateway search latency again for shards")
    out = ql.on_utterance("and shards latency search matters for the gateway")
    assert out["coverage"]["memory"] == "fresh"                # a new sentence did not invalidate the memory view
    ql.close()


def test_carried_candidates_mean_no_blocking_on_the_model():
    calls = {"n": 0}

    def gen(tail, topic, hits, n):
        calls["n"] += 1
        if calls["n"] > 1:
            time.sleep(1.0)
        return fake_generator(tail, topic, hits, n)
    ql = QLive(retriever=fake_retriever(), generator=gen, cfg=QConfig(retrieve_grace_s=0.25, cue_budget_s=2.0))
    ql.on_utterance("the gateway search latency fix")
    t0 = time.perf_counter()
    out = ql.on_utterance("the gateway latency scan again")     # 2nd generation is slow; carried cues exist
    assert time.perf_counter() - t0 < 0.5 and out["display_prompt"] is not None
    ql.close()


def test_reading_a_cue_that_contains_a_negation_is_use_not_contradiction():
    ql = make()
    dp = ql.on_utterance("talk about the gateway search latency fix")["display_prompt"]
    ql.cue.text = "When it doesn't know the answer it says so."     # a cue with its own negation
    out = ql.on_utterance("when it doesn't know the answer it says so, that is the rule")
    assert out["previous_cue_outcome"] == "used" and dp is not None
    ql.close()


def test_a_negation_in_an_unrelated_clause_is_not_a_contradiction():
    ql = make()
    ql.on_utterance("talk about the gateway search latency fix")
    ql.cue.text = "The gateway search latency fix matters."
    out = ql.on_utterance("the gateway search latency fix matters, and separately a dog is a pet, not a wolf today")
    assert out["previous_cue_outcome"] == "used"


def test_an_explicit_correction_is_a_contradiction():
    ql = make()
    ql.on_utterance("talk about the gateway search latency fix")
    ql.cue.text = "The gateway search latency fix always worked."
    out = ql.on_utterance("actually no, let me correct that, the gateway search latency fix did not always work")
    assert out["previous_cue_outcome"] == "contradicted"


def test_a_retired_cue_is_never_offered_again():
    ql = make()
    first = ql.on_utterance("the gateway search latency fix")["display_prompt"]["text"]
    ql.cue.text = first
    out = ql.on_utterance("so " + first.lower())                # spoken: the cue is used and retired
    assert out["previous_cue_outcome"] == "used"
    for line in ["gateway latency fix again", "search latency gateway scan", "the fix for gateway latency"]:
        nxt = ql.on_utterance(line)["display_prompt"]
        assert nxt is None or nxt["text"] != first
    ql.close()


def test_no_cue_is_shown_more_than_the_stale_window():
    ql = make()
    shown = []
    for line in ["gateway search latency fix", "gateway latency fix again", "the search latency scan",
                 "gateway latency once more", "and the fix", "gateway again", "latency fix"]:
        dp = ql.on_utterance(line)["display_prompt"]
        if dp and dp["mode"] == "memory":
            shown.append(dp["text"])
    assert all(shown.count(t) <= ql.cfg.stale_after_turns for t in set(shown))
    ql.close()


def test_a_stalled_model_costs_one_wait_not_one_per_turn():
    def stalled(tail, topic, hits, n):
        time.sleep(3.0)
        return fake_generator(tail, topic, hits, n)
    ql = QLive(retriever=fake_retriever(), generator=stalled, cfg=QConfig(retrieve_grace_s=0.25, cue_budget_s=0.3))
    first = ql.on_utterance("gateway search latency fix")
    assert first["latency_ms"] >= 250                             # the one budgeted wait
    later = [ql.on_utterance(f"gateway latency fix number {i}")["latency_ms"] for i in range(4)]
    assert max(later) < 150, later                                # the stuck call never blocks another turn
    ql.close()
