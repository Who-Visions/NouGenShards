"""Tests for RSI bootstrap slope resampling robustness, non-degeneracy, and CI correctness."""
import unittest
from nougen_shards.rsi_signature import bootstrap_slope_ci, linear_slope, evaluate_rsi_signature

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
