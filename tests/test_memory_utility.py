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


def test_min_cases_for_sign_test():
    from nougen_shards.memory_utility import min_cases_for_sign_test

    # One-sided
    assert min_cases_for_sign_test(1, alpha=0.05, two_sided=False) == 5
    assert min_cases_for_sign_test(5, alpha=0.05, two_sided=False) == 7
    assert min_cases_for_sign_test(20, alpha=0.05, two_sided=False) == 9
    assert min_cases_for_sign_test(50, alpha=0.05, two_sided=False) == 10

    # Two-sided
    assert min_cases_for_sign_test(1, alpha=0.05, two_sided=True) == 6
    assert min_cases_for_sign_test(5, alpha=0.05, two_sided=True) == 8
    assert min_cases_for_sign_test(20, alpha=0.05, two_sided=True) == 10
    assert min_cases_for_sign_test(50, alpha=0.05, two_sided=True) == 11


def test_effective_sample_size():
    from nougen_shards.memory_utility import effective_sample_size

    # Uncorrelated (rho = 0) -> n_eff = n
    assert effective_sample_size(10, 0.0) == 10.0
    # Fully correlated (rho = 1) -> n_eff = 1
    assert effective_sample_size(10, 1.0) == 1.0
    # Moderate correlation (rho = 0.5) -> 10 / (1 + 9 * 0.5) = 10 / 5.5 = 1.818...
    assert effective_sample_size(10, 0.5) == pytest.approx(10 / 5.5)
    # Zero or empty
    assert effective_sample_size(0, 0.5) == 0.0


def test_twenty_shards_under_sample_refusal(ledger):
    # Testing 20 shards with only 8 cases refuses to report marks (needs >= 10 for two-sided)
    shards_list = [(f"s_{k}", 10, 50.0) for k in range(20)]
    for i in range(8):
        cid = f"c_20_{i}"
        ledger.record_recall("e20", cid, shards_list, 100.0)
        ledger.record_run("e20", cid, True)
        # Shard 0 was withheld and led to failure (all 8 wins)
        for k in range(20):
            ledger.record_run("e20", cid, False if k == 0 else True, withheld=f"s_{k}")

    # 8 cases cannot clear alpha/20 (p = 2/256 = 0.0078125 > 0.0025)
    assert ledger.utility_marks(epoch="e20") == {}

    # Adding cases 8 and 9 (total 10 all-win cases, p = 2/1024 = 0.001953 < 0.0025)
    for i in range(8, 10):
        cid = f"c_20_{i}"
        ledger.record_recall("e20", cid, shards_list, 100.0)
        ledger.record_run("e20", cid, True)
        for k in range(20):
            ledger.record_run("e20", cid, False if k == 0 else True, withheld=f"s_{k}")

    assert ledger.utility_marks(epoch="e20") == {"s_0": 1.0}
