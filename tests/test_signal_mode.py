from bot.config import Config
from bot.insider import InsiderSignal
from bot.main import wants_entry
from bot.strategy import Signal

MA_BUY = Signal(action="buy", fast_ma=11.0, slow_ma=10.0, price=10.0)
MA_HOLD = Signal(action="hold", fast_ma=11.0, slow_ma=10.0, price=10.0)
INSIDER_BUY = InsiderSignal(symbol="ACME", action="buy", buyers=3)
INSIDER_HOLD = InsiderSignal(symbol="ACME", action="hold", buyers=1)


def config(mode: str) -> Config:
    cfg = Config()
    cfg.signal_mode = mode
    return cfg


def test_ma_mode_ignores_insider_data():
    assert wants_entry(config("ma"), MA_BUY, INSIDER_HOLD) is True
    assert wants_entry(config("ma"), MA_HOLD, INSIDER_BUY) is False


def test_insider_mode_enters_without_crossover():
    assert wants_entry(config("insider"), MA_HOLD, INSIDER_BUY) is True
    assert wants_entry(config("insider"), MA_BUY, INSIDER_HOLD) is False


def test_combined_mode_needs_both():
    assert wants_entry(config("combined"), MA_BUY, INSIDER_BUY) is True
    assert wants_entry(config("combined"), MA_BUY, INSIDER_HOLD) is False
    assert wants_entry(config("combined"), MA_HOLD, INSIDER_BUY) is False


def test_missing_insider_data_never_triggers_an_insider_entry():
    assert wants_entry(config("insider"), MA_BUY, None) is False
    assert wants_entry(config("combined"), MA_BUY, None) is False
