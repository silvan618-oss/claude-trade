from bot.memory import Memory, Trade


def make_memory(tmp_path) -> Memory:
    return Memory(str(tmp_path / "ledger.jsonl"), str(tmp_path / "lessons.md"))


def test_log_and_read_open_trade(tmp_path):
    memory = make_memory(tmp_path)
    trade = Trade(symbol="AAPL", side="long", qty=2, entry_price=100.0,
                  strategy="ma_crossover")
    memory.log_trade(trade)

    assert memory.open_trade("AAPL").id == trade.id
    assert memory.open_trade("MSFT") is None


def test_close_trade_computes_pnl(tmp_path):
    memory = make_memory(tmp_path)
    trade = Trade(symbol="AAPL", side="long", qty=2, entry_price=100.0,
                  strategy="ma_crossover")
    memory.log_trade(trade)

    closed = memory.close_trade(trade, exit_price=90.0)
    assert closed.pnl == -20.0
    assert closed.pnl_pct == -10.0
    assert memory.open_trade("AAPL") is None  # Close-Eintrag ersetzt Open-Eintrag

    stats = memory.stats()
    assert stats["closed_trades"] == 1
    assert stats["losses"] == 1
    assert stats["total_pnl"] == -20.0


def test_lessons_roundtrip(tmp_path):
    memory = make_memory(tmp_path)
    assert memory.read_lessons() == ""

    memory.add_lesson("Avoid crossovers when the MA spread is below 0.5%.")
    memory.add_lesson("Skip entries in the first 30 minutes after market open.")

    lessons = memory.read_lessons()
    assert "MA spread" in lessons
    assert "market open" in lessons
    assert lessons.startswith("# Lessons Learned")
