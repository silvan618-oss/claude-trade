import os
import tempfile
from datetime import date

import pytest

from bot.skew import SkewSettings, build_row, finalize_rows
from bot.skew_data import (
    CsvChainProvider,
    DemoChainProvider,
    _is_monthly,
    parse_occ_symbol,
    write_csv_template,
)
from bot.skew_map import attach_changes, build_map, previous_snapshot, save_snapshot


def test_parses_an_occ_symbol():
    assert parse_occ_symbol("AAPL251017C00230000") == (date(2025, 10, 17), "C", 230.0)
    # Variabel langer Root und Sub-Dollar-Strike
    assert parse_occ_symbol("BRKB260116P00012500") == (date(2026, 1, 16), "P", 12.5)


@pytest.mark.parametrize("symbol", ["AAPL", "AAPL251017X00230000", "AAPL2510C7C0023000A"])
def test_rejects_garbage_symbols(symbol):
    assert parse_occ_symbol(symbol) is None


def test_third_friday_is_the_monthly():
    assert _is_monthly(date(2026, 1, 16))       # dritter Freitag
    assert not _is_monthly(date(2026, 1, 9))    # zweiter Freitag
    assert not _is_monthly(date(2026, 1, 21))   # Mittwoch


def test_csv_accepts_percent_and_decimal_iv():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sheet.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("ticker,sector,atm_iv,put_iv,call_iv,return_1m\n")
            f.write("AAA,Software,0.40,0.46,0.36,5.0\n")
            f.write("BBB,Software,40,46,36,5.0\n")
        readings = CsvChainProvider(path).fetch()
    assert readings[0].atm_iv == pytest.approx(readings[1].atm_iv)


def test_csv_error_names_the_line():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sheet.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write("ticker,sector,atm_iv,put_iv,call_iv,return_1m\n")
            f.write("AAA,Software,0.40,nonsense,0.36,5.0\n")
        with pytest.raises(ValueError, match="sheet.csv:2"):
            CsvChainProvider(path).fetch()


def test_template_round_trips_through_the_provider():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "template.csv")
        write_csv_template(path, ["NVDA", "MSFT"], {"NVDA": "Semiconductors"})
        assert CsvChainProvider(path).fetch() == []  # leere Zeilen liefern nichts


def test_demo_run_is_deterministic_and_flags_the_broken_mark():
    settings = SkewSettings()
    rows_a = build_map(DemoChainProvider(), settings)
    rows_b = build_map(DemoChainProvider(), settings)
    assert [r.skew for r in rows_a] == [r.skew for r in rows_b]

    duke = next(r for r in rows_a if r.ticker == "DUK")
    assert not duke.chain_ok


def test_snapshot_history_fills_the_change_column():
    settings = SkewSettings(history_dir=tempfile.mkdtemp())
    yesterday_rows = finalize_rows(
        [build_row(r, settings) for r in DemoChainProvider(seed=1).fetch()], settings
    )
    save_snapshot(yesterday_rows, settings, day=date(2026, 8, 17))

    today_rows = finalize_rows(
        [build_row(r, settings) for r in DemoChainProvider(seed=2).fetch()], settings
    )
    assert all(r.delta_change is None for r in today_rows)

    attach_changes(today_rows, previous_snapshot(settings, before=date(2026, 8, 18)))
    assert all(r.delta_change is not None for r in today_rows)


def test_no_history_means_no_invented_change():
    settings = SkewSettings(history_dir=tempfile.mkdtemp())
    rows = build_map(DemoChainProvider(), settings)
    attach_changes(rows, previous_snapshot(settings))
    assert all(r.delta_change is None for r in rows)
