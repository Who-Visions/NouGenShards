"""The recall hook budget is learned from this host's real recall times."""
import json
from nougen_shards import recall_hook as rh


def _state(tmp_path, monkeypatch, samples=None):
    monkeypatch.setenv("NOUGEN_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("NOUGEN_RECALL_HOOK_BUDGET_STATE", raising=False)
    monkeypatch.delenv("NOUGEN_RECALL_HOOK_BUDGET_MS", raising=False)
    monkeypatch.delenv("NOUGEN_RECALL_HOOK_BUDGET_MAX_MS", raising=False)
    if samples is not None:
        (tmp_path / "recall_hook_budget.json").write_text(json.dumps({"samples": samples}))


def test_no_samples_uses_default(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    assert rh._env_budget_ms() == rh.DEFAULT_BUDGET_MS


def test_learned_from_slow_host(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [1200] * 10)
    assert rh._env_budget_ms() == 1800


def test_clamped_to_max(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [9000] * 10)
    assert rh._env_budget_ms() == 5000


def test_env_override_wins(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [1200] * 10)
    monkeypatch.setenv("NOUGEN_RECALL_HOOK_BUDGET_MS", "2500")
    assert rh._env_budget_ms() == 2500


def test_partial_result_grows_budget(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    for _ in range(3):
        rh.record_budget_sample({"partial": True, "budget_ms": 800, "tier": "keyword"})
    assert rh._env_budget_ms() == 2400


def test_completed_recall_records_elapsed(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    rh.record_budget_sample({"partial": False, "tier": "node", "elapsed_ms": 1100})
    data = json.loads((tmp_path / "recall_hook_budget.json").read_text())
    assert data["samples"] == [1100]


def test_corrupt_state_falls_back(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    (tmp_path / "recall_hook_budget.json").write_text("not json")
    assert rh._env_budget_ms() == rh.DEFAULT_BUDGET_MS


def test_p90_is_nearest_rank_not_max(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch, [1000] * 9 + [4000])
    # p90 of ten samples is the 9th value (1000), not the outlier (4000).
    assert rh._env_budget_ms() == 1500
