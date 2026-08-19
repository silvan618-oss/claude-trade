"""Ereignisse aus Kurs- und Volumendaten ableiten.

Ein Ereignis ist hier: ein grosser Ueberacht-Gap zusammen mit auffaellig hohem
Handelsvolumen. Das ist ein Stellvertreter fuer "es gab wichtige Nachrichten zu
dieser Firma" -- ohne dass wir eine Nachrichtendatenbank brauchen. Der Gap misst
die Reaktion auf alles, was ausserhalb der Handelszeit passiert ist: Quartals-
zahlen, Uebernahmen, Zulassungen, Gewinnwarnungen, Weltereignisse.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

VOLUME_LOOKBACK = 60


@dataclass(frozen=True)
class EventConfig:
    """Schwellen fuer die Ereigniserkennung."""
    min_gap: float = 0.04        # mind. 4 % Ueberacht-Bewegung
    min_volume_ratio: float = 2.0  # mind. doppeltes Volumen ggue. Normalniveau
    min_price: float = 5.0       # Pennystocks raus
    direction: str = "both"      # "up", "down" oder "both"


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Rechnet OHLC auf Splits und Dividenden um und ergaenzt Kennzahlen.

    Yahoo liefert ``adjclose`` bereinigt, ``open``/``high``/``low``/``close`` aber
    roh. Wer das mischt, sieht bei jedem Aktiensplit einen gewaltigen Fake-Gap --
    ein 4:1-Split saehe aus wie ein Kurssturz von 75 Prozent. Wir skalieren
    deshalb alle vier Kurse mit demselben Faktor ``adjclose / close``.
    """
    if "gap" in frame.columns and "volume_ratio" in frame.columns:
        return frame  # schon vorbereitet, nicht zweimal umrechnen

    out = frame.copy().sort_values("date").reset_index(drop=True)

    factor = out["adjclose"] / out["close"]
    for column in ("open", "high", "low"):
        out[column] = out[column] * factor
    out["close"] = out["adjclose"]

    prev_close = out["close"].shift(1)
    out["prev_close"] = prev_close
    # Ueberacht-Gap: was zwischen gestern Schluss und heute Eroeffnung passiert ist.
    out["gap"] = out["open"] / prev_close - 1.0
    # Tagesbewegung nach Eroeffnung: der Teil, den man theoretisch noch mitnimmt.
    out["intraday"] = out["close"] / out["open"] - 1.0
    out["ret"] = out["close"] / prev_close - 1.0

    median_volume = (
        out["volume"].shift(1).rolling(VOLUME_LOOKBACK, min_periods=20).median()
    )
    out["volume_ratio"] = out["volume"] / median_volume.replace(0, np.nan)

    # Vorlaufende Volatilitaet -- ausschliesslich aus der Vergangenheit, damit
    # sich keine Zukunftsinformation einschleicht.
    out["vol_20d"] = out["ret"].shift(1).rolling(20, min_periods=10).std()
    return out


def prepare_all(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Bereitet das ganze Universum einmal auf, statt bei jedem Zugriff neu."""
    return {symbol: prepare(frame) for symbol, frame in frames.items()}


def detect(frame: pd.DataFrame, symbol: str,
           config: EventConfig | None = None) -> pd.DataFrame:
    """Findet alle Ereignisse in einer vorbereiteten Kursreihe."""
    config = config or EventConfig()
    prepared = prepare(frame)

    usable = (
        prepared["gap"].notna()
        & prepared["volume_ratio"].notna()
        & (prepared["prev_close"] >= config.min_price)
    )
    big_move = prepared["gap"].abs() >= config.min_gap
    busy = prepared["volume_ratio"] >= config.min_volume_ratio

    if config.direction == "up":
        directional = prepared["gap"] > 0
    elif config.direction == "down":
        directional = prepared["gap"] < 0
    else:
        directional = pd.Series(True, index=prepared.index)

    hits = prepared.index[usable & big_move & busy & directional]

    return pd.DataFrame(
        {
            "symbol": symbol,
            "date": prepared.loc[hits, "date"].to_numpy(),
            "row": hits.to_numpy(),
            "gap": prepared.loc[hits, "gap"].to_numpy(),
            "intraday": prepared.loc[hits, "intraday"].to_numpy(),
            "volume_ratio": prepared.loc[hits, "volume_ratio"].to_numpy(),
            "vol_20d": prepared.loc[hits, "vol_20d"].to_numpy(),
            "side": np.where(prepared.loc[hits, "gap"].to_numpy() > 0, 1, -1),
        }
    )


def detect_universe(frames: dict[str, pd.DataFrame],
                    config: EventConfig | None = None) -> pd.DataFrame:
    """Ereignisse ueber das gesamte Universum."""
    found = [detect(frame, symbol, config) for symbol, frame in frames.items()]
    found = [f for f in found if not f.empty]
    if not found:
        return pd.DataFrame(
            columns=["symbol", "date", "row", "gap", "intraday",
                     "volume_ratio", "vol_20d", "side"]
        )
    return pd.concat(found, ignore_index=True).sort_values("date").reset_index(drop=True)


def random_control(frames: dict[str, pd.DataFrame], n: int, *,
                   seed: int = 0, min_price: float = 5.0,
                   margin: int = 25) -> pd.DataFrame:
    """Kontrollgruppe: zufaellige Tage in denselben Aktien.

    Das ist der Falsifikator. Jede Auswertung laeuft zusaetzlich ueber diese
    Zufallstage. Wenn die echten Ereignisse nicht deutlich ausserhalb dessen
    liegen, was der Zufall ohnehin produziert, ist der gefundene Effekt keiner.
    """
    rng = np.random.default_rng(seed)
    symbols = sorted(frames)
    rows = []

    attempts = 0
    while len(rows) < n and attempts < n * 50:
        attempts += 1
        symbol = symbols[rng.integers(len(symbols))]
        prepared = prepare(frames[symbol])
        if len(prepared) < 2 * margin + 10:
            continue
        idx = int(rng.integers(margin, len(prepared) - margin))
        if not (prepared.at[idx, "prev_close"] >= min_price):
            continue
        if pd.isna(prepared.at[idx, "gap"]):
            continue
        rows.append(
            {
                "symbol": symbol,
                "date": prepared.at[idx, "date"],
                "row": idx,
                "gap": prepared.at[idx, "gap"],
                "intraday": prepared.at[idx, "intraday"],
                "volume_ratio": prepared.at[idx, "volume_ratio"],
                "vol_20d": prepared.at[idx, "vol_20d"],
                # Richtung wuerfeln: die Kontrollgruppe darf keine eingebaute
                # Richtungswette enthalten, sonst misst sie den Markttrend mit.
                "side": 1 if rng.random() < 0.5 else -1,
            }
        )

    return pd.DataFrame(rows)
