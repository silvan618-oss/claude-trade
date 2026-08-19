"""Monatliche Signalliste der Momentum-Rotation.

Gibt aus, welche Aktien die in ``rotation.py`` untersuchte Regel aktuell halten
wuerde, und was sich gegenueber dem letzten Stichtag aendert.

    python -m research.signal_cli
    python -m research.signal_cli --halten 20 --lookback 126

Das ist die Ausgabe einer Regel, keine Empfehlung. Die Regel hat im Rueckblick
ueber 27 Jahre rund 3,8 Prozentpunkte pro Jahr mehr gebracht als eine
Zufallsauswahl im selben Universum -- bei zwischenzeitlich 49 % Drawdown, und
mit den Einschraenkungen, die in research/README.md stehen.
"""

from __future__ import annotations

import argparse
import datetime as dt
import warnings

import pandas as pd

from research import data
from research.events import prepare_all
from research.factors import SEKTOREN
from research.rotation import (RotationConfig, backtest, buy_and_hold, kennzahlen,
                               momentum, price_matrix, random_control)


def run(args: argparse.Namespace) -> int:
    warnings.filterwarnings("ignore")
    symbols = sorted({s for v in SEKTOREN.values() for s in v})
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * args.jahre)

    print(f"Lade {len(symbols)} Aktien ...")
    frames = data.load_universe(symbols, start, end, verbose=False, refresh=args.refresh)
    prepared = prepare_all(frames)
    prices = price_matrix(prepared)
    signal = momentum(prices, lookback=args.lookback)
    config = RotationConfig(n_halten=args.halten, rebalance_tage=args.rebalance)

    heute = prices.index[-1]
    aktuell = signal.loc[heute].dropna().sort_values(ascending=False)
    auswahl = aktuell.head(args.halten)

    # Stand am letzten Stichtag davor, um die Veraenderung zu zeigen.
    vorher_tag = prices.index[max(len(prices) - 1 - args.rebalance, 0)]
    vorher = set(signal.loc[vorher_tag].dropna().sort_values(ascending=False)
                 .head(args.halten).index)

    print(f"\n{'='*62}")
    print(f"SIGNALLISTE zum {heute.date()}  ({args.halten} Positionen, gleichgewichtet)")
    print(f"Signal: Rendite der letzten {args.lookback} Handelstage")
    print(f"{'='*62}")
    print(f"{'#':>3}  {'Aktie':<8} {'Momentum':>10}   Status")
    for i, (symbol, wert) in enumerate(auswahl.items(), 1):
        status = "haltEN" if symbol in vorher else "NEU"
        print(f"{i:>3}  {symbol:<8} {wert*100:>9.1f} %   {status}")

    raus = vorher - set(auswahl.index)
    if raus:
        print(f"\nWuerde verkauft: {', '.join(sorted(raus))}")
    print(f"Umschlag gegenueber letztem Stichtag: "
          f"{len(set(auswahl.index) ^ vorher) / (2*args.halten) * 100:.0f} %")

    if args.backtest:
        print(f"\n{'='*62}\nRUECKRECHNUNG derselben Regel")
        strategie = backtest(prices, signal, config)
        kontrolle = random_control(prices, config, seed=args.seed)
        halten_alle = buy_and_hold(prices, ab=strategie.index[0])
        for name, kurve in (("Rotation", strategie),
                            ("Zufallsauswahl (Kontrolle)", kontrolle),
                            ("alles gleichgewichtet halten", halten_alle)):
            werte = kennzahlen(kurve, rebalance_tage=args.rebalance)
            if werte:
                print(f"  {name:<30} {werte['pro_jahr_%']:>7.2f} % p.a.  "
                      f"Faktor {werte['faktor']:>6.1f}  maxDD {werte['max_drawdown_%']:>7.1f} %")
        print("\n  Massgeblich ist der Abstand zur Kontrolle, nicht zum Index:")
        print("  Beide tragen dieselbe Verzerrung durch das Ueberlebenden-Universum.")

    print("\nAusgabe einer Regel, keine Anlageempfehlung. Einschraenkungen: research/README.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--halten", type=int, default=15, help="Anzahl Positionen")
    parser.add_argument("--lookback", type=int, default=252, help="Momentum-Fenster in Tagen")
    parser.add_argument("--rebalance", type=int, default=21, help="Umschichtrhythmus in Tagen")
    parser.add_argument("--jahre", type=int, default=17, help="Historie fuer die Rueckrechnung")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--refresh", action="store_true", help="Kurse neu laden")
    parser.add_argument("--backtest", action="store_true", default=True)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
