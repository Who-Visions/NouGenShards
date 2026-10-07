"""Regression for modulo-four bootstrap samples repeating a permutation."""

from nougen_shards.rsi_signature import bootstrap_slope_ci


def test_noisy_four_epochs_do_not_claim_positive_slope():
    # Exhaustive 4**4 paired draws have percentile bounds [-4, 6].
    # The old sampler returned [1.1, 1.1] for every resample count.
    low, high = bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1, 5])
    assert low < 0 < high


def test_reproducible_without_modifying_global_random_state():
    import random

    state = random.getstate()
    first = bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1, 5])
    assert bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1, 5]) == first
    assert random.getstate() == state
