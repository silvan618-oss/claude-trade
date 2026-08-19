"""Mehrere Zeitebenen gleichzeitig auswerten (15m / 1h / 1d).

Die zu pruefende Behauptung lautet: Wenn mehrere Zeitebenen dasselbe sagen, ist
das Signal belastbarer als auf einer einzelnen.

Der Fallstrick dabei ist immer derselbe. Um 14:00 Uhr steht die Tageskerze noch
nicht fest -- sie schliesst erst am Abend. Wer trotzdem ihren Trend abliest,
benutzt Wissen aus der Zukunft und bekommt Ergebnisse, die live nicht
existieren. Deshalb bekommt hier jeder Balken einen Zeitpunkt, ab dem er
ueberhaupt bekannt ist, und hoehere Zeitebenen werden ausschliesslich ueber
diesen Zeitpunkt angebunden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Wie lange ein Balken laeuft -- daraus ergibt sich, wann er fertig ist.
BAR_DURATION = {
    "1m": pd.Timedelta(minutes=1),
    "5m": pd.Timedelta(minutes=5),
    "15m": pd.Timedelta(minutes=15),
    "30m": pd.Timedelta(minutes=30),
    "1h": pd.Timedelta(hours=1),
    # Eine Tageskerze traegt den Zeitstempel 00:00 UTC, ist aber erst nach
    # US-Handelsschluss (20:00 UTC) bekannt. Wir runden konservativ auf.
    "1d": pd.Timedelta(hours=21),
}

DEFAULT_FAST, DEFAULT_SLOW = 12, 26


def add_trend(frame: pd.DataFrame, interval: str, *,
              fast: int = DEFAULT_FAST, slow: int = DEFAULT_SLOW) -> pd.DataFrame:
    """Trendrichtung je Balken plus den Zeitpunkt, ab dem sie bekannt ist.

    ``state``        +1 wenn der schnelle Durchschnitt ueber dem langsamen liegt
    ``available_at`` wann dieser Balken abgeschlossen und damit auswertbar war
    """
    if interval not in BAR_DURATION:
        raise ValueError(f"unbekannte Aufloesung {interval!r}")

    out = frame.copy().sort_values("date").reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"], utc=True)

    ema_fast = out["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = out["close"].ewm(span=slow, adjust=False).mean()

    state = np.where(ema_fast > ema_slow, 1, -1).astype(float)
    # Vor dem langsamen Fenster ist der Trend nicht definiert.
    state[: slow] = np.nan
    out["state"] = state
    out["ema_spread"] = (ema_fast - ema_slow) / out["close"]
    out["available_at"] = out["date"] + BAR_DURATION[interval]
    return out


def align(base: pd.DataFrame, base_interval: str,
          higher: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Haengt die Trends hoeherer Zeitebenen an die Basiszeitebene an.

    Verbunden wird ueber ``available_at``: Zu jedem Basisbalken wird der letzte
    hoehere Balken gesucht, der zu diesem Zeitpunkt bereits geschlossen war.
    Damit ist Zukunftswissen strukturell ausgeschlossen, nicht nur per Konvention.
    """
    merged = add_trend(base, base_interval).sort_values("available_at").reset_index(drop=True)

    for interval, frame in higher.items():
        trend = add_trend(frame, interval)
        trend = (
            trend[["available_at", "state", "ema_spread"]]
            .dropna(subset=["state"])
            .sort_values("available_at")
            .rename(columns={"state": f"state_{interval}",
                             "ema_spread": f"spread_{interval}"})
        )
        merged = pd.merge_asof(
            merged, trend, on="available_at", direction="backward", allow_exact_matches=True
        )

    merged = merged.rename(columns={"state": f"state_{base_interval}",
                                    "ema_spread": f"spread_{base_interval}"})
    return merged


def confluence(aligned: pd.DataFrame, intervals: tuple[str, ...]) -> pd.DataFrame:
    """Zaehlt, wie viele Zeitebenen in dieselbe Richtung zeigen."""
    columns = [f"state_{i}" for i in intervals]
    missing = [c for c in columns if c not in aligned.columns]
    if missing:
        raise KeyError(f"fehlende Trendspalten: {missing}")

    out = aligned.copy()
    states = out[columns]
    out["n_zeitebenen"] = states.notna().sum(axis=1)
    out["score"] = states.sum(axis=1, min_count=1)
    # Volle Einigkeit heisst: alle vorhandenen Zeitebenen zeigen gleich.
    out["einig"] = states.abs().sum(axis=1).eq(out["score"].abs()) & out["n_zeitebenen"].eq(len(columns))
    out["richtung"] = np.sign(out["score"])
    return out


def forward_returns(aligned: pd.DataFrame, horizons: tuple[int, ...] = (1, 4, 8, 24)) -> pd.DataFrame:
    """Vorwaertsrenditen in Balken der Basiszeitebene, ab deren Schlusskurs."""
    out = aligned.copy()
    for h in horizons:
        out[f"fwd_{h}"] = out["close"].shift(-h) / out["close"] - 1.0
        # In Signalrichtung vorzeichenbereinigt: positiv = Trend ging weiter.
        out[f"sig_{h}"] = out[f"fwd_{h}"] * out["richtung"]
    return out


def by_confluence(measured: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Ergebnis nach Grad der Einigkeit zwischen den Zeitebenen."""
    column = f"sig_{horizon}"
    frame = measured.dropna(subset=[column, "score"]).copy()
    # Bei Gleichstand gibt es keine Richtung -- solche Balken sind kein Signal
    # und duerfen nicht als Nullergebnis in die Statistik wandern.
    frame = frame[frame["richtung"] != 0]
    if frame.empty:
        return pd.DataFrame()

    frame["tag"] = frame["date"].dt.date
    rows = []
    for score, group in frame.groupby(frame["score"].abs(), sort=True):
        values = group[column]
        # Nach Tag clustern: aufeinanderfolgende Intraday-Balken sind praktisch
        # dieselbe Beobachtung, sonst wird der t-Wert absurd gross.
        daily = group.groupby("tag")[column].mean()
        t_clustered = (
            float(daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily))))
            if len(daily) > 2 and daily.std(ddof=1) > 0 else np.nan
        )
        rows.append({
            "einigkeit": int(score),
            "n": len(values),
            "n_tage": group["tag"].nunique(),
            "mittel_bp": values.mean() * 10_000,
            "trefferquote_%": (values > 0).mean() * 100,
            "t_geclustert": t_clustered,
        })
    return pd.DataFrame(rows)


def signal_correlation(aligned: pd.DataFrame, intervals: tuple[str, ...]) -> pd.DataFrame:
    """Wie stark haengen die Zeitebenen voneinander ab?

    Das ist die eigentliche Frage hinter der Multi-Timeframe-Idee: Drei Ebenen,
    die dasselbe sagen, sind nur dann eine dreifache Bestaetigung, wenn sie
    unabhaengig voneinander sind. Sind sie hoch korreliert, ist es eine einzige
    Information, die dreimal abgelesen wurde.
    """
    columns = [f"state_{i}" for i in intervals]
    return aligned[columns].dropna().corr()
