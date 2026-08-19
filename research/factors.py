"""Die Muster, die laut Forschung tatsaechlich Bestand haben.

Alle bisherigen Studien haben nach Kurzfrist-Signalen gesucht -- Stunden bis
Wochen. Das ist der am haertesten umkaempfte Bereich. Es gibt aber eine zweite
Familie von Mustern, die seit Jahrzehnten dokumentiert ist und teilweise
weiterhin funktioniert. Sie unterscheidet sich in drei Punkten:

* Sie wirkt im **Querschnitt**: nicht "steigt diese Aktie", sondern "steigt sie
  staerker als die anderen".
* Sie braucht **Monate**, nicht Stunden.
* Sie ist keine Prognose, sondern eine **Risikopraemie** -- man wird dafuer
  bezahlt, etwas zu halten, das andere nicht halten wollen.

Getestet werden hier Momentum, langfristige Gegenbewegung und der
Volatilitaetseffekt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_MONTH = 21


def build_panel(prepared: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Ein Panel aus Datum, Aktie, Kurs und Monatsrendite."""
    parts = []
    for symbol, frame in prepared.items():
        frame = frame.reset_index(drop=True)
        parts.append(pd.DataFrame({
            "date": frame["date"],
            "symbol": symbol,
            "close": frame["close"],
        }))
    panel = pd.concat(parts, ignore_index=True)
    return panel.sort_values(["symbol", "date"]).reset_index(drop=True)


def add_signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Signale je Aktie -- ausschliesslich aus zurueckliegenden Kursen."""
    out = panel.copy()
    grouped = out.groupby("symbol")["close"]

    # Momentum: Rendite ueber 12 Monate, aber OHNE den letzten Monat.
    # Der juengste Monat wird ausgelassen, weil dort kurzfristige Gegenbewegung
    # herrscht, die den Effekt sonst verdeckt -- das ist die Standarddefinition.
    r12 = grouped.transform(lambda s: s.shift(TRADING_DAYS_PER_MONTH) /
                            s.shift(12 * TRADING_DAYS_PER_MONTH) - 1.0)
    out["momentum_12_1"] = r12

    # Kurzfristige Gegenbewegung: Rendite des letzten Monats, invertiert.
    out["reversal_1m"] = -grouped.transform(
        lambda s: s / s.shift(TRADING_DAYS_PER_MONTH) - 1.0)

    # Langfristige Gegenbewegung: 5 bis 1 Jahre zurueck, invertiert.
    out["reversal_lang"] = -grouped.transform(
        lambda s: s.shift(12 * TRADING_DAYS_PER_MONTH) /
        s.shift(60 * TRADING_DAYS_PER_MONTH) - 1.0)

    # Volatilitaetseffekt: ruhige Aktien schlagen historisch wilde.
    daily = grouped.transform(lambda s: s.pct_change())
    out["tief_vola"] = -daily.groupby(out["symbol"]).transform(
        lambda s: s.rolling(6 * TRADING_DAYS_PER_MONTH).std())

    return out


def add_forward(panel: pd.DataFrame, months: int = 1) -> pd.DataFrame:
    """Die Rendite der naechsten ``months`` Monate."""
    out = panel.copy()
    horizon = months * TRADING_DAYS_PER_MONTH
    out["fwd"] = out.groupby("symbol")["close"].transform(
        lambda s: s.shift(-horizon) / s - 1.0)
    return out


def long_short_returns(panel: pd.DataFrame, signal: str, *,
                       quantile: float = 0.2,
                       rebalance_days: int = TRADING_DAYS_PER_MONTH) -> pd.Series:
    """Bestes Fuenftel kaufen, schlechtestes verkaufen, monatlich umschichten.

    Marktneutral konstruiert: Long und Short gleich gross, damit nicht der
    allgemeine Aufwaertstrend gemessen wird.
    """
    frame = panel.dropna(subset=[signal, "fwd"]).copy()
    if frame.empty:
        return pd.Series(dtype=float)

    dates = sorted(frame["date"].unique())
    chosen = dates[::rebalance_days]
    frame = frame[frame["date"].isin(chosen)]

    results = {}
    for date, group in frame.groupby("date"):
        if len(group) < 20:
            continue
        ranks = group[signal].rank(pct=True)
        top = group.loc[ranks >= 1 - quantile, "fwd"]
        bottom = group.loc[ranks <= quantile, "fwd"]
        if top.empty or bottom.empty:
            continue
        results[date] = top.mean() - bottom.mean()

    return pd.Series(results).sort_index()


def summarise(returns: pd.Series, periods_per_year: float = 12.0) -> dict:
    """Kennzahlen einer Renditereihe."""
    if returns.empty or len(returns) < 6:
        return {}
    mean = returns.mean()
    std = returns.std(ddof=1)
    t = mean / (std / np.sqrt(len(returns))) if std > 0 else np.nan
    cumulative = (1 + returns).cumprod()
    drawdown = (cumulative / cumulative.cummax() - 1).min()
    return {
        "n_perioden": len(returns),
        "pro_periode_%": mean * 100,
        "pro_jahr_%": ((1 + mean) ** periods_per_year - 1) * 100,
        "sharpe": (mean / std * np.sqrt(periods_per_year)) if std > 0 else np.nan,
        "t": t,
        "gewinn_perioden_%": (returns > 0).mean() * 100,
        "max_drawdown_%": drawdown * 100,
        "gesamt_faktor": float(cumulative.iloc[-1]),
    }
