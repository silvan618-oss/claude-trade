"""Aktiv umschichten statt halten.

Die Faktorstudie in ``factors.py`` haelt Positionen und misst marktneutral. Das
ist die akademische Form der Frage und sie unterschlaegt zwei Dinge, die in der
Praxis den Unterschied machen: Man muss nicht ewig halten, und man muss nicht
gleichzeitig short gehen.

Dieses Modul rotiert stattdessen: Alle paar Wochen werden die Aktien mit dem
staerksten Signal gekauft und der Rest verkauft. Long only, konzentriert,
mit Umschichtkosten.

Der Massstab ist bewusst NICHT der Index, sondern eine Zufallsauswahl aus
demselben Universum. Nur so faellt der Survivorship Bias auf beiden Seiten
gleich aus -- ein Universum aus heutigen Firmen schlaegt den Index schon von
allein, ganz ohne Strategie.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

HANDELSTAGE_JAHR = 252


def price_matrix(prepared: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Ein gemeinsames Kursraster: Zeilen sind Tage, Spalten sind Aktien."""
    return pd.DataFrame(
        {symbol: frame.set_index("date")["close"] for symbol, frame in prepared.items()}
    ).sort_index()


def momentum(prices: pd.DataFrame, lookback: int = HANDELSTAGE_JAHR) -> pd.DataFrame:
    """Rendite ueber ``lookback`` Handelstage -- nur aus der Vergangenheit."""
    return prices / prices.shift(lookback) - 1.0


@dataclass(frozen=True)
class RotationConfig:
    n_halten: int = 15          # wie viele Aktien gleichzeitig
    rebalance_tage: int = 21    # wie oft umgeschichtet wird
    kosten_bp: float = 20.0     # Kosten je vollstaendig getauschter Position
    vorlauf: int = HANDELSTAGE_JAHR  # Balken, bevor gehandelt werden darf


def backtest(prices: pd.DataFrame, signal: pd.DataFrame,
             config: RotationConfig | None = None) -> pd.Series:
    """Kapitalkurve der Rotationsstrategie.

    An jedem Stichtag werden die ``n_halten`` Aktien mit dem hoechsten
    Signalwert gleichgewichtet gehalten. Umschichtkosten fallen nur auf den
    tatsaechlich getauschten Teil des Depots an.
    """
    config = config or RotationConfig()
    stichtage = prices.index[config.vorlauf:][::config.rebalance_tage]

    kapital = 1.0
    gehalten: set[str] = set()
    kurve: dict[pd.Timestamp, float] = {}

    for i, tag in enumerate(stichtage[:-1]):
        naechster = stichtage[i + 1]
        kandidaten = signal.loc[tag].dropna().sort_values(ascending=False)
        auswahl = list(kandidaten.index[: config.n_halten])

        if auswahl:
            rendite = (prices.loc[naechster, auswahl] / prices.loc[tag, auswahl] - 1).mean()
            rendite = 0.0 if np.isnan(rendite) else float(rendite)
            # Nur der ausgetauschte Teil kostet Gebuehren.
            umschlag = len(set(auswahl) ^ gehalten) / (2 * len(auswahl))
            rendite -= umschlag * config.kosten_bp / 10_000.0
        else:
            rendite = 0.0

        gehalten = set(auswahl)
        kapital *= 1.0 + rendite
        kurve[naechster] = kapital

    return pd.Series(kurve).sort_index()


def random_control(prices: pd.DataFrame, config: RotationConfig | None = None,
                   seed: int = 0) -> pd.Series:
    """Dieselbe Mechanik, aber die Aktien werden gewuerfelt.

    Das ist der einzig faire Massstab: gleiches Universum, gleiche Anzahl,
    gleiche Umschichtfrequenz, gleiche Kosten, gleiche Verzerrung -- nur ohne
    Signal. Was die Strategie darueber hinaus schafft, ist ihr Beitrag.
    """
    config = config or RotationConfig()
    rng = np.random.default_rng(seed)
    zufall = pd.DataFrame(
        rng.random(prices.shape), index=prices.index, columns=prices.columns
    ).where(prices.notna())
    return backtest(prices, zufall, config)


def buy_and_hold(prices: pd.DataFrame, ab: pd.Timestamp | None = None) -> pd.Series:
    """Alle Aktien gleichgewichtet halten, ohne Umschichten."""
    kurve = (1 + prices.pct_change().mean(axis=1).fillna(0)).cumprod()
    return kurve[kurve.index >= ab] if ab is not None else kurve


def kennzahlen(kurve: pd.Series, rebalance_tage: int = 21) -> dict:
    """Rendite, Drawdown und Sharpe -- korrekt auf die Umschichtfrequenz bezogen."""
    if kurve.empty or len(kurve) < 3:
        return {}
    jahre = (kurve.index[-1] - kurve.index[0]).days / 365.25
    renditen = kurve.pct_change().dropna()
    # Die Annualisierung muss der tatsaechlichen Periodenlaenge folgen; ein
    # fester Faktor blaeht den Sharpe bei seltenem Umschichten stark auf.
    perioden = HANDELSTAGE_JAHR / rebalance_tage
    streuung = renditen.std(ddof=1)
    return {
        "pro_jahr_%": ((kurve.iloc[-1] / kurve.iloc[0]) ** (1 / jahre) - 1) * 100,
        "faktor": float(kurve.iloc[-1] / kurve.iloc[0]),
        "max_drawdown_%": float((kurve / kurve.cummax() - 1).min() * 100),
        "sharpe": float(renditen.mean() / streuung * np.sqrt(perioden)) if streuung > 0 else np.nan,
    }
