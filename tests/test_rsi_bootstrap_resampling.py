"""Regression for modulo-four bootstrap samples repeating a permutation."""

import pytest

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


@pytest.mark.parametrize("n_resamples", [0, -1, 1.5, True])
def test_rejects_invalid_resample_count(n_resamples):
    with pytest.raises(ValueError, match="n_resamples must be a positive integer"):
        bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1, 5], n_resamples=n_resamples)


@pytest.mark.parametrize("alpha", [-0.1, 0.0, 1.0, 1.2, float("nan"), float("inf")])
def test_rejects_invalid_confidence_level(alpha):
    with pytest.raises(ValueError, match="alpha must be finite and strictly between 0 and 1"):
        bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1, 5], alpha=alpha)


def test_rejects_unpaired_series_lengths():
    with pytest.raises(ValueError, match="x_series and y_series must have the same length"):
        bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1])
