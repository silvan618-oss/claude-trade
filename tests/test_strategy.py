import pytest

from bot.strategy import ma_crossover_signal


def test_buy_on_bullish_crossover():
    # 10 flache Werte, dann starker Anstieg -> schneller MA (2) kreuzt langsamen (5) nach oben
    closes = [100.0] * 10 + [100.0, 105.0]
    signal = ma_crossover_signal(closes, fast=2, slow=5)
    assert signal.action == "buy"


def test_sell_on_bearish_crossover():
    closes = [100.0] * 10 + [100.0, 95.0]
    signal = ma_crossover_signal(closes, fast=2, slow=5)
    assert signal.action == "sell"


def test_hold_without_crossover():
    closes = [100.0 + i for i in range(12)]  # stetiger Aufwaertstrend, fast bleibt ueber slow
    signal = ma_crossover_signal(closes, fast=2, slow=5)
    assert signal.action == "hold"


def test_rejects_too_little_data():
    with pytest.raises(ValueError):
        ma_crossover_signal([100.0, 101.0], fast=2, slow=5)


def test_rejects_invalid_windows():
    with pytest.raises(ValueError):
        ma_crossover_signal([100.0] * 20, fast=5, slow=5)
