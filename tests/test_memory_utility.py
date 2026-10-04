import pytest

from nougen_shards.memory_utility import MemoryUtilityLedger, sign_test


@pytest.fixture
def ledger(tmp_path):
    return MemoryUtilityLedger(tmp_path / "mu.db")


def _case(ledger, i, base_ok, withheld_ok, *, created=100.0, shard_created=50.0):
    cid = f"c{i}"
    ledger.record_recall("e1", cid, [("useful", 40, shard_created), ("noise", 60, shard_created)], created)
    ledger.record_run("e1", cid, base_ok)
    ledger.record_run("e1", cid, withheld_ok["useful"], withheld="useful")
    ledger.record_run("e1", cid, withheld_ok["noise"], withheld="noise")


def test_sign_test():
    assert sign_test(0, 0) == 1.0
    assert sign_test(6, 0) == pytest.approx(2 / 64)
    assert sign_test(3, 3) == 1.0


def test_useful_shard_is_detected_and_noise_is_not(ledger):
    for i in range(8):
        _case(ledger, i, True, {"useful": False, "noise": True})
    u = ledger.utilities()
    assert u["useful"].mv == 1.0 and u["useful"].significant
    assert u["noise"].mv == 0.0 and not u["noise"].significant
    assert ledger.utility_marks() == {"useful": 1.0}


def test_harmful_shard_gets_negative_mark(ledger):
    for i in range(8):
        _case(ledger, i, False, {"useful": False, "noise": True})
    assert ledger.utility_marks() == {"noise": -1.0}


def test_leaked_shards_are_excluded(ledger):
    for i in range(8):
        _case(ledger, i, True, {"useful": False, "noise": True}, shard_created=100.0)
    assert ledger.utilities() == {}
    assert ledger.utility_marks() == {}


def test_min_n_blocks_small_samples(ledger):
    for i in range(4):
        _case(ledger, i, True, {"useful": False, "noise": True})
    assert ledger.utility_marks(min_n=5) == {}


def test_efficiency_counts_only_positive_mv_per_token(ledger):
    for i in range(8):
        _case(ledger, i, True, {"useful": False, "noise": True})
    # MV useful=1 over (40+60)*8 tokens loaded.
    assert ledger.efficiency() == pytest.approx(1.0 / 800)


def test_bonferroni_needs_more_cases_when_many_shards_tested(ledger):
    # 2 shards tested: alpha/2 = 0.025. Six one-way cases give p = 0.03125 -> rejected.
    for i in range(6):
        _case(ledger, i, True, {"useful": False, "noise": True})
    assert ledger.utility_marks() == {}
    for i in range(6, 8):
        _case(ledger, i, True, {"useful": False, "noise": True})
    assert ledger.utility_marks() == {"useful": 1.0}
