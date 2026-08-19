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
