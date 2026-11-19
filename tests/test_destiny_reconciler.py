"""Tests for the Destiny reconciler: intents become Destinies once, no duplicates."""
from nougen_shards import destiny, destiny_reconciler as rec


def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_DESTINY_DB", str(tmp_path / "destinies.db"))


def test_plan_creates_new_intents_and_reports_gaps():
    planned = rec.plan(
        [{"title": "Lanes run on free routes", "goal": "Lanes run themselves", "trigger": "every cycle"}],
        existing={},
    )
    assert len(planned["create"]) == 1
    assert planned["create"][0]["trigger"] == "every cycle"
    assert planned["gaps"] == [{"title": "Lanes run on free routes", "missing": ["verification"]}]
    assert planned["duplicate"] == [] and planned["invalid"] == []


def test_plan_skips_existing_titles_case_and_spacing_insensitively():
    existing = {"lanes run on free routes": {"id": 6, "status": "active"}}
    planned = rec.plan(
        [{"title": "  Lanes   run on FREE routes ", "goal": "restated goal"}],
        existing=existing,
    )
    assert planned["create"] == []
    assert planned["duplicate"][0]["existing"] == {"id": 6, "status": "active"}


def test_plan_rejects_intents_without_title_or_goal():
    planned = rec.plan([{"title": "ok", "goal": "fine goal"}, {"title": "Good title", "goal": ""}], existing={})
    assert planned["create"] == []
    assert len(planned["invalid"]) == 2


def test_plan_dedupes_within_one_batch():
    intent = {"title": "Same goal twice", "goal": "one goal"}
    planned = rec.plan([intent, dict(intent)], existing={})
    assert len(planned["create"]) == 1
    assert len(planned["duplicate"]) == 1


def test_reconcile_is_idempotent(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    intents = [{"title": "Measured self-improvement proof", "goal": "Prove the agent improves",
                "trigger": "weekly", "verification": "held-out tests pass"}]
    first = rec.reconcile(intents)
    assert len(first["created"]) == 1
    assert first["created"][0]["status"] == "dormant"
    second = rec.reconcile(intents)
    assert second["created"] == []
    assert len(second["duplicate"]) == 1
    assert len(destiny.unfinished_destinies(limit=50)["destinies"]) == 1


def test_finished_destiny_is_not_reopened_by_restated_goal(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    made = rec.reconcile([{"title": "Ship the drop zone", "goal": "photo drop works"}])["created"][0]
    destiny.update_status(made["id"], "active", actor="test")
    destiny.update_status(made["id"], "fulfilled", actor="test", evidence="verified")
    again = rec.reconcile([{"title": "Ship the drop zone", "goal": "photo drop works"}])
    assert again["created"] == []
    assert again["duplicate"][0]["existing"]["status"] == "fulfilled"


def test_concurrent_reconciles_of_one_title_create_exactly_one(tmp_path, monkeypatch):
    import threading
    _use_tmp_db(tmp_path, monkeypatch)
    intent = [{"title": "Race the same intent", "goal": "only one row may exist"}]
    results = []
    barrier = threading.Barrier(6)

    def worker():
        barrier.wait()
        results.append(rec.reconcile(intent))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert sum(len(r["created"]) for r in results) == 1
    assert len(destiny.unfinished_destinies(limit=50)["destinies"]) == 1
