"""Evaluate the user's daily Tongdaxin formula without changing nested HHV/LLV."""

from dataclasses import dataclass
import math
from typing import Sequence


class UndefinedFormulaError(ValueError):
    """The formula cannot yield a signal on the supplied history."""


@dataclass(frozen=True)
class FormulaResult:
    j: float
    dif: float
    avg_high: float
    avg_low: float

    @property
    def selected(self) -> bool:
        return self.j < 18 and self.dif > 0 and self.avg_high > 4 * self.avg_low


def _rolling(values: Sequence[float], window: int, extreme) -> list[float]:
    # Evaluate each timestamp before applying the next nested rolling expression.
    return [extreme(values[max(0, i - window + 1):i + 1]) for i in range(len(values))]


def volume_extremes(volume: Sequence[float]) -> tuple[float, float]:
    """VOL must be in lots (手), including the formula's literal 9999999 sentinel."""
    vh1 = _rolling(volume, 30, max)
    vh2 = _rolling([v if v < h else 0 for v, h in zip(volume, vh1)], 30, max)
    vh3 = _rolling([v if v < h else 0 for v, h in zip(volume, vh2)], 30, max)
    vl1 = _rolling(volume, 30, min)
    vl2 = _rolling([v if v > lo else 9999999 for v, lo in zip(volume, vl1)], 30, min)
    vl3 = _rolling([v if v > lo else 9999999 for v, lo in zip(volume, vl2)], 30, min)
    return (vh1[-1] + vh2[-1] + vh3[-1]) / 3, (vl1[-1] + vl2[-1] + vl3[-1]) / 3


def _smooth(values: Sequence[float], alpha: float) -> list[float]:
    previous = values[0]
    result = [previous]
    for value in values[1:]:
        previous += alpha * (value - previous)
        result.append(previous)
    return result


def evaluate_formula(
    close: Sequence[float], high: Sequence[float], low: Sequence[float], volume: Sequence[float],
) -> FormulaResult:
    """Chronological, forward-adjusted OHLC, raw volume in lots.

    SMA(X,3,1) uses the recursive alpha=1/3 smoothing, not a simple mean.
    EMA is seeded with the first close; SMA with the first complete-window RSV.
    At least 90 bars are required to warm up the three nested 30-bar extrema.
    Zero-range RSV is undefined and rejected, rather than inventing a signal.
    Exact terminal parity still depends on data, adjustment and seed history.
    """
    size = len(close)
    if size < 90 or any(len(v) != size for v in (high, low, volume)):
        raise UndefinedFormulaError("at least 90 aligned daily bars are required")
    if any(not math.isfinite(float(v)) for series in (close, high, low, volume) for v in series):
        raise ValueError("non-finite OHLCV data")
    for c, h, lo, v in zip(close, high, low, volume):
        if lo <= 0 or not lo <= c <= h or v < 0:
            raise ValueError("invalid OHLCV data")
    rsv = []
    for i in range(8, size):
        bottom, top = min(low[i - 8:i + 1]), max(high[i - 8:i + 1])
        if top == bottom:
            raise UndefinedFormulaError("undefined RSV: nine-bar high equals low")
        rsv.append((close[i] - bottom) / (top - bottom) * 100)
    k = _smooth(rsv, 1 / 3)
    d = _smooth(k, 1 / 3)
    dif = _smooth(close, 2 / 13)[-1] - _smooth(close, 2 / 27)[-1]
    avg_high, avg_low = volume_extremes(volume)
    return FormulaResult(3 * k[-1] - 2 * d[-1], dif, avg_high, avg_low)
