"""Skew-Map — Lauf, Board und Snapshot-Historie.

    python -m bot.skew_map --demo                  # ohne Keys, sofort sichtbar
    python -m bot.skew_map --csv sheet.csv         # der Tabellen-Weg
    python -m bot.skew_map --alpaca                # Ketten mit IV und Greeks
    python -m bot.skew_map --template sheet.csv    # leeres Blatt anlegen

Jeder Lauf wird als datierter Snapshot nach skew_history/ geschrieben. Das ist
der Schritt, den alle ueberspringen, und der einzige, der das Ding am Ende
funktionieren laesst: erst mit Historie kann die Spalte "Delta vs. letzter
Lauf" gefuellt werden — und die Veraenderung ist das Signal, nicht das Level.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date, datetime, timezone

from bot.config import Config
from bot.skew import (
    CONTRARIAN_BID,
    SkewRow,
    SkewSettings,
    build_row,
    describe_row,
    finalize_rows,
    quadrant_card,
    sector_readings,
)
from bot.skew_data import (
    AlpacaChainProvider,
    CsvChainProvider,
    DEMO_UNIVERSE,
    DemoChainProvider,
    write_csv_template,
)

QUADRANT_ORDER = [CONTRARIAN_BID, "HEDGED RALLY", "CHASE", "FEAR"]


# ---------------------------------------------------------------------------
# Historie (Entscheidung #7)
# ---------------------------------------------------------------------------

def snapshot_path(settings: SkewSettings, day: date | None = None) -> str:
    day = day or date.today()
    return os.path.join(settings.history_dir, f"{day.isoformat()}.json")


def save_snapshot(rows: list[SkewRow], settings: SkewSettings,
                  day: date | None = None) -> str:
    os.makedirs(settings.history_dir, exist_ok=True)
    path = snapshot_path(settings, day)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": asdict(settings),
        "rows": [r.to_dict() for r in rows],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def previous_snapshot(settings: SkewSettings, before: date | None = None) -> dict | None:
    """Juengster Snapshot, der aelter ist als 'before' (default: heute)."""
    before = before or date.today()
    if not os.path.isdir(settings.history_dir):
        return None
    candidates = sorted(
        f for f in os.listdir(settings.history_dir) if f.endswith(".json")
    )
    for name in reversed(candidates):
        try:
            day = date.fromisoformat(name[:-5])
        except ValueError:
            continue
        if day < before:
            with open(os.path.join(settings.history_dir, name), encoding="utf-8") as f:
                return json.load(f)
    return None


def attach_changes(rows: list[SkewRow], previous: dict | None) -> list[SkewRow]:
    """Traegt Delta vs. letztem Snapshot ein — leer, solange keine Historie da ist."""
    if not previous:
        return rows
    last = {r["ticker"]: r["skew"] for r in previous.get("rows", [])}
    for row in rows:
        if row.ticker in last:
            row.delta_change = round(row.skew - last[row.ticker], 4)
    return rows


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def build_map(provider, settings: SkewSettings,
              tickers: list[str] | None = None) -> list[SkewRow]:
    settings.validate()
    readings = provider.fetch(tickers)
    rows = [build_row(r, settings) for r in readings]
    return finalize_rows(rows, settings)


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def render_board(rows: list[SkewRow], settings: SkewSettings) -> str:
    """Die Tabelle aus Teil 4 — sortiert nach Skew, mit sichtbaren Flags."""
    header = (f"{'Ticker':<7}{'Sektor':<16}{'Skew':>8}{'VolPkt':>8}{'1M %':>8}"
              f"{'vsSPY':>8}{'RVOL':>7}{'Rank':>7}{'Δ':>8}  Quadrant")
    lines = [header, "-" * len(header)]
    for row in sorted(rows, key=lambda r: r.skew, reverse=True):
        rank = f"{row.sector_rank:.0%}" if row.sector_rank is not None else "—"
        change = f"{row.delta_change:+.3f}" if row.delta_change is not None else "—"
        mark = "" if row.chain_ok else "  (!)"
        lines.append(
            f"{row.ticker:<7}{row.sector:<16}{row.skew:>8.3f}{row.vol_points:>8.2f}"
            f"{row.return_1m:>8.1f}{row.return_vs_spy:>8.1f}{row.rvol:>7.2f}"
            f"{rank:>7}{change:>8}  {row.quadrant}{mark}"
        )
    return "\n".join(lines)


def render_scatter(rows: list[SkewRow], settings: SkewSettings,
                   width: int = 64, height: int = 17) -> str:
    """ASCII-Streudiagramm: x = 1M-Rendite, y = Skew, Fadenkreuz = die vier Boxen."""
    plotted = [r for r in rows if r.chain_ok]
    if not plotted:
        return "(keine belastbaren Zeilen zum Plotten)"

    xs = [r.return_1m for r in plotted]
    ys = [r.skew for r in plotted]
    x_lo, x_hi = min(xs + [0.0]), max(xs + [0.0])
    y_lo, y_hi = min(ys + [0.0]), max(ys + [0.0])
    x_pad = (x_hi - x_lo) * 0.1 or 1.0
    y_pad = (y_hi - y_lo) * 0.1 or 0.05
    x_lo, x_hi = x_lo - x_pad, x_hi + x_pad
    y_lo, y_hi = y_lo - y_pad, y_hi + y_pad

    def col(x: float) -> int:
        return min(width - 1, max(0, round((x - x_lo) / (x_hi - x_lo) * (width - 1))))

    def line(y: float) -> int:
        return min(height - 1, max(0, round((y_hi - y) / (y_hi - y_lo) * (height - 1))))

    grid = [[" "] * width for _ in range(height)]
    zero_col, zero_line = col(0.0), line(0.0)
    for r in range(height):
        grid[r][zero_col] = "|"
    for c in range(width):
        grid[zero_line][c] = "-"
    grid[zero_line][zero_col] = "+"

    for row in plotted:
        c, r = col(row.return_1m), line(row.skew)
        label = row.ticker[:4]
        if c + len(label) < width and all(ch in " |-+" for ch in grid[r][c:c + len(label)]):
            grid[r][c:c + len(label)] = list(label)
        else:
            grid[r][c] = "o"

    out = [
        "  Skew (Puts teurer ^ / Calls teurer v)   x-Achse: 1M-Rendite %",
        "  oben links = FEAR        oben rechts = HEDGED RALLY",
        "  unten links = CONTRARIAN BID   unten rechts = CHASE",
        "",
    ]
    out += ["".join(r) for r in grid]
    out.append(f"  x: {x_lo:+.1f} % .. {x_hi:+.1f} %   y: {y_lo:+.2f} .. {y_hi:+.2f}")
    return "\n".join(out)


def render_report(rows: list[SkewRow], settings: SkewSettings) -> str:
    parts: list[str] = []

    parts.append(render_board(rows, settings))
    parts.append("")
    parts.append(render_scatter(rows, settings))
    parts.append("")

    parts.append("Sektoren (in Vol-Punkten, nicht normalisiert — Falle #2):")
    for reading in sector_readings(rows, settings):
        marker = "  " if reading.trustworthy else "! "
        parts.append(f"{marker}{reading.describe()}")
    parts.append("")

    for quadrant in QUADRANT_ORDER:
        bucket = [r for r in rows if r.quadrant == quadrant and r.chain_ok]
        if not bucket:
            continue
        parts.append(f"{quadrant} ({len(bucket)}):")
        for row in sorted(bucket, key=lambda r: abs(r.skew), reverse=True):
            parts.append("  " + describe_row(row, settings))
        parts.append("")

    rejected = [r for r in rows if not r.chain_ok]
    parts.append(f"Nicht belastbar ({len(rejected)}) — einzeln benannt statt still gedroppt:")
    for row in rejected:
        parts.append(f"  {row.ticker}: " + "; ".join(row.flags))
    if not rejected:
        parts.append("  (keine)")
    parts.append("")

    parts.append("Diese Ebene sagt, wo man hinschauen soll — nicht wann. Level, "
                 "Invalidierung und Einstieg kommen vom Chart.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _settings_from_env() -> SkewSettings:
    def num(name: str, default, cast):
        raw = os.getenv(name)
        return cast(raw) if raw else default

    base = SkewSettings()
    return SkewSettings(
        delta_target=num("SKEW_DELTA_TARGET", base.delta_target, float),
        target_dte=num("SKEW_TARGET_DTE", base.target_dte, int),
        min_dte=num("SKEW_MIN_DTE", base.min_dte, int),
        max_dte=num("SKEW_MAX_DTE", base.max_dte, int),
        min_open_interest=num("SKEW_MIN_OI", base.min_open_interest, int),
        sanity_ceiling=num("SKEW_SANITY_CEILING", base.sanity_ceiling, float),
        min_names_per_sector=num("SKEW_MIN_SECTOR_NAMES", base.min_names_per_sector, int),
        min_sector_agreement=num("SKEW_MIN_AGREEMENT", base.min_sector_agreement, float),
        history_dir=os.getenv("SKEW_HISTORY_DIR", base.history_dir),
        center_mode=os.getenv("SKEW_CENTER_MODE", base.center_mode),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Skew-Map: was Optionshaendler gerade bezahlen")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="synthetische Daten, keine Keys noetig")
    source.add_argument("--csv", metavar="PFAD", help="handgefuelltes Blatt einlesen")
    source.add_argument("--alpaca", action="store_true", help="Optionsketten via Alpaca")
    parser.add_argument("--template", metavar="PFAD", help="leeres CSV-Blatt anlegen und beenden")
    parser.add_argument("--tickers", help="Komma-Liste, sonst SYMBOLS aus der .env")
    parser.add_argument("--no-save", action="store_true", help="Snapshot nicht schreiben")
    parser.add_argument("--card", action="store_true", help="nur die Quadranten-Karte zeigen")
    args = parser.parse_args()

    if args.card:
        print(quadrant_card())
        return

    settings = _settings_from_env()
    config = Config()
    tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
               if args.tickers else None)

    if args.template:
        names = tickers or [t for t, _ in DEMO_UNIVERSE]
        write_csv_template(args.template, names, dict(DEMO_UNIVERSE))
        print(f"Leeres Blatt geschrieben: {args.template}")
        print("Pro Name aus der Broker-Kette abtippen: ATM-IV, Put-IV und Call-IV "
              f"beim {settings.delta_target:.2f}-Delta, gespiegelt, gleiche Expiry.")
        return

    if args.csv:
        provider = CsvChainProvider(args.csv)
    elif args.alpaca:
        if not config.has_alpaca:
            raise SystemExit("Keine Alpaca-Keys in der .env — --demo oder --csv nutzen.")
        provider = AlpacaChainProvider(
            config.alpaca_api_key, config.alpaca_secret_key, settings, dict(DEMO_UNIVERSE)
        )
        tickers = tickers or config.symbols
    else:
        provider = DemoChainProvider()

    rows = build_map(provider, settings, tickers)
    if not rows:
        raise SystemExit("Keine Zeilen erzeugt — Datenquelle pruefen.")

    rows = attach_changes(rows, previous_snapshot(settings))

    print(quadrant_card())
    print()
    print(render_report(rows, settings))

    if not args.no_save:
        path = save_snapshot(rows, settings)
        print(f"\nSnapshot: {path}")
        if all(r.delta_change is None for r in rows):
            print("Noch keine Historie — die Δ-Spalte fuellt sich ab dem zweiten Lauf. "
                  "Rund sechs Laeufe, bis sie etwas aussagt.")


if __name__ == "__main__":
    main()
