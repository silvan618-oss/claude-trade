"""Der Trading-Loop: Markt pruefen -> Setup entscheiden -> Trade ausfuehren.

Vor jedem Einstieg liest der Bot seine Lern-Datei und laesst das Setup vom
Gehirn (Claude) gegen die eigenen Lektionen pruefen. Nach jedem Verlust-Trade
schreibt das Gehirn eine neue Lektion in die Lern-Datei.

Welches Signal einen Einstieg ausloest, steuert SIGNAL_MODE:
    ma        MA-Crossover (Default, unveraendert)
    insider   Cluster Buying aus Pflichtmeldungen (bot/insider.py)
    combined  Crossover UND Insider-Bestaetigung

Der Ausstieg laeuft in allen Modi ueber das baerische Crossover: Meldedaten
liefern Einstiegs-, aber keine brauchbaren Ausstiegssignale.

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
from bot.insider import build_insider_source, signal_for
from bot.memory import Memory, Trade
from bot.strategy import ma_crossover_signal


def wants_entry(config: Config, signal, insider) -> bool:
    """Entscheidet je nach SIGNAL_MODE, ob ein Einstieg geprueft werden soll."""
    ma_buy = signal.action == "buy"
    insider_buy = insider is not None and insider.action == "buy"

    if config.signal_mode == "insider":
        return insider_buy
    if config.signal_mode == "combined":
        return ma_buy and insider_buy
    return ma_buy


def run_iteration(
    config: Config, broker, memory: Memory, brain: Brain, insider_source=None
) -> None:
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

        # Insider-Ebene nur abfragen, wenn sie den Einstieg beeinflussen kann.
        insider = None
        if insider_source is not None and position is None and signal.action != "sell":
            try:
                insider = signal_for(insider_source, symbol, config)
                print(f"[{symbol}] {insider.describe()}")
            except Exception as exc:
                print(f"[{symbol}] insider lookup failed: {exc}")

        if position is None and wants_entry(config, signal, insider):
            context = insider.describe() if insider else ""
            decision = brain.evaluate_setup(symbol, signal, lessons, context=context)
            if not decision["approve"]:
                print(f"[{symbol}] VETO by brain: {decision['reason']}")
                continue

            qty = round(broker.equity() * (config.risk_pct / 100) / signal.price, 4)
            if qty <= 0:
                continue
            broker.buy(symbol, qty)
            params = {"fast": config.fast_ma, "slow": config.slow_ma}
            if insider is not None:
                params["insider_buyers"] = insider.buyers
                params["insider_score"] = insider.score
                params["insider_people"] = insider.people
                params["insider_max_filing_lag_days"] = insider.max_filing_lag_days
            trade = Trade(
                symbol=symbol,
                side="long",
                qty=qty,
                entry_price=signal.price,
                strategy=config.signal_mode,
                params=params,
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
    if config.signal_mode not in ("ma", "insider", "combined"):
        sys.exit(f"Unbekannter SIGNAL_MODE '{config.signal_mode}' "
                 "(erlaubt: ma, insider, combined)")

    memory = Memory(config.ledger_path, config.lessons_path)
    brain = Brain(config.anthropic_api_key)
    insider_source = build_insider_source(config) if config.uses_insider else None

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
    print(f"Signal: {config.signal_mode}" + (
        f" | Insider: {'QuiverQuant' if config.has_quiver else 'simuliert (kein Key)'}, "
        f"min. {config.insider_min_buyers} Kaeufer in {config.insider_lookback_days}d"
        if config.uses_insider else ""))

    while True:
        try:
            run_iteration(config, broker, memory, brain, insider_source)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as exc:
            print(f"Iteration failed: {exc}")
        if args.once:
            break
        time.sleep(config.loop_interval_seconds)


if __name__ == "__main__":
    main()
