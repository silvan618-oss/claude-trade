"""Faktencheck: Overnight- vs. Intraday-Renditen ("Stop day-trading, try night-trading").

Zerlegt jede Tagesrendite in zwei Teile:
  overnight = Open(t) / Close(t-1) - 1   (kaufen zum Schluss, verkaufen zur Eröffnung)
  intraday  = Close(t) / Open(t) - 1     (kaufen zur Eröffnung, verkaufen zum Schluss)

Multipliziert man beide Ketten, kommt exakt Buy-and-Hold heraus. Die Zerlegung
"erzeugt" also keine Rendite, sie verteilt sie nur.

Nutzung:
    python research/overnight_vs_intraday.py MU SPY AAPL GOOGL
Erwartet research/data/<SYMBOL>.csv mit den Spalten date, open, close
(vollständig adjustierte Kurse). Beiliegende Daten: viaNexus EOD, Stand 2026-09-08.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
COST_BPS = (0, 1, 2, 5, 10)  # Kosten pro Round-Trip in Basispunkten


def load(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{symbol}.csv").sort_values("date").reset_index(drop=True)
    df = df[["date", "open", "close"]].dropna()
    # Datenfehler (Open oder Close = 0) verwerfen
    df = df[(df["open"] > 0) & (df["close"] > 0)]
    # Feiertage sind im Rohdatensatz als exakte Kopie des Vortags enthalten -> entfernen
    dup = (df[["open", "close"]].shift() == df[["open", "close"]]).all(axis=1)
    df = df[~dup].reset_index(drop=True)
    df["overnight"] = df["open"] / df["close"].shift() - 1
    df["intraday"] = df["close"] / df["open"] - 1
    df["close_to_close"] = df["close"] / df["close"].shift() - 1
    return df.dropna().reset_index(drop=True)


def cum(r: pd.Series) -> float:
    return float((1 + r).prod() - 1)


def report(symbol: str, df: pd.DataFrame) -> None:
    n = len(df)
    years = n / 252
    on, idy = df["overnight"], df["intraday"]
    print(f"\n=== {symbol}  {df.date.iloc[0]} .. {df.date.iloc[-1]}  ({n} Handelstage, {years:.1f} Jahre)")
    print(f"Buy&Hold (Close->Close):         {cum(df.close_to_close):>12.1%}")
    print(f"Overnight kumuliert (Close->Open):{cum(on):>12.1%}")
    print(f"Intraday kumuliert (Open->Close): {cum(idy):>12.1%}")
    for name, r in (("overnight", on), ("intraday", idy)):
        t = r.mean() / (r.std() / np.sqrt(n))
        cagr = (1 + r).prod() ** (1 / years) - 1
        print(
            f"  {name:9s} Ø/Tag {r.mean() * 1e4:6.1f} bp  Median {r.median() * 1e4:5.1f} bp  "
            f"Std {r.std() * 1e4:5.0f} bp  t={t:5.2f}  Trefferquote {(r > 0).mean():.1%}  CAGR {cagr:.1%}"
        )
    q99 = on.quantile(0.99)
    print(f"  Overnight ohne die besten 1% Nächte ({int((on >= q99).sum())} Tage): {cum(on[on < q99]):.0%}")
    print("  Overnight-Strategie nach Kosten (pro Round-Trip):")
    for c in COST_BPS:
        net = on - c / 1e4
        print(f"    {c:3d} bp: {cum(net):>12.1%}   (CAGR {(1 + net).prod() ** (1 / years) - 1:.1%})")
    df = df.assign(year=df.date.str[:4])
    g = df.groupby("year").agg(
        overnight=("overnight", cum), intraday=("intraday", cum), buy_hold=("close_to_close", cum)
    )
    print(g.map(lambda v: f"{v:+.0%}").to_string())


if __name__ == "__main__":
    for sym in sys.argv[1:] or ["MU", "SPY", "AAPL", "GOOGL"]:
        report(sym, load(sym))
