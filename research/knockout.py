"""Simuliert Hebelzertifikate auf den gefundenen Ereignissen.

Beantwortet die Frage, die eine reine Renditestatistik nicht beantworten kann:
Haette man die Bewegung mit Hebel ueberhaupt ueberlebt? Ein Knock-out-Papier
ist pfadabhaengig -- es reicht nicht, dass der Kurs am Ende richtig steht, er
darf zwischendurch nie die Schwelle beruehrt haben.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Bei Hebel L liegt die Knock-out-Schwelle rund 1/L vom Einstiegskurs entfernt.
LEVERAGES = (50, 20, 10, 5, 2, 1)


@dataclass(frozen=True)
class CostModel:
    """Kosten, die auf ein Hebelzertifikat anfallen."""
    financing_rate: float = 0.04   # Jahreszins auf das Nominal (= Hebel x Einsatz)
    spread: float = 0.010          # Spread hin und zurueck, Anteil am Zertifikat
    trading_days: int = 252


def simulate(measured: pd.DataFrame, prepared: dict[str, pd.DataFrame], *,
             leverage: float, horizon: int,
             costs: CostModel | None = None) -> pd.DataFrame:
    """Haelt ein Zertifikat in Ereignisrichtung ``horizon`` Tage lang.

    Einstieg zum Schlusskurs des Ereignistages, Ausstieg ``horizon``
    Handelstage spaeter -- oder vorher per Knock-out.
    """
    costs = costs or CostModel()
    barrier_distance = 1.0 / leverage
    records = []

    for record in measured.itertuples(index=False):
        frame = prepared[record.symbol]
        row = int(record.row)
        exit_row = row + horizon
        if exit_row >= len(frame):
            continue

        entry = frame.at[row, "close"]
        if not entry or entry <= 0:
            continue
        side = int(record.side)

        if side > 0:
            barrier = entry * (1.0 - barrier_distance)
        else:
            barrier = entry * (1.0 + barrier_distance)

        # Tag fuer Tag pruefen, ob die Schwelle unterwegs beruehrt wurde.
        # Erst ab row+1: am Ereignistag sind wir zum Schluss eingestiegen.
        knocked_day = 0
        window = frame.iloc[row + 1: exit_row + 1]
        for offset, bar in enumerate(window.itertuples(index=False), start=1):
            touched = bar.low <= barrier if side > 0 else bar.high >= barrier
            if touched:
                knocked_day = offset
                break

        underlying = (frame.at[exit_row, "close"] / entry - 1.0) * side
        held_days = knocked_day if knocked_day else horizon
        financing = leverage * costs.financing_rate / costs.trading_days * held_days

        if knocked_day:
            payoff = -1.0  # Totalverlust des Einsatzes
        else:
            payoff = leverage * underlying - financing - costs.spread
            payoff = max(payoff, -1.0)  # mehr als den Einsatz kann man nicht verlieren

        records.append(
            {
                "symbol": record.symbol,
                "date": record.date,
                "side": side,
                "underlying_%": underlying * 100,
                "knocked_out": bool(knocked_day),
                "knock_tag": knocked_day or np.nan,
                "ergebnis_%": payoff * 100,
                "richtung_stimmte": underlying > 0,
            }
        )

    return pd.DataFrame(records)


def sweep(measured: pd.DataFrame, prepared: dict[str, pd.DataFrame], *,
          horizon: int = 5, leverages: tuple[float, ...] = LEVERAGES,
          costs: CostModel | None = None) -> pd.DataFrame:
    """Dieselbe Ereignismenge ueber verschiedene Hebelstufen."""
    rows = []
    for leverage in leverages:
        trades = simulate(measured, prepared, leverage=leverage,
                          horizon=horizon, costs=costs)
        if trades.empty:
            continue

        correct = trades[trades["richtung_stimmte"]]
        # Die entscheidende Zahl: Richtung war richtig -- und trotzdem ausgeknockt.
        wasted = (correct["knocked_out"].mean() * 100
                  if not correct.empty else np.nan)

        rows.append(
            {
                "hebel": leverage,
                "schwelle_%": 100.0 / leverage,
                "n": len(trades),
                "ausgeknockt_%": trades["knocked_out"].mean() * 100,
                "richtig_und_raus_%": wasted,
                "mittel_%": trades["ergebnis_%"].mean(),
                "median_%": trades["ergebnis_%"].median(),
                "totalverlust_%": (trades["ergebnis_%"] <= -99).mean() * 100,
            }
        )
    return pd.DataFrame(rows)


def growth(trades_mean_pct: float, n_trades: int) -> float:
    """Kapitalentwicklung bei gleichbleibendem Einsatz pro Trade (grob)."""
    return (1.0 + trades_mean_pct / 100.0) ** n_trades


def wealth_analysis(results: pd.DataFrame, fractions: tuple[float, ...] = (1.0, 0.5, 0.2, 0.1, 0.05),
                    seed: int = 3, draws: int = 2000) -> pd.DataFrame:
    """Was passiert mit dem Kapital, wenn man diese Trades wirklich hintereinander macht.

    Der arithmetische Mittelwert taeuscht bei Totalverlust-Risiken gewaltig: Ein
    einziger Verdreissigfacher hebt ihn ueber null, waehrend fast jeder einzelne
    Pfad im Ruin endet. Massgeblich ist die geometrische Rendite, also das, was
    das Kapital tatsaechlich macht, wenn Trade auf Trade folgt.
    """
    payoffs = results["ergebnis_%"].to_numpy() / 100.0
    if payoffs.size == 0:
        return pd.DataFrame()

    rng = np.random.default_rng(seed)
    rows = []
    for fraction in fractions:
        multipliers = 1.0 + fraction * payoffs
        # Bei vollem Einsatz ist der Totalverlust absorbierend.
        multipliers = np.clip(multipliers, 1e-12, None)
        log_growth = np.log(multipliers)

        # 100 Trades hintereinander, viele Male gewuerfelt.
        sample = rng.choice(log_growth, size=(draws, 100), replace=True).sum(axis=1)
        terminal = np.exp(sample)
        rows.append(
            {
                "einsatz_je_trade": f"{fraction:.0%}",
                "arith_mittel_%": payoffs.mean() * 100 * fraction,
                "geom_je_trade_%": (np.exp(log_growth.mean()) - 1) * 100,
                "median_nach_100_trades": float(np.median(terminal)),
                "anteil_ruin_%": float((terminal < 0.01).mean() * 100),
                "anteil_im_plus_%": float((terminal > 1.0).mean() * 100),
            }
        )
    return pd.DataFrame(rows)


def bootstrap_mean(results: pd.DataFrame, draws: int = 5000, seed: int = 11) -> dict:
    """Vertrauensintervall fuer den Mittelwert -- bei schiefen Verteilungen noetig."""
    payoffs = results["ergebnis_%"].to_numpy()
    if payoffs.size == 0:
        return {}
    rng = np.random.default_rng(seed)
    means = rng.choice(payoffs, size=(draws, payoffs.size), replace=True).mean(axis=1)
    return {
        "mittel_%": float(payoffs.mean()),
        "ci_unten_%": float(np.percentile(means, 2.5)),
        "ci_oben_%": float(np.percentile(means, 97.5)),
    }
