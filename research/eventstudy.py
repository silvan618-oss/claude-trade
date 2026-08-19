"""Ereignis-Studie: was passiert mit dem Kurs NACH dem Ereignis.

Alle Renditen werden ab dem *Schlusskurs des Ereignistages* gemessen. Das ist
bewusst konservativ: Der Ueberacht-Gap ist zu diesem Zeitpunkt laengst gelaufen
und fuer niemanden mehr handelbar, der die Nachricht erst lesen muss. Gemessen
wird also nur, was tatsaechlich noch uebrig ist.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (1, 2, 3, 5, 10, 20)


def _benchmark_series(prepared_benchmark: pd.DataFrame) -> pd.Series:
    return pd.Series(
        prepared_benchmark["close"].to_numpy(),
        index=pd.DatetimeIndex(prepared_benchmark["date"]),
    )


def measure(events: pd.DataFrame, prepared: dict[str, pd.DataFrame],
            benchmark: pd.DataFrame,
            horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """Ergaenzt jedes Ereignis um seine Vorwaertsrenditen.

    ``fwd_{h}``   -- rohe Rendite ueber h Handelstage ab Schluss Ereignistag
    ``abn_{h}``   -- dieselbe Rendite abzueglich Marktbewegung (SPY)
    ``sig_{h}``   -- marktbereinigt und mit der Ereignisrichtung multipliziert.
                     Positiv heisst: die Bewegung ging weiter (Momentum).
                     Negativ heisst: der Kurs kam zurueck (Reversal).
    """
    if events.empty:
        return events.copy()

    bench = _benchmark_series(benchmark)
    out = events.copy().reset_index(drop=True)

    columns: dict[str, list[float]] = {}
    for h in horizons:
        columns[f"fwd_{h}"] = []
        columns[f"abn_{h}"] = []

    for record in out.itertuples(index=False):
        frame = prepared[record.symbol]
        row = int(record.row)
        entry = frame.at[row, "close"]
        entry_date = frame.at[row, "date"]

        for h in horizons:
            target = row + h
            if target >= len(frame) or entry <= 0:
                columns[f"fwd_{h}"].append(np.nan)
                columns[f"abn_{h}"].append(np.nan)
                continue

            stock = frame.at[target, "close"] / entry - 1.0
            exit_date = frame.at[target, "date"]

            # Marktbewegung ueber exakt denselben Kalenderzeitraum abziehen.
            try:
                b0 = bench.asof(entry_date)
                b1 = bench.asof(exit_date)
                market = b1 / b0 - 1.0 if b0 and b0 > 0 else np.nan
            except (KeyError, TypeError):
                market = np.nan

            columns[f"fwd_{h}"].append(stock)
            columns[f"abn_{h}"].append(stock - market)

    for name, values in columns.items():
        out[name] = values
    for h in horizons:
        out[f"sig_{h}"] = out[f"abn_{h}"] * out["side"]

    return out


def _clustered_tstat(values: pd.Series, dates: pd.Series) -> float:
    """t-Wert mit Clusterung nach Datum.

    Ereignisse haeufen sich an denselben Tagen -- an einem Crashtag gapt der
    halbe Markt gleichzeitig nach unten. Behandelt man die als unabhaengige
    Beobachtungen, wird der t-Wert dramatisch zu gross. Deshalb wird zuerst pro
    Handelstag gemittelt und erst dann ueber die Tage getestet.
    """
    frame = pd.DataFrame({"value": values, "date": dates}).dropna()
    if frame.empty:
        return np.nan
    daily = frame.groupby("date")["value"].mean()
    if len(daily) < 3 or daily.std(ddof=1) == 0:
        return np.nan
    return float(daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily))))


def summarise(measured: pd.DataFrame, column_prefix: str = "sig",
              horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """Aggregiert die Ereignisse zu einer Ergebnistabelle."""
    rows = []
    for h in horizons:
        column = f"{column_prefix}_{h}"
        if column not in measured.columns:
            continue
        series = measured[column].dropna()
        if series.empty:
            continue

        naive_t = (
            float(series.mean() / (series.std(ddof=1) / np.sqrt(len(series))))
            if len(series) > 2 and series.std(ddof=1) > 0
            else np.nan
        )
        aligned = measured.loc[series.index]
        rows.append(
            {
                "horizont_tage": h,
                "n": len(series),
                "n_tage": aligned["date"].nunique(),
                "mittel_%": series.mean() * 100,
                "median_%": series.median() * 100,
                "trefferquote_%": (series > 0).mean() * 100,
                "streuung_%": series.std(ddof=1) * 100,
                "t_naiv": naive_t,
                "t_geclustert": _clustered_tstat(series, aligned["date"]),
            }
        )
    return pd.DataFrame(rows)


def compare(event_summary: pd.DataFrame, control_summary: pd.DataFrame) -> pd.DataFrame:
    """Stellt Ereignisse und Zufallskontrolle nebeneinander."""
    merged = event_summary.merge(
        control_summary, on="horizont_tage", suffixes=("_ereignis", "_zufall")
    )
    merged["differenz_%"] = merged["mittel_%_ereignis"] - merged["mittel_%_zufall"]
    return merged[
        [
            "horizont_tage",
            "n_ereignis", "mittel_%_ereignis", "trefferquote_%_ereignis",
            "t_naiv_ereignis", "t_geclustert_ereignis",
            "n_zufall", "mittel_%_zufall", "trefferquote_%_zufall",
            "differenz_%",
        ]
    ]


def decompose(measured: pd.DataFrame) -> pd.DataFrame:
    """Zerlegt die Ereignisbewegung in die drei Phasen.

    Zeigt, wie sich die Gesamtbewegung auf den Teil vor der Eroeffnung, den
    Handelstag selbst und die Zeit danach verteilt -- also darauf, was fuer
    jemanden, der die Nachricht erst lesen muss, ueberhaupt erreichbar ist.
    """
    signed_gap = measured["gap"] * measured["side"]
    signed_intraday = measured["intraday"] * measured["side"]
    rows = [
        {"phase": "Ueberacht-Gap (vor Eroeffnung)", "mittel_%": signed_gap.mean() * 100,
         "beschreibung": "bereits gelaufen, nicht handelbar"},
        {"phase": "Ereignistag ab Eroeffnung", "mittel_%": signed_intraday.mean() * 100,
         "beschreibung": "nur mit Sekundenreaktion erreichbar"},
    ]
    for h in (5, 20):
        column = f"sig_{h}"
        if column in measured.columns:
            rows.append(
                {
                    "phase": f"danach, {h} Handelstage",
                    "mittel_%": measured[column].mean() * 100,
                    "beschreibung": "das ist der handelbare Rest",
                }
            )
    return pd.DataFrame(rows)
