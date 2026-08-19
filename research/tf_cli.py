"""Multi-Timeframe-Studie: bringt Einigkeit zwischen Zeitebenen etwas?

    python -m research.tf_cli                      # 1h-Basis + Tageschart, 3 Jahre
    python -m research.tf_cli --base 15m --higher 1h,1d
    python -m research.tf_cli --symbols AAPL,NVDA --horizon 8
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from research import data
from research.timeframes import (align, by_confluence, confluence,
                                 forward_returns, signal_correlation)

DEFAULT_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "AMZN", "TSLA", "NFLX", "JPM",
    "BAC", "GS", "V", "MA", "XOM", "CVX", "JNJ", "PFE", "UNH", "LLY",
    "WMT", "COST", "PG", "KO", "HD", "BA", "CAT", "INTC", "MU", "QCOM",
]
# Grobe Roundtrip-Kosten bei liquiden US-Aktien, in Basispunkten.
COST_BP = (10.0, 30.0)


def run(args: argparse.Namespace) -> int:
    higher = tuple(x.strip() for x in args.higher.split(",") if x.strip())
    intervals = (args.base,) + higher
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else DEFAULT_SYMBOLS

    print(f"Basiszeitebene {args.base}, hoehere Ebenen {', '.join(higher)}")
    print(f"Lade {len(symbols)} Aktien ...")

    session = data.make_session()
    collected, correlations = [], []
    try:
        for i, symbol in enumerate(symbols, 1):
            try:
                frames = data.load_timeframes(symbol, intervals, session=session,
                                              refresh=args.refresh)
                aligned = align(frames[args.base], args.base,
                                {k: frames[k] for k in higher})
                scored = confluence(aligned, intervals)
                measured = forward_returns(scored, horizons=tuple(args.horizons))
                measured["symbol"] = symbol
                collected.append(measured)
                correlations.append(signal_correlation(scored, intervals))
            except Exception as exc:
                print(f"  {symbol}: uebersprungen ({type(exc).__name__})")
            if i % 10 == 0:
                print(f"  ... {i}/{len(symbols)}")
    finally:
        session.close()

    if not collected:
        raise SystemExit("keine Daten geladen")

    frame = pd.concat(collected, ignore_index=True)
    print(f"\n{len(frame):,} Balken, {frame['symbol'].nunique()} Aktien, "
          f"{frame['date'].min().date()} bis {frame['date'].max().date()}")

    print("\nKorrelation der Trendrichtungen untereinander:")
    mean_corr = sum(correlations) / len(correlations)
    print(mean_corr.to_string(float_format=lambda v: f"{v:6.3f}"))
    if mean_corr.isna().any().any():
        print("  NaN heisst: eine Zeitebene dreht im geladenen Fenster kaum -- zu kurz "
              "fuer diese Ebene.")

    for horizon in args.horizons:
        result = by_confluence(frame, horizon)
        if result.empty:
            continue
        print(f"\n--- {horizon} Balken vorwaerts, nach Zahl der einigen Zeitebenen ---")
        print(result.to_string(index=False, float_format=lambda v: f"{v:9.2f}"))

    print(f"\nZum Vergleich Roundtrip-Kosten: {COST_BP[0]:.0f} bis {COST_BP[1]:.0f} bp.")
    print("Ein Mittelwert unterhalb dieser Spanne ist nach Kosten kein Gewinn.")
    print("Belastbar waere |t_geclustert| > 3.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="1h", help="Basiszeitebene (15m, 1h, ...)")
    parser.add_argument("--higher", default="1d", help="hoehere Ebenen, kommagetrennt")
    parser.add_argument("--symbols", default=None, help="eigene Auswahl, kommagetrennt")
    parser.add_argument("--horizons", type=lambda s: [int(x) for x in s.split(",")],
                        default=[4, 8, 24], help="Vorwaertshorizonte in Basisbalken")
    parser.add_argument("--refresh", action="store_true")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
