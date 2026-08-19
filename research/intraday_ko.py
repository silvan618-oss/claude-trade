"""Knock-out-Zertifikate mit Haltedauer von Stunden bis maximal einem Tag.

Die Tagesstudie in ``knockout.py`` haelt mehrere Tage. Hier geht es um den
kurzen Fall: rein, ein paar Stunden halten, wieder raus.

Zwei Dinge sprechen dabei fuer den kurzen Halt:

* **Keine Finanzierung.** Wer vor Handelsschluss glattstellt, zahlt keine
  Uebernachtzinsen -- bei Hebel 30 immerhin rund 0,48 Prozent pro Tag.
* **Weniger Zeit fuer die Schwelle.** Die Wahrscheinlichkeit, eine Barriere zu
  beruehren, waechst mit der Wurzel der Zeit. Zwei Stunden statt fuenf Tagen
  sind ein voellig anderes Risiko.

Dagegen steht: In zwei Stunden entsteht auch kaum Bewegung, und der Spread
faellt bei jedem einzelnen Trade erneut an.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

BARS_PER_SESSION = 26  # 6,5 Handelsstunden in 15-Minuten-Balken


@dataclass(frozen=True)
class IntradayCosts:
    """Kosten eines Intraday-Trades im Zertifikat."""
    spread: float = 0.010      # hin und zurueck, Anteil am Zertifikatswert
    overnight_rate: float = 0.04  # nur falls doch ueber Nacht gehalten wird
    leverage: float = 30.0


def simulate_holds(bars: pd.DataFrame, *, leverage: float, hold_bars: int,
                   side: int = 1, costs: IntradayCosts | None = None,
                   step: int = 1) -> pd.DataFrame:
    """Jeder Balken ist ein moeglicher Einstieg; gehalten wird ``hold_bars`` lang.

    Der Pfad wird ueber Hoch und Tief jedes Balkens geprueft, damit ein
    zwischenzeitliches Reissen der Schwelle nicht uebersehen wird.
    """
    costs = costs or IntradayCosts(leverage=leverage)
    barrier_distance = 1.0 / leverage

    frame = bars.reset_index(drop=True)
    close = frame["close"].to_numpy(float)
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    session = pd.to_datetime(frame["date"]).dt.date.to_numpy()

    entries = np.arange(0, len(frame) - hold_bars, step)
    records = []
    for i in entries:
        exit_i = i + hold_bars
        # Nur Trades innerhalb desselben Handelstages -- sonst waere es kein
        # Intraday-Trade mehr und die Uebernachtkosten kaemen dazu.
        if session[i] != session[exit_i]:
            continue

        entry = close[i]
        if not np.isfinite(entry) or entry <= 0:
            continue

        if side > 0:
            barrier = entry * (1.0 - barrier_distance)
            touched = np.any(low[i + 1: exit_i + 1] <= barrier)
        else:
            barrier = entry * (1.0 + barrier_distance)
            touched = np.any(high[i + 1: exit_i + 1] >= barrier)

        underlying = (close[exit_i] / entry - 1.0) * side
        payoff = -1.0 if touched else max(leverage * underlying - costs.spread, -1.0)

        records.append({
            "einstieg": frame.at[i, "date"],
            "underlying_%": underlying * 100,
            "ausgeknockt": bool(touched),
            "ergebnis_%": payoff * 100,
            "richtung_stimmte": underlying > 0,
        })

    return pd.DataFrame(records)


def sweep_holds(bars_by_symbol: dict[str, pd.DataFrame], *, leverage: float = 30.0,
                holds: tuple[int, ...] = (2, 4, 8, 13, 26),
                costs: IntradayCosts | None = None,
                step: int = 2) -> pd.DataFrame:
    """Dieselbe Aktienmenge ueber verschiedene Haltedauern, long und short."""
    rows = []
    for hold in holds:
        both = []
        for symbol, bars in bars_by_symbol.items():
            for side in (1, -1):
                trades = simulate_holds(bars, leverage=leverage, hold_bars=hold,
                                        side=side, costs=costs, step=step)
                if not trades.empty:
                    both.append(trades)
        if not both:
            continue
        trades = pd.concat(both, ignore_index=True)
        correct = trades[trades["richtung_stimmte"]]
        rows.append({
            "halten_balken": hold,
            "halten_std": hold * 0.25,
            "n": len(trades),
            "ausgeknockt_%": trades["ausgeknockt"].mean() * 100,
            "richtig_und_raus_%": (correct["ausgeknockt"].mean() * 100
                                   if not correct.empty else np.nan),
            "gewinntrades_%": (trades["ergebnis_%"] > 0).mean() * 100,
            "mittel_%": trades["ergebnis_%"].mean(),
            "median_%": trades["ergebnis_%"].median(),
        })
    return pd.DataFrame(rows)
