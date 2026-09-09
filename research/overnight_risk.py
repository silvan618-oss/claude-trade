"""Kehrseite der Overnight-Strategie: schlimmste Nächte und maximaler Drawdown.

    python research/overnight_risk.py MU TSLA NVDA AMD AMC GME IWM META
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from overnight_vs_intraday import load  # noqa: E402


def max_drawdown(r: pd.Series, dates: pd.Series):
    eq = (1 + r).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1
    i = dd.idxmin()
    p = eq[:i].idxmax()
    rec = eq[i:][eq[i:] >= peak[i]]
    rec_date = dates[rec.index[0]] if len(rec) else "nie"
    return dd.min(), dates[p], dates[i], rec_date


def report(sym: str):
    df = load(sym)
    on = df.overnight
    print(f"\n=== {sym}  {df.date.iloc[0]} .. {df.date.iloc[-1]}")
    worst = df.nsmallest(5, "overnight")
    print("  Schlimmste 5 Nächte (Close -> nächster Open):")
    for _, r in worst.iterrows():
        print(f"    {r.date}  {r.overnight:+.1%}")
    for th in (-0.05, -0.10, -0.15, -0.20):
        print(f"  Nächte schlechter als {th:+.0%}: {(on <= th).sum():3d}   (Tage intraday schlechter: {(df.intraday <= th).sum()})")
    mdd, p, t, rec = max_drawdown(on, df.date)
    print(f"  Max. Drawdown Overnight-Strategie: {mdd:+.1%}  (Hoch {p}, Tief {t}, wieder erholt {rec})")
    mdd_bh, p, t, rec = max_drawdown(df.close_to_close, df.date)
    print(f"  Max. Drawdown Buy&Hold:            {mdd_bh:+.1%}  (Hoch {p}, Tief {t}, wieder erholt {rec})")
    # längste Verlustserie in Nächten
    s = (on < 0).astype(int)
    streak = s.groupby((s != s.shift()).cumsum()).cumsum().max()
    print(f"  Längste Serie negativer Nächte: {streak}")


if __name__ == "__main__":
    for sym in sys.argv[1:] or ["MU", "TSLA", "NVDA", "AMD", "AMC", "GME", "IWM", "META"]:
        report(sym)
