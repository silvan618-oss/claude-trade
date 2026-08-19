"""Zur Eroeffnung einsteigen, nachdem eine gute Nachricht kam.

Die Idee: Nur wenige Anleger verfolgen Termine taeglich. Kommt ueber Nacht eine
sehr gute Meldung, steigt man morgens zur Eroeffnung ein und verdient an den
Nachzuegern, die erst im Lauf des Tages oder der naechsten Tage nachkaufen.

Der Unterschied zur Studie in ``eventstudy.py`` ist der Einstiegszeitpunkt: dort
der Schlusskurs, hier die **Eroeffnung**. Das ist ein anderer Trade und muss
getrennt gemessen werden.

Zwei Korrekturen entscheiden ueber das Ergebnis und fehlen in fast jeder
Darstellung dieser Strategie:

* **Marktbereinigung.** Ueber 20 Tage steigt der Markt im Mittel ohnehin. Ohne
  Abzug misst man die allgemeine Aufwaertsdrift mit.
* **Clusterung nach Datum.** Meldungen ballen sich auf Berichtstagen -- 1.373
  Ereignisse verteilen sich auf nur 787 Handelstage. An einem grossen
  Berichtstag gapt der halbe Sektor gleichzeitig, das sind keine unabhaengigen
  Beobachtungen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HORIZONTE = (0, 1, 3, 5, 20)


@dataclass(frozen=True)
class NewsConfig:
    min_gap: float = 0.05          # ab wann eine Meldung als gross gilt
    min_volume_ratio: float = 2.0
    richtung: int = 1              # 1 = gute Nachricht, -1 = schlechte
    kosten_bp: float = 30.0        # Roundtrip; zur Eroeffnung ist der Spread weit


def find_entries(prepared: dict[str, pd.DataFrame], benchmark: pd.DataFrame,
                 config: NewsConfig | None = None,
                 horizonte: tuple[int, ...] = HORIZONTE) -> pd.DataFrame:
    """Alle Meldungsereignisse mit Einstieg zur Eroeffnung, marktbereinigt."""
    config = config or NewsConfig()
    bench = benchmark.reset_index(drop=True)
    markt = pd.Series(bench["close"].to_numpy(), index=pd.DatetimeIndex(bench["date"]))

    records = []
    for symbol, frame in prepared.items():
        frame = frame.reset_index(drop=True)
        gap = frame["gap"].to_numpy()
        vr = frame["volume_ratio"].to_numpy()
        opens = frame["open"].to_numpy()
        close = frame["close"].to_numpy()
        dates = frame["date"]

        grenze = len(frame) - max(horizonte) - 1
        for i in range(60, grenze):
            g = gap[i] * config.richtung
            if not (np.isfinite(g) and g >= config.min_gap):
                continue
            if not (np.isfinite(vr[i]) and vr[i] >= config.min_volume_ratio):
                continue
            einstieg = opens[i]
            if not np.isfinite(einstieg) or einstieg <= 0:
                continue

            start = dates.iloc[i]
            record = {"symbol": symbol, "date": start, "gap_%": gap[i] * 100}
            for h in horizonte:
                j = i + h
                roh = (close[j] / einstieg - 1.0) * config.richtung
                try:
                    m = markt.asof(dates.iloc[j]) / markt.asof(start) - 1.0
                except (KeyError, TypeError):
                    m = np.nan
                record[f"t{h}"] = (roh - m * config.richtung) * 100
            records.append(record)

    return pd.DataFrame(records).dropna()


def evaluate(entries: pd.DataFrame, config: NewsConfig | None = None,
             horizonte: tuple[int, ...] = HORIZONTE) -> pd.DataFrame:
    """Kennzahlen je Haltedauer, mit geclustertem t-Wert und nach Kosten."""
    config = config or NewsConfig()
    rows = []
    for h in horizonte:
        spalte = f"t{h}"
        if spalte not in entries.columns:
            continue
        werte = entries[spalte].dropna()
        if len(werte) < 30:
            continue

        naiv = werte.mean() / (werte.std(ddof=1) / np.sqrt(len(werte)))
        # Pro Handelstag mitteln: Meldungen desselben Tages sind eine Beobachtung.
        taeglich = entries.loc[werte.index].groupby("date")[spalte].mean()
        geclustert = (taeglich.mean() / (taeglich.std(ddof=1) / np.sqrt(len(taeglich)))
                      if len(taeglich) > 2 and taeglich.std(ddof=1) > 0 else np.nan)

        rows.append({
            "halten_tage": h,
            "n": len(werte),
            "n_tage": len(taeglich),
            "mittel_%": werte.mean(),
            "median_%": werte.median(),
            "treffer_%": (werte > 0).mean() * 100,
            "t_naiv": naiv,
            "t_geclustert": geclustert,
            "nach_kosten_%": werte.mean() - config.kosten_bp / 100.0,
        })
    return pd.DataFrame(rows)
