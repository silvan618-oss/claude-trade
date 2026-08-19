"""Kerzenmuster und Chartformationen erkennen und einzeln vermessen.

Nicht "was macht der Durchschnitt aller Kerzen", sondern: Wenn genau DIESES
Muster auftritt -- was macht die naechste Kerze dann?

Jedes Muster wird gegen die Basisrate gemessen, nicht gegen 50 Prozent. Aktien
steigen an rund 52 Prozent aller Tage. Ein Muster mit 52 Prozent Trefferquote
sagt also nichts aus, es ist der Normalzustand.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def anatomy(frame: pd.DataFrame) -> pd.DataFrame:
    """Zerlegt jede Kerze in Koerper, Dochte und Lage."""
    out = frame.copy().reset_index(drop=True)
    o, h, l, c = out["open"], out["high"], out["low"], out["close"]

    out["koerper"] = (c - o).abs()
    out["spanne"] = (h - l).replace(0, np.nan)
    out["docht_oben"] = h - np.maximum(o, c)
    out["docht_unten"] = np.minimum(o, c) - l
    out["gruen"] = c > o
    out["rot"] = c < o
    out["koerper_anteil"] = out["koerper"] / out["spanne"]

    # Trendkontext: wo steht der Kurs relativ zum eigenen Durchschnitt.
    sma20 = c.rolling(20).mean()
    out["im_abwaertstrend"] = c < sma20
    out["im_aufwaertstrend"] = c > sma20
    out["hoch_20"] = h.rolling(20).max()
    out["tief_20"] = l.rolling(20).min()
    return out


def _shift_ok(series: pd.Series, n: int) -> pd.Series:
    return series.shift(n).fillna(False).astype(bool)


def detect_patterns(frame: pd.DataFrame) -> pd.DataFrame:
    """Alle Muster als Spalten mit True/False je Kerze.

    Konvention: Das Muster gilt als am Tag t abgeschlossen. Bewertet wird, was
    an Tag t+1 passiert. Es fliesst nichts ein, was am Tag t nicht bekannt war.
    """
    a = anatomy(frame)
    o, h, l, c = a["open"], a["high"], a["low"], a["close"]
    body, span = a["koerper"], a["spanne"]
    gruen, rot = a["gruen"], a["rot"]

    p: dict[str, pd.Series] = {}

    # --- Einzelkerzen ---
    p["doji"] = a["koerper_anteil"] < 0.10
    p["hammer"] = (
        (a["docht_unten"] >= 2 * body) & (a["docht_oben"] <= body)
        & (a["koerper_anteil"] < 0.4) & a["im_abwaertstrend"]
    )
    p["shooting_star"] = (
        (a["docht_oben"] >= 2 * body) & (a["docht_unten"] <= body)
        & (a["koerper_anteil"] < 0.4) & a["im_aufwaertstrend"]
    )
    p["marubozu_bull"] = gruen & (a["koerper_anteil"] > 0.9)
    p["marubozu_bear"] = rot & (a["koerper_anteil"] > 0.9)

    # --- Zwei Kerzen ---
    prev_o, prev_c = o.shift(1), c.shift(1)
    prev_body_top = np.maximum(prev_o, prev_c)
    prev_body_bot = np.minimum(prev_o, prev_c)

    p["bullish_engulfing"] = (
        _shift_ok(rot, 1) & gruen & (o <= prev_body_bot) & (c >= prev_body_top)
    )
    p["bearish_engulfing"] = (
        _shift_ok(gruen, 1) & rot & (o >= prev_body_top) & (c <= prev_body_bot)
    )
    p["bullish_harami"] = (
        _shift_ok(rot, 1) & gruen & (o >= prev_body_bot) & (c <= prev_body_top)
        & (body < body.shift(1))
    )
    p["bearish_harami"] = (
        _shift_ok(gruen, 1) & rot & (o >= prev_body_bot) & (c <= prev_body_top)
        & (body < body.shift(1))
    )
    p["piercing_line"] = (
        _shift_ok(rot, 1) & gruen & (o < c.shift(1))
        & (c > (prev_o + prev_c) / 2) & (c < prev_o)
    )
    p["dark_cloud"] = (
        _shift_ok(gruen, 1) & rot & (o > c.shift(1))
        & (c < (prev_o + prev_c) / 2) & (c > prev_o)
    )
    p["tweezer_bottom"] = (
        a["im_abwaertstrend"] & ((l - l.shift(1)).abs() / c < 0.002) & gruen
    )
    p["tweezer_top"] = (
        a["im_aufwaertstrend"] & ((h - h.shift(1)).abs() / c < 0.002) & rot
    )
    p["inside_bar"] = (h < h.shift(1)) & (l > l.shift(1))
    p["outside_bar"] = (h > h.shift(1)) & (l < l.shift(1))

    # --- Drei Kerzen ---
    p["morning_star"] = (
        _shift_ok(rot, 2) & (body.shift(2) / span.shift(2) > 0.5)
        & (a["koerper_anteil"].shift(1) < 0.35)
        & gruen & (c > (o.shift(2) + c.shift(2)) / 2)
    )
    p["evening_star"] = (
        _shift_ok(gruen, 2) & (body.shift(2) / span.shift(2) > 0.5)
        & (a["koerper_anteil"].shift(1) < 0.35)
        & rot & (c < (o.shift(2) + c.shift(2)) / 2)
    )
    p["three_white_soldiers"] = (
        gruen & _shift_ok(gruen, 1) & _shift_ok(gruen, 2)
        & (c > c.shift(1)) & (c.shift(1) > c.shift(2))
    )
    p["three_black_crows"] = (
        rot & _shift_ok(rot, 1) & _shift_ok(rot, 2)
        & (c < c.shift(1)) & (c.shift(1) < c.shift(2))
    )

    # --- Ausbrueche und Gaps ---
    p["breakout_20d_hoch"] = c > a["hoch_20"].shift(1)
    p["breakdown_20d_tief"] = c < a["tief_20"].shift(1)
    p["gap_up"] = o / c.shift(1) - 1 > 0.02
    p["gap_down"] = o / c.shift(1) - 1 < -0.02

    # --- Doppeltop / Doppelboden ueber lokale Extrema ---
    p["double_top"] = _double_extreme(h, c, top=True)
    p["double_bottom"] = _double_extreme(l, c, top=False)

    result = pd.DataFrame({k: v.fillna(False).astype(bool) for k, v in p.items()})
    result.insert(0, "date", a["date"])
    result.insert(1, "close", c)
    return result


def _double_extreme(extreme: pd.Series, close: pd.Series, *, top: bool,
                    window: int = 10, tolerance: float = 0.02) -> pd.Series:
    """Zwei aehnlich hohe Hochs (bzw. Tiefs) mit einem Tal dazwischen.

    Bewusst simpel gehalten: Der aktuelle Balken bildet ein lokales Extrem, und
    innerhalb der letzten ``window`` Balken gab es schon eines auf gleichem
    Niveau. Alles nur aus zurueckliegenden Daten.
    """
    if top:
        is_local = extreme == extreme.rolling(5, center=False).max()
        prior = extreme.shift(5).rolling(window).max()
    else:
        is_local = extreme == extreme.rolling(5, center=False).min()
        prior = extreme.shift(5).rolling(window).min()

    similar = (extreme - prior).abs() / close.replace(0, np.nan) < tolerance
    return (is_local & similar).fillna(False)


PATTERN_NAMES = [
    "doji", "hammer", "shooting_star", "marubozu_bull", "marubozu_bear",
    "bullish_engulfing", "bearish_engulfing", "bullish_harami", "bearish_harami",
    "piercing_line", "dark_cloud", "tweezer_bottom", "tweezer_top",
    "inside_bar", "outside_bar", "morning_star", "evening_star",
    "three_white_soldiers", "three_black_crows",
    "breakout_20d_hoch", "breakdown_20d_tief", "gap_up", "gap_down",
    "double_top", "double_bottom",
]

# Welche Richtung die Lehrbuecher dem Muster zuschreiben.
BULLISH = {
    "hammer", "marubozu_bull", "bullish_engulfing", "bullish_harami",
    "piercing_line", "tweezer_bottom", "morning_star", "three_white_soldiers",
    "breakout_20d_hoch", "gap_up", "double_bottom",
}
BEARISH = {
    "shooting_star", "marubozu_bear", "bearish_engulfing", "bearish_harami",
    "dark_cloud", "tweezer_top", "evening_star", "three_black_crows",
    "breakdown_20d_tief", "gap_down", "double_top",
}


def build_pattern_dataset(prepared: dict[str, pd.DataFrame],
                          horizon: int = 1,
                          benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    """Muster ueber das ganze Universum, mit der Rendite der naechsten Kerze(n).

    Wird ein Benchmark uebergeben, kommt zusaetzlich ``fwd_abn`` dazu: dieselbe
    Rendite abzueglich Marktbewegung. Das ist zwingend, sobald baerische Muster
    mitgemessen werden -- eine Short-Position verliert in einem steigenden Markt
    schon deshalb, weil der Markt steigt, nicht wegen des Musters.
    """
    market = None
    if benchmark is not None:
        bench = benchmark.reset_index(drop=True)
        market = pd.Series(
            (bench["close"].shift(-horizon) / bench["close"] - 1.0).to_numpy(),
            index=pd.DatetimeIndex(bench["date"]),
        )

    parts = []
    for symbol, frame in prepared.items():
        found = detect_patterns(frame)
        found["symbol"] = symbol
        close = found["close"]
        found["fwd"] = close.shift(-horizon) / close - 1.0
        if market is not None:
            found["fwd_abn"] = found["fwd"] - found["date"].map(market)
        parts.append(found)
    return pd.concat(parts, ignore_index=True).dropna(subset=["fwd"])


def evaluate(dataset: pd.DataFrame,
             names: list[str] | None = None,
             column: str = "fwd") -> pd.DataFrame:
    """Trefferquote und Rendite je Muster, gegen die Basisrate gemessen.

    ``column="fwd_abn"`` rechnet marktbereinigt -- die ehrliche Variante, sobald
    baerische Muster dabei sind.
    """
    names = names or PATTERN_NAMES
    dataset = dataset.dropna(subset=[column])
    base_rate = (dataset[column] > 0).mean() * 100
    base_mean = dataset[column].mean() * 10_000

    rows = []
    for name in names:
        if name not in dataset.columns:
            continue
        hits = dataset[dataset[name]]
        if len(hits) < 50:
            continue

        direction = 1 if name in BULLISH else (-1 if name in BEARISH else 1)
        signed = hits[column] * direction

        # Nach Datum clustern: Muster treten marktweit am selben Tag auf.
        daily = signed.groupby(hits["date"]).mean()
        t = (float(daily.mean() / (daily.std(ddof=1) / np.sqrt(len(daily))))
             if len(daily) > 2 and daily.std(ddof=1) > 0 else np.nan)

        rows.append({
            "muster": name,
            "richtung": "bullish" if direction > 0 else "bearish",
            "n": len(hits),
            "n_tage": hits["date"].nunique(),
            "treffer_%": (signed > 0).mean() * 100,
            "vs_basis_pp": (signed > 0).mean() * 100 - (base_rate if direction > 0
                                                        else 100 - base_rate),
            "mittel_bp": signed.mean() * 10_000,
            "t_geclustert": t,
        })

    result = pd.DataFrame(rows).sort_values("t_geclustert", ascending=False)
    result.attrs["basisrate_%"] = base_rate
    result.attrs["basis_bp"] = base_mean
    return result
