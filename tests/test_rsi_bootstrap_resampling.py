"""Tests for RSI bootstrap slope resampling robustness, non-degeneracy, and CI correctness."""

import random
import unittest

import pytest

from nougen_shards.rsi_signature import bootstrap_slope_ci, evaluate_rsi_signature


def test_noisy_four_epochs_do_not_claim_positive_slope():
    # Exhaustive 4**4 paired draws have percentile bounds [-4, 6].
    # The old sampler returned [1.1, 1.1] for every resample count.
    low, high = bootstrap_slope_ci([0, 1, 2, 3], [0, 3, -1, 5])
    assert low < 0 < high


def test_reproducible_without_modifying_global_random_state():
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


class TestRsiBootstrapResampling(unittest.TestCase):
    def test_bootstrap_slope_ci_degenerate_resampling_protection(self):
        # Monotonically increasing line should yield positive slope CI
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        ci_low, ci_high = bootstrap_slope_ci(x, y, n_resamples=100)
        self.assertGreater(ci_low, 0.0)
        self.assertGreater(ci_high, 0.0)
        self.assertLessEqual(ci_low, ci_high)

    def test_bootstrap_slope_ci_handles_identical_points(self):
        # All points have identical x in a sample (degenerate case)
        x = [1.0, 1.0, 1.0]
        y = [2.0, 3.0, 4.0]
        ci_low, ci_high = bootstrap_slope_ci(x, y, n_resamples=50)
        self.assertEqual(ci_low, 0.0)
        self.assertEqual(ci_high, 0.0)

    def test_evaluate_rsi_signature_with_bootstrap(self):
        epochs = [1, 2, 3, 4, 5]
        eta = [0.1, 0.25, 0.4, 0.65, 0.9]
        search = [0.2, 0.4, 0.6, 0.8, 1.0]
        ood = [0.15, 0.35, 0.55, 0.75, 0.95]
        result = evaluate_rsi_signature(epochs, eta, search, ood)
        self.assertTrue(result.is_rsi_confirmed)
        self.assertGreater(result.ci_lower, 0.0)


if __name__ == '__main__':
    unittest.main()
