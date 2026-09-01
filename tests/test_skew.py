import pytest

from bot.skew import (
    CHASE,
    CONTRARIAN_BID,
    FEAR,
    HEDGED_RALLY,
    ChainReading,
    SkewSettings,
    build_row,
    classify_quadrant,
    compute_skew,
    describe_row,
    finalize_rows,
    sector_readings,
)


def reading(ticker="AAA", sector="Semiconductors", atm=0.40, put=0.46, call=0.36,
            ret=5.0, **kwargs) -> ChainReading:
    return ChainReading(ticker=ticker, sector=sector, atm_iv=atm, put_iv=put,
                        call_iv=call, return_1m=ret, **kwargs)


# --- Kernformel -------------------------------------------------------------

def test_put_skew_is_positive():
    skew, vol_points = compute_skew(atm_iv=0.40, put_iv=0.46, call_iv=0.36)
    assert skew == pytest.approx(0.25)
    assert vol_points == pytest.approx(10.0)


def test_call_skew_is_negative():
    skew, vol_points = compute_skew(atm_iv=0.40, put_iv=0.34, call_iv=0.44)
    assert skew < 0
    assert vol_points == pytest.approx(-10.0)


def test_normalization_makes_a_utility_comparable_to_a_semi():
    # Gleiche 4 Vol-Punkte, sehr unterschiedliche ATM-IV: normalisiert liegt
    # der Versorger weit vorn — genau der Effekt hinter Falle #2.
    utility, _ = compute_skew(atm_iv=0.15, put_iv=0.17, call_iv=0.13)
    semi, _ = compute_skew(atm_iv=0.60, put_iv=0.62, call_iv=0.58)
    assert utility > semi * 3


def test_rejects_nonsense_inputs():
    with pytest.raises(ValueError):
        compute_skew(atm_iv=0.0, put_iv=0.3, call_iv=0.3)
    with pytest.raises(ValueError):
        compute_skew(atm_iv=0.3, put_iv=-0.1, call_iv=0.3)


# --- Quadranten -------------------------------------------------------------

@pytest.mark.parametrize("skew,ret,expected", [
    (0.20, -6.0, FEAR),
    (0.20, 6.0, HEDGED_RALLY),
    (-0.20, -6.0, CONTRARIAN_BID),
    (-0.20, 6.0, CHASE),
])
def test_four_quadrants(skew, ret, expected):
    assert classify_quadrant(skew, ret) == expected


def test_median_crosshair_moves_the_boxes():
    # Alles positiv geskewt: bei Fadenkreuz 0 landet niemand unten,
    # beim Median teilt sich dieselbe Liste auf.
    settings = SkewSettings(center_mode="zero")
    readings = [reading(f"T{i}", put=0.42 + i * 0.02, ret=1.0 * i) for i in range(6)]
    rows = finalize_rows([build_row(r, settings) for r in readings], settings)
    assert all(r.quadrant in (FEAR, HEDGED_RALLY) for r in rows)

    settings = SkewSettings(center_mode="median")
    rows = finalize_rows([build_row(r, settings) for r in readings], settings)
    assert {r.quadrant for r in rows} & {CONTRARIAN_BID, CHASE}


# --- Falle #4: ein kaputter Mark --------------------------------------------

def test_sanity_ceiling_rejects_an_impossible_mark():
    # Der Duke-Fall aus dem Artikel: -1.43 auf einem Versorger.
    settings = SkewSettings(sanity_ceiling=0.75)
    row = build_row(reading("DUK", sector="Utilities", atm=0.18, put=0.06, call=0.32),
                    settings)
    assert not row.chain_ok
    assert any(f.startswith("sanity_ceiling") for f in row.flags)
    assert row.weight == settings.thin_chain_weight


def test_thin_chain_is_downweighted_not_dropped():
    settings = SkewSettings(min_open_interest=100)
    row = build_row(reading(open_interest=12), settings)
    assert not row.chain_ok
    assert any(f.startswith("thin_chain") for f in row.flags)


def test_bad_mark_does_not_drag_its_sector():
    settings = SkewSettings(min_names_per_sector=2)
    readings = [reading(f"U{i}", sector="Utilities", atm=0.18, put=0.20, call=0.17)
                for i in range(4)]
    readings.append(reading("BAD", sector="Utilities", atm=0.18, put=0.03, call=0.40))
    rows = finalize_rows([build_row(r, settings) for r in readings], settings)

    utilities = next(s for s in sector_readings(rows, settings) if s.sector == "Utilities")
    assert utilities.names == 4          # der kaputte Name ist raus
    assert utilities.avg_vol_points > 0  # und hat den Schnitt nicht gekippt


# --- Falle #5: datierter Katalysator ----------------------------------------

def test_earnings_inside_the_measured_expiry_is_flagged():
    settings = SkewSettings()
    row = build_row(reading(expiry="2099-10-16", earnings_date="2099-10-02"), settings)
    assert any(f.startswith("earnings_in_expiry") for f in row.flags)


def test_stale_earnings_date_is_not_event_premium():
    # Termin liegt vor der Expiry, aber auch schon in der Vergangenheit —
    # das ist ein liegengebliebenes Datum im Blatt, keine Event-Praemie.
    settings = SkewSettings()
    row = build_row(reading(expiry="2099-10-16", earnings_date="2001-01-05"), settings)
    assert not any(f.startswith("earnings_in_expiry") for f in row.flags)


def test_earnings_after_the_expiry_is_not_flagged():
    settings = SkewSettings()
    row = build_row(reading(expiry="2099-10-16", earnings_date="2099-11-04"), settings)
    assert not any(f.startswith("earnings_in_expiry") for f in row.flags)


# --- Falle #3: Agreement ----------------------------------------------------

def test_split_sector_is_marked_untrustworthy():
    settings = SkewSettings(min_names_per_sector=4, min_sector_agreement=0.7)
    readings = [reading("A", put=0.50, call=0.32), reading("B", put=0.50, call=0.32),
                reading("C", put=0.32, call=0.50), reading("D", put=0.32, call=0.50)]
    rows = finalize_rows([build_row(r, settings) for r in readings], settings)
    sector = sector_readings(rows, settings)[0]
    assert sector.agreement == 0.5
    assert not sector.trustworthy
    assert "Agreement" in sector.caveat


def test_too_few_names_is_not_a_sector_read():
    settings = SkewSettings(min_names_per_sector=5)
    rows = finalize_rows([build_row(reading("A"), settings)], settings)
    assert not sector_readings(rows, settings)[0].trustworthy


# --- Sektor-Rang und Satz ---------------------------------------------------

def test_sector_rank_is_relative_to_peers_only():
    settings = SkewSettings()
    readings = [reading("LOW", put=0.38), reading("MID", put=0.46), reading("HIGH", put=0.54)]
    rows = finalize_rows([build_row(r, settings) for r in readings], settings)
    ranks = {r.ticker: r.sector_rank for r in rows}
    assert ranks["LOW"] < ranks["MID"] < ranks["HIGH"]


def test_sentence_follows_the_fixed_template():
    settings = SkewSettings()
    rows = finalize_rows([build_row(reading("NVDA", ret=8.0, spy_return_1m=2.0,
                                            rvol=1.9), settings)], settings)
    sentence = describe_row(rows[0], settings)
    assert sentence.startswith("NVDA — Trader zahlen")
    assert "Puts" in sentence
    assert "vs. SPY" in sentence
    assert HEDGED_RALLY in sentence
    assert "Stops nachziehen" in sentence


def test_settings_validate_catches_a_drifting_expiry_rule():
    with pytest.raises(ValueError):
        SkewSettings(min_dte=30, target_dte=10, max_dte=60).validate()
    with pytest.raises(ValueError):
        SkewSettings(center_mode="whatever").validate()


def test_call_side_rank_is_mirrored_in_the_sentence():
    # Der staerkste Call-Bid im Sektor steht auf Perzentil 0 des Put-Skews —
    # im Satz muss daraus "mehr Aufwaerts-Exposure als bei ~100 %" werden.
    settings = SkewSettings()
    readings = [reading("BULL", put=0.30, call=0.52, ret=-4.0),
                reading("MID", put=0.44, call=0.38, ret=-4.0),
                reading("BEAR", put=0.52, call=0.30, ret=-4.0)]
    rows = finalize_rows([build_row(r, settings) for r in readings], settings)
    bull = next(r for r in rows if r.ticker == "BULL")
    assert bull.sector_rank < 0.2
    sentence = describe_row(bull, settings)
    assert "Aufwaerts-Exposure als bei 83%" in sentence
