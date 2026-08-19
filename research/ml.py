"""Mustererkennung: aus der Vergangenheit lernen, um die Zukunft zu prognostizieren.

Genau die Idee, um die es geht. Ein Modell bekommt alles, was am Tag t bekannt
ist, und soll vorhersagen, was am Tag t+1 passiert.

Zwei Regeln machen den Unterschied zwischen einer Messung und einer Selbst-
taeuschung:

1. **Jedes Merkmal muss am Tag t berechenbar sein.** Ein einziges Merkmal, das
   heimlich in die Zukunft schaut, erzeugt Trefferquoten von 90 Prozent, die
   live nicht existieren.
2. **Getestet wird ausschliesslich auf Daten nach dem Training.** Ein Modell auf
   denselben Daten zu bewerten, auf denen es gelernt hat, misst Auswendiglernen,
   nicht Koennen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

RETURN_LOOKBACKS = (1, 2, 3, 5, 10, 20, 60, 120)
VOL_LOOKBACKS = (5, 20, 60)
MA_LOOKBACKS = (20, 50, 200)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def build_features(prepared: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Merkmale fuer eine Aktie. Alles ausschliesslich rueckwaertsgerichtet."""
    frame = prepared.copy().reset_index(drop=True)
    close = frame["close"]
    out = pd.DataFrame({"symbol": symbol, "date": frame["date"], "close": close})

    for n in RETURN_LOOKBACKS:
        out[f"ret_{n}"] = close.pct_change(n)

    daily = close.pct_change()
    for n in VOL_LOOKBACKS:
        out[f"vol_{n}"] = daily.rolling(n).std()

    for n in MA_LOOKBACKS:
        out[f"ma_dist_{n}"] = close / close.rolling(n).mean() - 1.0

    out["rsi_14"] = _rsi(close)
    out["hoch_20"] = close / close.rolling(20).max() - 1.0
    out["tief_20"] = close / close.rolling(20).min() - 1.0

    # Volumen relativ zum eigenen Normalniveau -- shift(1), damit der heutige
    # Umsatz nicht den Massstab mitbestimmt, an dem er gemessen wird.
    median_volume = frame["volume"].shift(1).rolling(60, min_periods=20).median()
    out["vol_ratio"] = frame["volume"] / median_volume.replace(0, np.nan)

    out["gap"] = frame["open"] / close.shift(1) - 1.0
    out["spanne"] = (frame["high"] - frame["low"]) / close.shift(1)
    # Wo im Tagesbereich der Schluss liegt: 1 = am Hoch, 0 = am Tief.
    spread = (frame["high"] - frame["low"]).replace(0, np.nan)
    out["schluss_lage"] = (close - frame["low"]) / spread

    out["wochentag"] = pd.to_datetime(frame["date"]).dt.dayofweek
    out["monat"] = pd.to_datetime(frame["date"]).dt.month

    # ZIEL: die Rendite des NAECHSTEN Tages. Nur diese eine Zeile blickt nach
    # vorn, und sie ist das, was vorhergesagt werden soll -- kein Merkmal.
    out["ziel_rendite"] = close.shift(-1) / close - 1.0
    out["ziel_hoch"] = (out["ziel_rendite"] > 0).astype(int)
    return out


def build_dataset(prepared: dict[str, pd.DataFrame],
                  benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    """Merkmale ueber das gesamte Universum, plus Marktkontext und Querschnittsraenge."""
    parts = [build_features(frame, symbol) for symbol, frame in prepared.items()]
    data = pd.concat(parts, ignore_index=True)

    if benchmark is not None:
        bench = benchmark.copy().reset_index(drop=True)
        market = pd.DataFrame({
            "date": bench["date"],
            "markt_ret_1": bench["close"].pct_change(1),
            "markt_ret_5": bench["close"].pct_change(5),
            "markt_ret_20": bench["close"].pct_change(20),
            "markt_vol_20": bench["close"].pct_change().rolling(20).std(),
        })
        data = data.merge(market, on="date", how="left")

    # Querschnittsraenge: wie steht diese Aktie an diesem Tag im Vergleich zu
    # allen anderen da. Oft die staerksten Merkmale ueberhaupt.
    for column in ("ret_5", "ret_20", "ret_60", "vol_20", "vol_ratio", "rsi_14"):
        if column in data.columns:
            data[f"rang_{column}"] = data.groupby("date")[column].rank(pct=True)

    return data.sort_values(["date", "symbol"]).reset_index(drop=True)


def feature_columns(data: pd.DataFrame) -> list[str]:
    """Alle Merkmalsspalten -- alles ausser Kennung, Kurs und Ziel."""
    excluded = {"symbol", "date", "close", "ziel_rendite", "ziel_hoch"}
    return [c for c in data.columns if c not in excluded]


@dataclass
class WalkForwardResult:
    """Ergebnis eines vollstaendigen Walk-Forward-Laufs."""
    predictions: pd.DataFrame
    in_sample_accuracy: list[float] = field(default_factory=list)
    out_sample_accuracy: list[float] = field(default_factory=list)
    folds: list[dict] = field(default_factory=list)

    @property
    def mean_in_sample(self) -> float:
        return float(np.mean(self.in_sample_accuracy)) if self.in_sample_accuracy else np.nan

    @property
    def mean_out_sample(self) -> float:
        return float(np.mean(self.out_sample_accuracy)) if self.out_sample_accuracy else np.nan


def walk_forward(data: pd.DataFrame, model_factory, *,
                 train_years: int = 4, test_months: int = 6,
                 shuffle_target: bool = False, seed: int = 0,
                 verbose: bool = True) -> WalkForwardResult:
    """Rollierend trainieren und immer nur auf spaeteren Daten testen.

    Das Trainingsfenster waechst, das Testfenster wandert. Getestet wird
    ausschliesslich auf Zeitraeumen, die das Modell nie gesehen hat.

    ``shuffle_target`` wuerfelt die Zielwerte durch. Das ist die Kontrollprobe:
    Ein Modell, das dabei im Training weiterhin hohe Trefferquoten erreicht,
    lernt nichts -- es lernt die Daten auswendig.
    """
    features = feature_columns(data)
    frame = data.dropna(subset=features + ["ziel_hoch"]).copy()
    frame["date"] = pd.to_datetime(frame["date"])

    if shuffle_target:
        rng = np.random.default_rng(seed)
        shuffled = rng.permutation(frame["ziel_hoch"].to_numpy())
        frame["ziel_hoch"] = shuffled
        frame["ziel_rendite"] = rng.permutation(frame["ziel_rendite"].to_numpy())

    result = WalkForwardResult(predictions=pd.DataFrame())
    collected = []

    start = frame["date"].min()
    train_end = start + pd.DateOffset(years=train_years)
    last = frame["date"].max()

    while train_end < last:
        test_end = train_end + pd.DateOffset(months=test_months)
        train = frame[frame["date"] < train_end]
        test = frame[(frame["date"] >= train_end) & (frame["date"] < test_end)]
        if len(train) < 5_000 or len(test) < 200:
            train_end = test_end
            continue

        model = model_factory()
        model.fit(train[features], train["ziel_hoch"])

        in_acc = float((model.predict(train[features]) == train["ziel_hoch"]).mean())
        predicted = model.predict(test[features])
        out_acc = float((predicted == test["ziel_hoch"]).mean())

        probability = (model.predict_proba(test[features])[:, 1]
                       if hasattr(model, "predict_proba") else predicted.astype(float))

        collected.append(pd.DataFrame({
            "date": test["date"].to_numpy(),
            "symbol": test["symbol"].to_numpy(),
            "wahrsch_hoch": probability,
            "vorhersage": predicted,
            "tatsaechlich": test["ziel_hoch"].to_numpy(),
            "rendite": test["ziel_rendite"].to_numpy(),
        }))

        result.in_sample_accuracy.append(in_acc)
        result.out_sample_accuracy.append(out_acc)
        result.folds.append({
            "trainiert_bis": train_end.date(),
            "getestet_bis": test_end.date(),
            "n_train": len(train), "n_test": len(test),
            "im_training_%": in_acc * 100, "ausserhalb_%": out_acc * 100,
        })
        if verbose:
            print(f"  bis {train_end.date()}: Training {in_acc*100:5.2f} %  "
                  f"| ungesehen {out_acc*100:5.2f} %  (n={len(test):,})")

        train_end = test_end

    if collected:
        result.predictions = pd.concat(collected, ignore_index=True)
    return result


def trade_top_decile(predictions: pd.DataFrame, *, quantile: float = 0.9,
                     cost_bp: float = 10.0) -> dict:
    """Handelt taeglich die zuversichtlichsten Vorhersagen und misst das Ergebnis."""
    if predictions.empty:
        return {}
    frame = predictions.copy()
    frame["schwelle"] = frame.groupby("date")["wahrsch_hoch"].transform(
        lambda s: s.quantile(quantile))
    picked = frame[frame["wahrsch_hoch"] >= frame["schwelle"]]
    if picked.empty:
        return {}

    net = picked["rendite"] - cost_bp / 10_000.0
    daily = net.groupby(picked["date"]).mean()
    return {
        "n_trades": len(picked),
        "trefferquote_%": float((picked["rendite"] > 0).mean() * 100),
        "mittel_bp": float(net.mean() * 10_000),
        "tage": int(daily.size),
        "kapital_faktor": float((1 + daily).prod()),
        "sharpe": float(daily.mean() / daily.std(ddof=1) * np.sqrt(252))
        if daily.std(ddof=1) > 0 else np.nan,
    }
