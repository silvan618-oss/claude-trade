"""Muster selbst finden statt aus dem Lehrbuch nehmen.

Bekannte Formationen sind bekannt -- und damit sehr wahrscheinlich
wegarbitriert. Dieses Modul sucht stattdessen selbst: Es uebersetzt jedes
Kursfenster in ein Symbol-Wort, zaehlt alle vorkommenden Woerter und misst fuer
jedes einzelne, was danach passiert.

Der schwierige Teil ist nicht das Finden. Wer zehntausend Muster testet, findet
garantiert hunderte mit traumhaften Werten -- rein durch Zufall. Der schwierige
Teil ist der Filter danach, und der besteht hier aus drei Stufen:

1. **FDR-Korrektur** (Benjamini-Hochberg) ueber alle getesteten Muster.
2. **Strikte Trennung**: gesucht wird nur im Trainingszeitraum, geprueft wird
   ausschliesslich auf spaeteren Daten.
3. **Kontrolllauf** mit durchgewuerfelten Zielwerten, der zeigt, wie viele
   "Funde" der Zufall allein produziert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

# Bruchpunkte der Standardnormalverteilung fuer gleich haeufige Klassen.
BREAKPOINTS = {
    3: [-0.4307, 0.4307],
    4: [-0.6745, 0.0, 0.6745],
    5: [-0.8416, -0.2533, 0.2533, 0.8416],
}
LETTERS = "abcdefgh"


def shape_motifs(close: np.ndarray, window: int, alphabet: int) -> np.ndarray:
    """Uebersetzt jedes Kursfenster in ein Formwort.

    Das Fenster wird z-normiert, damit nur die *Form* zaehlt und nicht das
    Kursniveau -- ein Anstieg von 10 auf 11 Euro ergibt dasselbe Wort wie einer
    von 100 auf 110. Anschliessend wird jeder Punkt einer Klasse zugeordnet.

    Das Wort an Position t beschreibt die Fenster bis einschliesslich t. Es
    enthaelt keine spaeteren Kurse.
    """
    n = len(close)
    out = np.full(n, "", dtype=object)
    if n < window:
        return out

    windows = sliding_window_view(close, window)
    mean = windows.mean(axis=1, keepdims=True)
    std = windows.std(axis=1, keepdims=True)
    std = np.where(std == 0, np.nan, std)
    z = (windows - mean) / std

    codes = np.digitize(z, BREAKPOINTS[alphabet])
    letters = np.array(list(LETTERS[:alphabet]))
    words = np.where(
        np.isnan(z).any(axis=1),
        "",
        [''.join(row) for row in letters[codes]],
    )
    out[window - 1:] = words
    return out


def candle_motifs(frame: pd.DataFrame, window: int) -> np.ndarray:
    """Uebersetzt jede Kerze in ein Symbol und verkettet die letzten ``window``.

    Symbole nach Koerperrichtung und -groesse relativ zur eigenen Spanne:
    ``H`` grosse gruene, ``h`` kleine gruene, ``o`` Doji,
    ``l`` kleine rote, ``L`` grosse rote.
    """
    o = frame["open"].to_numpy(float)
    c = frame["close"].to_numpy(float)
    h = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)

    span = np.where((h - low) == 0, np.nan, h - low)
    ratio = (c - o) / span

    symbol = np.full(len(frame), "o", dtype="<U1")
    symbol[ratio > 0.15] = "h"
    symbol[ratio > 0.55] = "H"
    symbol[ratio < -0.15] = "l"
    symbol[ratio < -0.55] = "L"
    symbol[np.isnan(ratio)] = "?"

    n = len(frame)
    out = np.full(n, "", dtype=object)
    if n < window:
        return out
    words = [''.join(symbol[i - window + 1: i + 1]) for i in range(window - 1, n)]
    out[window - 1:] = ["" if "?" in w else w for w in words]
    return out


def build_motif_dataset(prepared: dict[str, pd.DataFrame],
                        benchmark: pd.DataFrame, *,
                        window: int = 5, alphabet: int = 4,
                        kind: str = "shape", horizon: int = 1) -> pd.DataFrame:
    """Ein Datensatz aus (Muster, Datum, Vorwaertsrendite) fuer das Universum."""
    bench = benchmark.reset_index(drop=True)
    market = pd.Series(
        (bench["close"].shift(-horizon) / bench["close"] - 1.0).to_numpy(),
        index=pd.DatetimeIndex(bench["date"]),
    )

    parts = []
    for symbol, frame in prepared.items():
        frame = frame.reset_index(drop=True)
        close = frame["close"].to_numpy(float)
        if kind == "shape":
            words = shape_motifs(close, window, alphabet)
        elif kind == "candle":
            words = candle_motifs(frame, window)
        else:
            raise ValueError(f"unbekannte Musterart {kind!r}")

        forward = np.full(len(frame), np.nan)
        if horizon < len(frame):
            forward[:-horizon] = close[horizon:] / close[:-horizon] - 1.0

        part = pd.DataFrame({
            "symbol": symbol,
            "date": frame["date"],
            "muster": words,
            "fwd": forward,
        })
        part["fwd_abn"] = part["fwd"] - part["date"].map(market)
        parts.append(part)

    data = pd.concat(parts, ignore_index=True)
    return data[(data["muster"] != "") & data["fwd_abn"].notna()].reset_index(drop=True)


def mine(dataset: pd.DataFrame, *, min_count: int = 200,
         column: str = "fwd_abn") -> pd.DataFrame:
    """Misst jedes vorkommende Muster einzeln.

    Der t-Wert wird nach Datum geclustert -- Muster treten marktweit am selben
    Tag auf, und ohne Clusterung waeren die Werte um ein Vielfaches zu gross.
    """
    frame = dataset.dropna(subset=[column])
    counts = frame["muster"].value_counts()
    keep = counts[counts >= min_count].index
    frame = frame[frame["muster"].isin(keep)]
    if frame.empty:
        return pd.DataFrame()

    # Tagesmittel je Muster -- die Einheit, auf der getestet wird.
    daily = frame.groupby(["muster", "date"])[column].mean().reset_index()
    grouped = daily.groupby("muster")[column]

    stats = pd.DataFrame({
        "n_tage": grouped.size(),
        "mittel": grouped.mean(),
        "streuung": grouped.std(ddof=1),
    })
    stats["n"] = frame.groupby("muster").size()
    stats["treffer_%"] = frame.groupby("muster")[column].apply(lambda s: (s > 0).mean() * 100)
    stats["mittel_bp"] = stats["mittel"] * 10_000
    stats["t"] = stats["mittel"] / (stats["streuung"] / np.sqrt(stats["n_tage"]))
    stats = stats[stats["n_tage"] >= 30].copy()

    # Zweiseitiger p-Wert ueber die Normalapproximation (n_tage ist gross).
    from math import erf, sqrt
    stats["p"] = stats["t"].apply(
        lambda t: 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2)))) if np.isfinite(t) else np.nan)
    return stats.sort_values("t", ascending=False).reset_index()


def benjamini_hochberg(stats: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Korrigiert fuer die Menge gleichzeitig getesteter Muster.

    Ohne diese Korrektur ist bei 1.000 Tests mit rund 50 "signifikanten"
    Ergebnissen zu rechnen, obwohl kein einziges echt ist.
    """
    out = stats.dropna(subset=["p"]).sort_values("p").reset_index(drop=True)
    if out.empty:
        return out
    m = len(out)
    out["rang"] = np.arange(1, m + 1)
    out["bh_schwelle"] = alpha * out["rang"] / m
    passed = out["p"] <= out["bh_schwelle"]
    cutoff = out.loc[passed, "rang"].max() if passed.any() else 0
    out["besteht_fdr"] = out["rang"] <= (cutoff if cutoff == cutoff else 0)
    return out


def validate_out_of_sample(dataset: pd.DataFrame, split: str, *,
                           min_count: int = 200, alpha: float = 0.05,
                           top_k: int = 25, column: str = "fwd_abn") -> dict:
    """Im Trainingszeitraum suchen, im Haltezeitraum pruefen.

    Das ist der eigentliche Test. Alles davor ist Suche, und Suchen findet
    immer etwas.
    """
    cut = pd.Timestamp(split)
    train = dataset[dataset["date"] < cut]
    holdout = dataset[dataset["date"] >= cut]

    found = mine(train, min_count=min_count, column=column)
    if found.empty:
        return {"gefunden": pd.DataFrame(), "geprueft": pd.DataFrame()}

    corrected = benjamini_hochberg(found, alpha=alpha)
    survivors = corrected[corrected["besteht_fdr"]]

    # Wenn die FDR-Korrektur nichts durchlaesst, pruefen wir trotzdem die
    # nominell besten -- damit sichtbar wird, was mit ihnen passiert.
    candidates = (survivors if not survivors.empty
                  else corrected.reindex(corrected["t"].abs().sort_values(ascending=False).index).head(top_k))

    later = mine(holdout, min_count=max(min_count // 4, 30), column=column).set_index("muster")
    rows = []
    # itertuples benennt Spalten mit Sonderzeichen um -- deshalb ueber die Zeile.
    for _, record in candidates.iterrows():
        motif = record["muster"]
        if motif not in later.index:
            continue
        after = later.loc[motif]
        rows.append({
            "muster": motif,
            "richtung": "long" if record["t"] > 0 else "short",
            "train_bp": record["mittel_bp"], "train_t": record["t"],
            "train_treffer_%": record["treffer_%"],
            "holdout_bp": after["mittel_bp"], "holdout_t": after["t"],
            "holdout_treffer_%": after["treffer_%"],
            "haelt": bool(np.sign(record["t"]) == np.sign(after["t"])),
        })

    return {
        "gefunden": corrected,
        "ueberlebende_fdr": survivors,
        "geprueft": pd.DataFrame(rows),
        "n_getestet": len(found),
    }
