"""Der Trading-Loop: Markt pruefen -> Setup entscheiden -> Trade ausfuehren.

Vor jedem Einstieg liest der Bot seine Lern-Datei und laesst das Setup vom
Gehirn (Claude) gegen die eigenen Lektionen pruefen. Nach jedem Verlust-Trade
schreibt das Gehirn eine neue Lektion in die Lern-Datei.

Start:
    python -m bot.main            # Endlos-Loop
    python -m bot.main --once     # genau eine Iteration (zum Testen)
"""

import argparse
import sys
import time

from bot.brain import Brain
from bot.broker import AlpacaBroker, SimulatedBroker
from bot.config import Config
from bot.memory import Memory, Trade
from bot.strategy import ma_crossover_signal


def run_iteration(config: Config, broker, memory: Memory, brain: Brain) -> None:
    lessons = memory.read_lessons()
    lookback = config.slow_ma + 5

    for symbol in config.symbols:
        try:
            closes = broker.get_closes(symbol, lookback)
            signal = ma_crossover_signal(closes, config.fast_ma, config.slow_ma)
        except Exception as exc:
            print(f"[{symbol}] data/signal error: {exc}")
            continue

        position = memory.open_trade(symbol)
        print(f"[{symbol}] {signal.describe()}"
              f"{' | position open' if position else ''}")

        if signal.action == "buy" and position is None:
            decision = brain.evaluate_setup(symbol, signal, lessons)
            if not decision["approve"]:
                print(f"[{symbol}] VETO by brain: {decision['reason']}")
                continue

            qty = round(broker.equity() * (config.risk_pct / 100) / signal.price, 4)
            if qty <= 0:
                continue
            broker.buy(symbol, qty)
            trade = Trade(
                symbol=symbol,
                side="long",
                qty=qty,
                entry_price=signal.price,
                strategy="ma_crossover",
                params={"fast": config.fast_ma, "slow": config.slow_ma},
                reason=decision["reason"],
            )
            memory.log_trade(trade)
            print(f"[{symbol}] OPENED {qty} @ {signal.price:.2f} ({decision['reason']})")

        elif signal.action == "sell" and position is not None:
            broker.sell(symbol, position.qty)
            closed = memory.close_trade(position, exit_price=signal.price)
            print(f"[{symbol}] CLOSED @ {signal.price:.2f} | "
                  f"PnL {closed.pnl} ({closed.pnl_pct}%)")

            if (closed.pnl or 0) < 0:
                lesson = brain.review_losing_trade(closed, lessons)
                memory.add_lesson(lesson)
                lessons = memory.read_lessons()
                print(f"[{symbol}] New lesson recorded:\n  {lesson}")

    print(f"Stats: {memory.stats()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MA-crossover trading bot with memory")
    parser.add_argument("--once", action="store_true", help="run a single iteration")
    args = parser.parse_args()

    config = Config()
    memory = Memory(config.ledger_path, config.lessons_path)
    brain = Brain(config.anthropic_api_key)

    if config.has_alpaca:
        if not config.alpaca_paper:
            print("WARNUNG: Live-Trading aktiv (ALPACA_PAPER=false). "
                  "Nur mit kleinen Betraegen (1-3 % des Kapitals) handeln!")
        broker = AlpacaBroker(
            config.alpaca_api_key, config.alpaca_secret_key, paper=config.alpaca_paper
        )
        mode = "paper" if config.alpaca_paper else "LIVE"
    else:
        broker = SimulatedBroker()
        mode = "simulated (no Alpaca keys)"

    print(f"Mode: {mode} | Brain: {'Claude' if config.has_anthropic else 'rule-based fallback'}")
    print(f"Symbols: {', '.join(config.symbols)} | "
          f"MA {config.fast_ma}/{config.slow_ma} | Risk {config.risk_pct}%")

    while True:
        try:
            run_iteration(config, broker, memory, brain)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as exc:
            print(f"Iteration failed: {exc}")
        if args.once:
            break
        time.sleep(config.loop_interval_seconds)


if __name__ == "__main__":
    main()
