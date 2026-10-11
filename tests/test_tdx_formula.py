"""Offline regression tests for nested Tongdaxin formula semantics."""

import math
import unittest

from src.services.screening.tdx_formula import FormulaResult, evaluate_formula, volume_extremes
from scripts.screen_tdx import eligible


class TongdaxinFormulaTest(unittest.TestCase):
    def test_nested_extrema_are_not_sorted_top_three(self):
        volumes = [float(i % 13 + 1) for i in range(100)]
        high, low = volume_extremes(volumes)
        self.assertEqual((high, low), (12, 2))
        self.assertNotEqual(high, sum(sorted(volumes[-30:])[-3:]) / 3)
        self.assertNotEqual(low, sum(sorted(volumes[-30:])[:3]) / 3)

    def test_constant_volume_preserves_literal_sentinel(self):
        self.assertEqual(volume_extremes([100.] * 100), (100 / 3, (100 + 9999999 * 2) / 3))

    def test_recursive_sma_not_simple_average(self):
        # Independent recurrence on fixed 9-bar extrema; the first RSV is 50.
        closes = [5.] * 100 + [1., 2., 1.]
        ema12 = ema26 = 5.
        for close in closes[1:]:
            ema12 = (2 * close + 11 * ema12) / 13
            ema26 = (2 * close + 25 * ema26) / 27
        result = evaluate_formula(closes, [10.] * 103, [0.1] * 103, [100.] * 103)
        # Repeat reference RSV with the actual low=0.1.
        k = d = (5 - 0.1) / 9.9 * 100
        for close in closes[100:]:
            k = ((close - 0.1) / 9.9 * 100 + 2 * k) / 3
            d = (k + 2 * d) / 3
        self.assertAlmostEqual(result.j, 3 * k - 2 * d)
        self.assertAlmostEqual(result.dif, ema12 - ema26)

    def test_strict_boundaries(self):
        self.assertTrue(FormulaResult(17, 1, 41, 10).selected)
        for result in (FormulaResult(18, 1, 41, 10), FormulaResult(17, 0, 41, 10),
                       FormulaResult(17, 1, 40, 10)):
            self.assertFalse(result.selected)

    def test_invalid_history_is_not_a_nonmatch(self):
        for size, close, high, low, volume in (
            (20, 5, 10, 1, 100), (100, math.nan, 10, 1, 100),
            (100, 5, 5, 5, 100), (100, 5, 10, 1, -1),
        ):
            with self.assertRaises(ValueError):
                evaluate_formula([close] * size, [high] * size, [low] * size, [volume] * size)

    def test_market_scope_and_st(self):
        for code in ("600519", "000001", "300750", "688001", "002001", "601001"):
            self.assertTrue(eligible(code, "正常名称"))
            self.assertFalse(eligible(code, "*ST测试"))
        for code in ("920001", "830001", "510300", "900901", "200001", "AAPL"):
            self.assertFalse(eligible(code, "正常名称"))


if __name__ == "__main__":
    unittest.main()
