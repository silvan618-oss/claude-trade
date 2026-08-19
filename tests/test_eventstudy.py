"""Tests fuer die Ereignis-Studie.

Schwerpunkt liegt auf den Fehlern, die eine Studie still ruinieren:
Zukunftswissen, unbereinigte Splits und falsch simulierte Knock-outs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.events import EventConfig, detect, prepare, random_control
from research.eventstudy import measure, summarise
from research.knockout import CostModel, simulate


def make_frame(closes, *, highs=None, lows=None, opens=None, volumes=None,
               adj_factor=1.0):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    opens = np.asarray(opens if opens is not None else closes, dtype=float)
    highs = np.asarray(highs if highs is not None else np.maximum(opens, closes), dtype=float)
    lows = np.asarray(lows if lows is not None else np.minimum(opens, closes), dtype=float)
    volumes = np.asarray(volumes if volumes is not None else np.full(n, 1_000_000), dtype=float)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-01", periods=n),
            "open": opens, "high": highs, "low": lows, "close": closes,
            "volume": volumes, "adjclose": closes * adj_factor,
        }
    )


class TestPrepare:
    def test_split_does_not_create_fake_gap(self):
        """Ein 4:1-Split darf nicht als Kurssturz von 75 Prozent erscheinen."""
        # Rohkurse: 400 -> 100 am Splittag. adjclose ist durchgaengig bereinigt.
        raw_close = [400.0, 400.0, 100.0, 100.0]
        frame = make_frame(raw_close, opens=[400.0, 400.0, 100.0, 100.0])
        frame["adjclose"] = [100.0, 100.0, 100.0, 100.0]

        prepared = prepare(frame)
        gaps = prepared["gap"].dropna().abs()
        assert gaps.max() < 1e-9, "Split wurde nicht herausgerechnet"

    def test_ohlc_scaled_consistently(self):
        frame = make_frame([100.0, 110.0], highs=[105.0, 115.0], lows=[95.0, 105.0])
        frame["adjclose"] = [50.0, 55.0]
        prepared = prepare(frame)
        # Alle vier Kurse muessen mit demselben Faktor 0.5 skaliert sein.
        assert prepared.at[0, "high"] == pytest.approx(52.5)
        assert prepared.at[0, "low"] == pytest.approx(47.5)
        assert prepared.at[0, "close"] == pytest.approx(50.0)

    def test_volume_ratio_uses_only_past(self):
        """Das Normalvolumen darf den aktuellen Tag nicht enthalten."""
        volumes = np.full(80, 1_000.0)
        volumes[79] = 500_000.0  # riesiger Ausreisser am letzten Tag
        prepared = prepare(make_frame(np.full(80, 100.0), volumes=volumes))
        # Waere der eigene Tag im Median, laege das Verhaeltnis nahe 1.
        assert prepared.at[79, "volume_ratio"] == pytest.approx(500.0, rel=0.01)

    def test_prepare_is_idempotent(self):
        frame = make_frame(np.linspace(100, 120, 90))
        once = prepare(frame)
        twice = prepare(once)
        pd.testing.assert_frame_equal(once, twice)


class TestDetect:
    def test_requires_both_gap_and_volume(self):
        closes = np.full(80, 100.0)
        opens = closes.copy()
        opens[70] = 110.0  # 10 Prozent Gap, aber normales Volumen
        frame = make_frame(closes, opens=opens)

        quiet = detect(frame, "TEST", EventConfig(min_gap=0.04, min_volume_ratio=2.0))
        assert quiet.empty, "Gap ohne Volumenanstieg darf kein Ereignis sein"

        volumes = np.full(80, 1_000.0)
        volumes[70] = 5_000.0
        loud = detect(make_frame(closes, opens=opens, volumes=volumes), "TEST",
                      EventConfig(min_gap=0.04, min_volume_ratio=2.0))
        assert len(loud) == 1
        assert loud.iloc[0]["side"] == 1

    def test_direction_filter(self):
        closes = np.full(80, 100.0)
        opens = closes.copy()
        opens[70] = 90.0
        volumes = np.full(80, 1_000.0)
        volumes[70] = 5_000.0
        frame = make_frame(closes, opens=opens, volumes=volumes)

        assert detect(frame, "T", EventConfig(direction="up")).empty
        assert len(detect(frame, "T", EventConfig(direction="down"))) == 1

    def test_penny_stocks_excluded(self):
        closes = np.full(80, 2.0)
        opens = closes.copy()
        opens[70] = 2.4
        volumes = np.full(80, 1_000.0)
        volumes[70] = 5_000.0
        frame = make_frame(closes, opens=opens, volumes=volumes)
        assert detect(frame, "T", EventConfig(min_price=5.0)).empty


class TestMeasure:
    def test_forward_return_is_strictly_future(self):
        """fwd_h muss close[row+h] gegen close[row] messen -- nicht davor."""
        closes = np.array([100.0] * 50 + [110.0] + [121.0] * 50)
        frame = prepare(make_frame(closes))
        events = pd.DataFrame(
            [{"symbol": "T", "date": frame.at[50, "date"], "row": 50, "gap": 0.1,
              "intraday": 0.0, "volume_ratio": 3.0, "vol_20d": 0.01, "side": 1}]
        )
        flat_benchmark = prepare(make_frame(np.full(101, 100.0)))

        measured = measure(events, {"T": frame}, flat_benchmark, horizons=(1,))
        # close[50] = 110, close[51] = 121  ->  +10 Prozent
        assert measured.at[0, "fwd_1"] == pytest.approx(0.10)

    def test_market_adjustment_removes_common_move(self):
        """Steigt alles gleich stark, muss die bereinigte Rendite null sein."""
        stock = prepare(make_frame(np.array([100.0, 105.0, 110.0])))
        bench = prepare(make_frame(np.array([200.0, 210.0, 220.0])))
        events = pd.DataFrame(
            [{"symbol": "T", "date": stock.at[0, "date"], "row": 0, "gap": 0.0,
              "intraday": 0.0, "volume_ratio": 1.0, "vol_20d": 0.01, "side": 1}]
        )
        measured = measure(events, {"T": stock}, bench, horizons=(1,))
        assert measured.at[0, "abn_1"] == pytest.approx(0.0, abs=1e-12)

    def test_signed_return_flips_for_short_side(self):
        stock = prepare(make_frame(np.array([100.0, 90.0])))
        bench = prepare(make_frame(np.array([100.0, 100.0])))
        events = pd.DataFrame(
            [{"symbol": "T", "date": stock.at[0, "date"], "row": 0, "gap": -0.1,
              "intraday": 0.0, "volume_ratio": 3.0, "vol_20d": 0.01, "side": -1}]
        )
        measured = measure(events, {"T": stock}, bench, horizons=(1,))
        # Kurs faellt 10 %, Position ist short -> signiert positiv.
        assert measured.at[0, "sig_1"] == pytest.approx(0.10)


class TestKnockout:
    def _event(self, frame, side=1, row=0):
        return pd.DataFrame(
            [{"symbol": "T", "date": frame.at[row, "date"], "row": row, "gap": 0.05,
              "intraday": 0.0, "volume_ratio": 3.0, "vol_20d": 0.01, "side": side}]
        )

    def test_barrier_touched_by_intraday_low(self):
        """Der Knock-out muss ausloesen, auch wenn der Schluss wieder erholt ist."""
        # Schluss steigt durchgehend, aber Tag 1 faellt zwischendurch auf 97.
        # Bei Hebel 50 liegt die Schwelle bei 98 -- das Tief reisst sie.
        frame = prepare(make_frame(
            closes=[100.0, 101.0, 105.0],
            highs=[100.0, 101.0, 105.0],
            lows=[100.0, 97.0, 105.0],
        ))
        trades = simulate(self._event(frame), {"T": frame}, leverage=50, horizon=2,
                          costs=CostModel(financing_rate=0.0, spread=0.0))
        assert bool(trades.at[0, "knocked_out"]) is True
        assert trades.at[0, "ergebnis_%"] == pytest.approx(-100.0)
        # Richtung stimmte (105 > 100) -- trotzdem Totalverlust.
        assert bool(trades.at[0, "richtung_stimmte"]) is True

    def test_survives_when_barrier_not_reached(self):
        frame = prepare(make_frame(
            closes=[100.0, 101.0, 104.0],
            highs=[100.0, 101.5, 104.0],
            lows=[100.0, 99.0, 101.0],
        ))
        trades = simulate(self._event(frame), {"T": frame}, leverage=10, horizon=2,
                          costs=CostModel(financing_rate=0.0, spread=0.0))
        assert bool(trades.at[0, "knocked_out"]) is False
        # 4 Prozent Kursgewinn mal Hebel 10.
        assert trades.at[0, "ergebnis_%"] == pytest.approx(40.0)

    def test_short_knocks_out_on_rising_high(self):
        frame = prepare(make_frame(
            closes=[100.0, 99.0, 95.0],
            highs=[100.0, 106.0, 95.0],
            lows=[100.0, 99.0, 95.0],
        ))
        trades = simulate(self._event(frame, side=-1), {"T": frame}, leverage=20,
                          horizon=2, costs=CostModel(financing_rate=0.0, spread=0.0))
        assert bool(trades.at[0, "knocked_out"]) is True

    def test_entry_day_move_cannot_knock_out(self):
        """Einstieg ist der Schlusskurs -- das Tief DESSELBEN Tages zaehlt nicht."""
        frame = prepare(make_frame(
            closes=[100.0, 100.0],
            highs=[120.0, 100.0],
            lows=[50.0, 100.0],   # extremes Tief am Einstiegstag
        ))
        trades = simulate(self._event(frame), {"T": frame}, leverage=50, horizon=1,
                          costs=CostModel(financing_rate=0.0, spread=0.0))
        assert bool(trades.at[0, "knocked_out"]) is False

    def test_loss_capped_at_total_stake(self):
        frame = prepare(make_frame(closes=[100.0, 100.0, 60.0],
                                   lows=[100.0, 100.0, 60.0],
                                   highs=[100.0, 100.0, 100.0]))
        trades = simulate(self._event(frame), {"T": frame}, leverage=2, horizon=2,
                          costs=CostModel(financing_rate=0.0, spread=0.0))
        assert trades.at[0, "ergebnis_%"] >= -100.0

    def test_financing_scales_with_leverage_and_time(self):
        flat = prepare(make_frame(closes=[100.0] * 6, lows=[100.0] * 6, highs=[100.0] * 6))
        costs = CostModel(financing_rate=0.04, spread=0.0, trading_days=252)
        trades = simulate(self._event(flat), {"T": flat}, leverage=50, horizon=5, costs=costs)
        # 50 * 4 % / 252 * 5 Tage = rund 3,97 Prozent Kosten bei unveraendertem Kurs.
        assert trades.at[0, "ergebnis_%"] == pytest.approx(-3.968, abs=0.01)


class TestControlGroup:
    def test_sides_are_balanced(self):
        frames = {f"S{i}": make_frame(np.linspace(100, 130, 200)) for i in range(5)}
        control = random_control(frames, n=400, seed=1)
        share_long = (control["side"] == 1).mean()
        assert 0.40 < share_long < 0.60, "Kontrollgruppe hat eine Richtungsschlagseite"

    def test_control_avoids_series_edges(self):
        frames = {"S": make_frame(np.linspace(100, 130, 200))}
        control = random_control(frames, n=200, seed=2, margin=25)
        assert control["row"].min() >= 25
        assert control["row"].max() <= 200 - 25


class TestSummarise:
    def test_clustered_tstat_below_naive_when_events_share_dates(self):
        """Ballen sich Ereignisse auf wenigen Tagen, muss der geclusterte t-Wert kleiner sein."""
        rng = np.random.default_rng(0)
        per_day, days = 50, 6
        # 300 Ereignisse, aber nur 6 Handelstage -- und pro Tag fast identische
        # Renditen, so wie an einem Crashtag, an dem alles gemeinsam faellt.
        day_effect = np.array([0.05, 0.045, 0.048, 0.052, 0.047, 0.049])
        dates = pd.to_datetime(
            [f"2020-03-{16 + d:02d}" for d in range(days) for _ in range(per_day)]
        )
        values = np.repeat(day_effect, per_day) + rng.normal(0, 0.0005, per_day * days)
        measured = pd.DataFrame({"date": dates, "sig_5": values})

        result = summarise(measured, horizons=(5,))
        assert abs(result.at[0, "t_geclustert"]) < abs(result.at[0, "t_naiv"])


class TestTimeframes:
    """Der teuerste Fehler beim Multi-Timeframe ist Zukunftswissen."""

    def _hourly(self, n=200, start="2024-01-02 14:30"):
        idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
        return pd.DataFrame({
            "date": idx,
            "open": np.linspace(100, 120, n), "high": np.linspace(101, 121, n),
            "low": np.linspace(99, 119, n), "close": np.linspace(100, 120, n),
            "volume": np.full(n, 1000.0), "adjclose": np.linspace(100, 120, n),
        })

    def _daily(self, n=140, start="2023-10-01"):
        idx = pd.date_range(start, periods=n, freq="1D", tz="UTC")
        return pd.DataFrame({
            "date": idx,
            "open": np.linspace(100, 160, n), "high": np.linspace(101, 161, n),
            "low": np.linspace(99, 159, n), "close": np.linspace(100, 160, n),
            "volume": np.full(n, 1000.0), "adjclose": np.linspace(100, 160, n),
        })

    def test_daily_bar_not_visible_before_it_closes(self):
        """Eine Tageskerze darf erst nach Handelsschluss sichtbar sein."""
        from research.timeframes import BAR_DURATION, add_trend
        daily = add_trend(self._daily(), "1d")
        first = daily.iloc[0]
        # Zeitstempel 00:00 UTC, verfuegbar erst 21 Stunden spaeter.
        assert first["available_at"] - first["date"] == BAR_DURATION["1d"]
        assert first["available_at"].hour == 21

    def test_alignment_uses_only_closed_higher_bars(self):
        from research.timeframes import align
        aligned = align(self._hourly(), "1h", {"1d": self._daily()})
        merged = aligned.dropna(subset=["state_1d"])
        assert not merged.empty

        from research.timeframes import add_trend
        daily = add_trend(self._daily(), "1d").dropna(subset=["state"])

        for row in merged.head(50).itertuples(index=False):
            # Der angebundene Tagesbalken muss vor dem Basisbalken fertig gewesen sein.
            usable = daily[daily["available_at"] <= row.available_at]
            assert not usable.empty
            assert usable.iloc[-1]["state"] == row.state_1d

    def test_no_future_daily_state_leaks_in(self):
        """Kernprobe: ein spaeterer Tagesbalken darf das Ergebnis nicht aendern."""
        from research.timeframes import align
        daily = self._daily()
        full = align(self._hourly(), "1h", {"1d": daily})

        # Alles ab der Haelfte aus den Tagesdaten entfernen ...
        cutoff = full["available_at"].iloc[len(full) // 2]
        truncated_daily = daily[daily["date"] + pd.Timedelta(hours=21) <= cutoff]
        partial = align(self._hourly(), "1h", {"1d": truncated_daily})

        # ... darf die frueheren Basisbalken nicht veraendert haben.
        early = full["available_at"] <= cutoff
        pd.testing.assert_series_equal(
            full.loc[early, "state_1d"].reset_index(drop=True),
            partial.loc[early, "state_1d"].reset_index(drop=True),
        )

    def test_confluence_counts_agreement(self):
        from research.timeframes import confluence
        frame = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=4, tz="UTC"),
            "close": [100.0, 101, 102, 103],
            "state_1h": [1.0, 1, -1, 1],
            "state_1d": [1.0, -1, -1, np.nan],
        })
        out = confluence(frame, ("1h", "1d"))
        assert list(out["score"][:3]) == [2.0, 0.0, -2.0]
        assert list(out["einig"][:3]) == [True, False, True]
        assert bool(out["einig"].iloc[3]) is False  # fehlende Ebene zaehlt nicht als einig

    def test_disagreement_excluded_from_results(self):
        from research.timeframes import by_confluence
        frame = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=6, freq="1h", tz="UTC"),
            "score": [0.0, 0, 2, 2, 2, 2],
            "richtung": [0.0, 0, 1, 1, 1, 1],
            "sig_1": [0.0, 0.0, 0.01, 0.02, -0.01, 0.03],
        })
        result = by_confluence(frame, 1)
        # Die beiden richtungslosen Balken duerfen nicht als Treffer zaehlen.
        assert 0 not in result["einigkeit"].tolist()
        assert result.loc[result["einigkeit"] == 2, "n"].iloc[0] == 4


class TestMachineLearning:
    """Die Merkmale duerfen ausschliesslich Vergangenheit enthalten."""

    def _series(self, n=400, seed=5):
        rng = np.random.default_rng(seed)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
        return pd.DataFrame({
            "date": pd.bdate_range("2020-01-01", periods=n),
            "open": close * (1 + rng.normal(0, 0.002, n)),
            "high": close * (1 + abs(rng.normal(0, 0.008, n))),
            "low": close * (1 - abs(rng.normal(0, 0.008, n))),
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
            "adjclose": close,
        })

    def test_no_feature_sees_the_future(self):
        """Kernprobe: Daten nach Tag t loeschen darf die Merkmale bei t nicht aendern."""
        from research.events import prepare
        from research.ml import build_features, feature_columns

        full = prepare(self._series())
        cut = 300
        truncated = prepare(self._series().iloc[: cut + 1].copy())

        a = build_features(full, "T").iloc[:cut]
        b = build_features(truncated, "T").iloc[:cut]

        for column in feature_columns(a):
            if column not in b.columns:
                continue
            left, right = a[column], b[column]
            both = left.notna() & right.notna()
            assert np.allclose(left[both], right[both], equal_nan=True), \
                f"Merkmal {column!r} aendert sich, wenn spaetere Daten fehlen -> Zukunftswissen"

    def test_target_is_next_day_return(self):
        from research.events import prepare
        from research.ml import build_features

        frame = prepare(self._series(n=50))
        features = build_features(frame, "T")
        expected = frame.at[11, "close"] / frame.at[10, "close"] - 1.0
        assert features.at[10, "ziel_rendite"] == pytest.approx(expected)
        assert features.at[10, "ziel_hoch"] == int(expected > 0)

    def test_last_row_target_is_undefined(self):
        """Fuer den letzten Tag gibt es kein Morgen -- das Ziel muss leer sein."""
        from research.events import prepare
        from research.ml import build_features
        features = build_features(prepare(self._series(n=50)), "T")
        assert pd.isna(features["ziel_rendite"].iloc[-1])

    def test_cross_sectional_rank_uses_same_day_only(self):
        from research.ml import build_dataset
        from research.events import prepare
        prepared = {f"S{i}": prepare(self._series(seed=i)) for i in range(4)}
        data = build_dataset(prepared)
        day = data[data["date"] == data["date"].iloc[-40]].dropna(subset=["rang_ret_20"])
        if len(day) > 1:
            # Raenge innerhalb eines Tages muessen zwischen 0 und 1 liegen und verschieden sein.
            assert day["rang_ret_20"].between(0, 1).all()
            assert day["rang_ret_20"].nunique() == len(day)

    def test_walk_forward_never_tests_on_training_dates(self):
        from research.ml import build_dataset, walk_forward
        from research.events import prepare
        from sklearn.dummy import DummyClassifier

        prepared = {f"S{i}": prepare(self._series(n=2000, seed=i)) for i in range(6)}
        data = build_dataset(prepared)
        result = walk_forward(data, lambda: DummyClassifier(strategy="most_frequent"),
                              train_years=2, test_months=12, verbose=False)
        assert result.folds, "kein einziger Durchlauf zustande gekommen"
        for fold in result.folds:
            # Getestet wird immer NACH dem Ende des Trainings.
            assert fold["getestet_bis"] > fold["trainiert_bis"]


class TestIntradayKnockout:
    """Kurze Haltedauern: Pfadpruefung und Tagesgrenze."""

    def _bars(self, closes, highs=None, lows=None, day="2024-01-02", start_hour=14):
        n = len(closes)
        closes = np.asarray(closes, dtype=float)
        return pd.DataFrame({
            "date": pd.date_range(f"{day} {start_hour}:30", periods=n, freq="15min", tz="UTC"),
            "open": closes,
            "high": np.asarray(highs if highs is not None else closes, dtype=float),
            "low": np.asarray(lows if lows is not None else closes, dtype=float),
            "close": closes,
            "volume": np.full(n, 1000.0), "adjclose": closes,
        })

    def test_barrier_touched_within_holding_window(self):
        from research.intraday_ko import IntradayCosts, simulate_holds
        # Hebel 30 -> Schwelle 3,33 % -> bei Einstieg 100 liegt sie bei 96,67.
        bars = self._bars([100, 100, 100, 100],
                          highs=[100, 100, 100, 100],
                          lows=[100, 96.0, 100, 100])
        trades = simulate_holds(bars, leverage=30, hold_bars=2,
                                costs=IntradayCosts(spread=0.0))
        assert bool(trades.at[0, "ausgeknockt"]) is True
        assert trades.at[0, "ergebnis_%"] == pytest.approx(-100.0)

    def test_no_knockout_when_barrier_held(self):
        from research.intraday_ko import IntradayCosts, simulate_holds
        bars = self._bars([100, 99, 101], highs=[100, 99.5, 101], lows=[100, 98.0, 100])
        trades = simulate_holds(bars, leverage=30, hold_bars=2,
                                costs=IntradayCosts(spread=0.0))
        assert bool(trades.at[0, "ausgeknockt"]) is False
        assert trades.at[0, "ergebnis_%"] == pytest.approx(30.0)  # +1 % mal Hebel 30

    def test_trades_never_span_two_sessions(self):
        """Ein Intraday-Trade darf nicht ueber Nacht laufen -- sonst faellt Finanzierung an."""
        from research.intraday_ko import simulate_holds
        day1 = self._bars([100] * 4, day="2024-01-02")
        day2 = self._bars([100] * 4, day="2024-01-03")
        bars = pd.concat([day1, day2], ignore_index=True)
        trades = simulate_holds(bars, leverage=30, hold_bars=3)
        tage = pd.to_datetime(trades["einstieg"]).dt.date.nunique()
        # Nur Einstiege, bei denen der Ausstieg am selben Tag liegt.
        assert len(trades) == 2, "Trades ueber die Tagesgrenze wurden nicht ausgefiltert"
        assert tage == 2

    def test_spread_is_the_only_intraday_cost(self):
        from research.intraday_ko import IntradayCosts, simulate_holds
        flat = self._bars([100] * 4)
        trades = simulate_holds(flat, leverage=30, hold_bars=2,
                                costs=IntradayCosts(spread=0.01))
        # Kurs unveraendert -> genau der Spread bleibt als Verlust, keine Finanzierung.
        assert trades["ergebnis_%"].iloc[0] == pytest.approx(-1.0)

    def test_short_side_uses_highs(self):
        from research.intraday_ko import IntradayCosts, simulate_holds
        bars = self._bars([100, 100, 100], highs=[100, 104.0, 100], lows=[100, 100, 100])
        trades = simulate_holds(bars, leverage=30, hold_bars=2, side=-1,
                                costs=IntradayCosts(spread=0.0))
        assert bool(trades.at[0, "ausgeknockt"]) is True


class TestPatterns:
    """Muster muessen genau das erkennen, was ihr Name sagt."""

    def _candles(self, rows):
        """rows: Liste von (open, high, low, close)."""
        n = len(rows)
        arr = np.array(rows, dtype=float)
        return pd.DataFrame({
            "date": pd.bdate_range("2020-01-01", periods=n),
            "open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3],
            "volume": np.full(n, 1000.0), "adjclose": arr[:, 3],
        })

    def test_bullish_engulfing_needs_full_body_cover(self):
        from research.patterns import detect_patterns
        # Tag 1 rot (102 -> 100), Tag 2 gruen und umschliesst den Koerper (99 -> 103).
        frame = self._candles([(102, 102, 100, 100), (99, 103.5, 98.5, 103)])
        assert bool(detect_patterns(frame)["bullish_engulfing"].iloc[1]) is True

        # Gruener Koerper zu klein -> kein Engulfing.
        frame = self._candles([(102, 102, 100, 100), (100.5, 102, 100, 101.5)])
        assert bool(detect_patterns(frame)["bullish_engulfing"].iloc[1]) is False

    def test_doji_requires_tiny_body(self):
        from research.patterns import detect_patterns
        frame = self._candles([(100, 103, 97, 100.1)])   # Koerper 0,1 von 6 Spanne
        assert bool(detect_patterns(frame)["doji"].iloc[0]) is True
        frame = self._candles([(100, 103, 97, 102.5)])
        assert bool(detect_patterns(frame)["doji"].iloc[0]) is False

    def test_inside_and_outside_bar_are_opposites(self):
        from research.patterns import detect_patterns
        inside = self._candles([(100, 105, 95, 100), (100, 103, 97, 101)])
        found = detect_patterns(inside)
        assert bool(found["inside_bar"].iloc[1]) is True
        assert bool(found["outside_bar"].iloc[1]) is False

        outside = self._candles([(100, 103, 97, 100), (100, 106, 94, 101)])
        found = detect_patterns(outside)
        assert bool(found["outside_bar"].iloc[1]) is True
        assert bool(found["inside_bar"].iloc[1]) is False

    def test_three_black_crows_needs_three_falling_reds(self):
        from research.patterns import detect_patterns
        rows = [(100, 100, 99, 99), (99, 99, 98, 98), (98, 98, 97, 97)]
        assert bool(detect_patterns(self._candles(rows))["three_black_crows"].iloc[2]) is True
        # Eine gruene Kerze dazwischen bricht das Muster.
        rows = [(100, 100, 99, 99), (98, 99.5, 98, 99.5), (99.5, 99.5, 97, 97)]
        assert bool(detect_patterns(self._candles(rows))["three_black_crows"].iloc[2]) is False

    def test_pattern_uses_no_future_candles(self):
        """Kernprobe: spaetere Kerzen loeschen darf frueher erkannte Muster nicht aendern."""
        from research.patterns import detect_patterns, PATTERN_NAMES
        rng = np.random.default_rng(3)
        n = 300
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
        openp = close * (1 + rng.normal(0, 0.004, n))
        high = np.maximum(openp, close) * (1 + abs(rng.normal(0, 0.006, n)))
        low = np.minimum(openp, close) * (1 - abs(rng.normal(0, 0.006, n)))
        full = self._candles(list(zip(openp, high, low, close)))

        cut = 200
        a = detect_patterns(full).iloc[:cut]
        b = detect_patterns(full.iloc[:cut].copy())
        for name in PATTERN_NAMES:
            assert a[name].equals(b[name]), f"Muster {name!r} nutzt spaetere Kerzen"

    def test_market_adjustment_changes_bearish_verdict(self):
        """Ohne Marktbereinigung messen Short-Muster den Aufwaertsdrift mit."""
        from research.patterns import build_pattern_dataset
        rng = np.random.default_rng(1)
        n = 400
        # Markt mit klarem Aufwaertsdrift, Aktie folgt ihm exakt.
        drift = np.cumsum(rng.normal(0.002, 0.01, n))
        close = 100 * np.exp(drift)
        frame = self._candles([(c, c * 1.01, c * 0.99, c) for c in close])
        prepared = {"S": frame}
        dataset = build_pattern_dataset(prepared, horizon=1, benchmark=frame)
        # Aktie == Benchmark -> marktbereinigte Rendite muss null sein.
        assert dataset["fwd_abn"].abs().max() < 1e-9
        assert dataset["fwd"].abs().max() > 0


class TestSelectivity:
    """Kalibrierung und Auswahl der besten Signale."""

    def _preds(self, n=1000, seed=0, informative=True):
        rng = np.random.default_rng(seed)
        prob = rng.uniform(0.2, 0.8, n)
        # Bei informative=True trifft die Wahrscheinlichkeit tatsaechlich zu.
        actual = (rng.random(n) < (prob if informative else 0.5)).astype(int)
        return pd.DataFrame({
            "date": np.repeat(pd.date_range("2024-01-01", periods=n // 10), 10),
            "symbol": [f"S{i%10}" for i in range(n)],
            "wahrsch_hoch": prob,
            "vorhersage": (prob > 0.5).astype(int),
            "tatsaechlich": actual,
            "rendite": np.where(actual == 1, 0.01, -0.01),
        })

    def test_calibration_detects_honest_probabilities(self):
        from research.ml import calibration
        table = calibration(self._preds(n=5000, informative=True))
        # Ein ehrliches Modell liegt in jedem Dezil nah an seiner Ansage.
        assert table["abweichung_pp"].abs().max() < 8

    def test_calibration_detects_overconfidence(self):
        from research.ml import calibration
        table = calibration(self._preds(n=5000, informative=False))
        # Sagt das Modell 80 % und liefert 50 %, muss die Abweichung stark negativ sein.
        assert table["abweichung_pp"].iloc[-1] < -15
        assert table["abweichung_pp"].iloc[0] > 10

    def test_selectivity_picks_top_n_per_day(self):
        from research.ml import selectivity_curve
        preds = self._preds(n=1000, informative=True)
        curve = selectivity_curve(preds, top_n=(10, 3, 1), cost_bp=0.0)
        days = preds["date"].nunique()
        assert curve.loc[curve["beste_pro_tag"] == 1, "n_trades"].iloc[0] == days
        assert curve.loc[curve["beste_pro_tag"] == 3, "n_trades"].iloc[0] == days * 3

    def test_selectivity_raises_hit_rate_when_model_is_real(self):
        """Kontrollprobe des Tests selbst: bei echtem Signal MUSS die Kurve steigen."""
        from research.ml import selectivity_curve
        curve = selectivity_curve(self._preds(n=20000, informative=True),
                                  top_n=(10, 1), cost_bp=0.0)
        breit = curve.loc[curve["beste_pro_tag"] == 10, "treffer_%"].iloc[0]
        eng = curve.loc[curve["beste_pro_tag"] == 1, "treffer_%"].iloc[0]
        assert eng > breit, "Bei echtem Signal muss Selektivitaet die Trefferquote heben"

    def test_selectivity_flat_when_model_is_noise(self):
        from research.ml import selectivity_curve
        curve = selectivity_curve(self._preds(n=20000, informative=False),
                                  top_n=(10, 1), cost_bp=0.0)
        spanne = curve["treffer_%"].max() - curve["treffer_%"].min()
        assert spanne < 8, "Bei reinem Rauschen darf Selektivitaet nichts bringen"
