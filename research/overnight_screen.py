"""Overnight- vs. Intraday-Zerlegung über viele Titel (Tabelle).

    python research/overnight_screen.py            # alle CSVs in research/data
    python research/overnight_screen.py MU NVDA    # Auswahl
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from overnight_vs_intraday import DATA, cum, load  # noqa: E402

MIN_YEARS = 2
COST_BP = 5


def row(sym: str) -> dict | None:
    df = load(sym)
    n = len(df)
    years = n / 252
    if years < MIN_YEARS:
        return None
    on, idy = df["overnight"], df["intraday"]
    q99 = on.quantile(0.99)
    last5 = df[df.date >= "2021-09-08"]
    return {
        "Symbol": sym,
        "ab": df.date.iloc[0][:4],
        "Buy&Hold": cum(df.close_to_close),
        "Overnight": cum(on),
        "Intraday": cum(idy),
        "ON bp/Tag": on.mean() * 1e4,
        "ID bp/Tag": idy.mean() * 1e4,
        "t(ON-ID)": (on - idy).mean() / ((on - idy).std() / np.sqrt(n)),
        "ON ohne Top1%": cum(on[on < q99]),
        f"ON CAGR @{COST_BP}bp": (1 + on - COST_BP / 1e4).prod() ** (1 / years) - 1,
        "B&H CAGR": (1 + df.close_to_close).prod() ** (1 / years) - 1,
        "ON 5J": cum(last5.overnight),
        "ID 5J": cum(last5.intraday),
    }


def fmt(v):
    if isinstance(v, float):
        return f"{v:+.1f}" if abs(v) < 50 and "." in f"{v}" and abs(v) > 3 else f"{v:+.0%}"
    return str(v)


if __name__ == "__main__":
    syms = sys.argv[1:] or sorted(p.stem for p in DATA.glob("*.csv"))
    rows = [r for r in (row(s) for s in syms) if r]
    t = pd.DataFrame(rows).set_index("Symbol")
    pct = [c for c in t.columns if c not in ("ab", "ON bp/Tag", "ID bp/Tag", "t(ON-ID)")]
    out = t.copy()
    for c in pct:
        out[c] = t[c].map(lambda v: f"{v:+.0%}")
    for c in ("ON bp/Tag", "ID bp/Tag", "t(ON-ID)"):
        out[c] = t[c].map(lambda v: f"{v:+.1f}")
    print(out.to_string())
    print(f"\nTitel mit Overnight > Intraday (gesamt): {(t['Overnight'] > t['Intraday']).sum()} von {len(t)}")
    print(f"Titel mit Overnight > Intraday (letzte 5 Jahre): {(t['ON 5J'] > t['ID 5J']).sum()} von {len(t)}")
    print(f"Titel, bei denen Overnight nach {COST_BP} bp Kosten Buy&Hold schlägt: {(t[f'ON CAGR @{COST_BP}bp'] > t['B&H CAGR']).sum()} von {len(t)}")
    print(f"Titel mit |t| > 2 für Overnight minus Intraday: {(t['t(ON-ID)'].abs() > 2).sum()} von {len(t)}")
