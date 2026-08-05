"""Moving-Average-Crossover — die simple Startstrategie aus dem Video.

Signal-Logik:
  * BUY  wenn der schnelle MA den langsamen MA von unten nach oben kreuzt
  * SELL wenn der schnelle MA den langsamen MA von oben nach unten kreuzt
  * HOLD sonst
"""

from dataclasses import dataclass


@dataclass
class Signal:
    action: str  # "buy" | "sell" | "hold"
    fast_ma: float
    slow_ma: float
    price: float

    def describe(self) -> str:
        return (
            f"{self.action.upper()} @ {self.price:.2f} "
            f"(fast MA {self.fast_ma:.2f} / slow MA {self.slow_ma:.2f})"
        )


def sma(values: list[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"Need at least {window} values, got {len(values)}")
    return sum(values[-window:]) / window


def ma_crossover_signal(closes: list[float], fast: int, slow: int) -> Signal:
    """Berechnet das Crossover-Signal aus einer Liste von Schlusskursen."""
    if fast >= slow:
        raise ValueError("fast MA window must be smaller than slow MA window")
    if len(closes) < slow + 1:
        raise ValueError(f"Need at least {slow + 1} closes, got {len(closes)}")

    fast_now = sma(closes, fast)
    slow_now = sma(closes, slow)
    fast_prev = sma(closes[:-1], fast)
    slow_prev = sma(closes[:-1], slow)

    if fast_prev <= slow_prev and fast_now > slow_now:
        action = "buy"
    elif fast_prev >= slow_prev and fast_now < slow_now:
        action = "sell"
    else:
        action = "hold"

    return Signal(action=action, fast_ma=fast_now, slow_ma=slow_now, price=closes[-1])
