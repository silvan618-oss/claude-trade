"""Fuehrt die komplette Ereignis-Studie aus und druckt den Bericht.

    python -m research.cli
    python -m research.cli --gap 0.06 --horizon 10 --start 2010-01-01
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

from research import data, eventstudy, knockout
from research.events import EventConfig, detect_universe, prepare_all, random_control


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _table(frame: pd.DataFrame) -> str:
    return frame.to_string(index=False, float_format=lambda v: f"{v:8.2f}")


def run(args: argparse.Namespace) -> int:
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    symbols = data.UNIVERSE[: args.limit] if args.limit else data.UNIVERSE

    print(f"Lade {len(symbols)} Aktien + Benchmark {data.BENCHMARK} "
          f"({start} bis {end}) ...")
    frames = data.load_universe(symbols + [data.BENCHMARK], start, end,
                                refresh=args.refresh)
    benchmark = frames.pop(data.BENCHMARK, None)
    if benchmark is None:
        raise SystemExit(f"Benchmark {data.BENCHMARK} konnte nicht geladen werden.")

    prepared = prepare_all(frames)
    prepared_benchmark = prepare_all({data.BENCHMARK: benchmark})[data.BENCHMARK]
    lookup = dict(prepared)
    print(f"  {len(prepared)} Aktien mit ausreichender Historie.")

    config = EventConfig(min_gap=args.gap, min_volume_ratio=args.volume)
    events = detect_universe(prepared, config)
    if events.empty:
        raise SystemExit("Keine Ereignisse gefunden -- Schwellen zu streng?")

    measured = eventstudy.measure(events, lookup, prepared_benchmark)
    controls = random_control(prepared, n=max(len(events) * 3, 500), seed=args.seed)
    measured_control = eventstudy.measure(controls, lookup, prepared_benchmark)

    print(f"\nEreignisse: {len(measured)}  "
          f"(Gap >= {args.gap:.0%}, Volumen >= {args.volume:.1f}x Normalniveau)")
    print(f"davon aufwaerts: {(measured['side'] == 1).sum()}  "
          f"abwaerts: {(measured['side'] == -1).sum()}")
    print(f"verteilt auf {measured['date'].nunique()} verschiedene Handelstage "
          f"und {measured['symbol'].nunique()} Aktien")

    _rule("1. Wo steckt die Bewegung? (Mittelwert in Ereignisrichtung)")
    print(_table(eventstudy.decompose(measured)))

    _rule("2. Ereignisse gegen Zufallstage (marktbereinigt, in Ereignisrichtung)")
    summary = eventstudy.summarise(measured)
    control_summary = eventstudy.summarise(measured_control)
    print(_table(eventstudy.compare(summary, control_summary)))
    print("\n  t_geclustert ist der ehrliche Wert: Ereignisse ballen sich an")
    print("  denselben Tagen. Als Faustregel gilt |t| > 3 als belastbar.")

    _rule(f"3. Mit Hebel gehandelt ({args.horizon} Handelstage halten)")
    swept = knockout.sweep(measured, lookup, horizon=args.horizon)
    print(_table(swept))
    print("\n  richtig_und_raus_% = Richtung stimmte am Ende, trotzdem vorher ausgeknockt.")

    _rule("4. Fazit")
    best = summary.loc[summary["t_geclustert"].abs().idxmax()] if not summary.empty else None
    if best is not None:
        print(f"  Staerkster Effekt: {best['horizont_tage']:.0f} Tage, "
              f"{best['mittel_%']:+.2f} % im Mittel, t = {best['t_geclustert']:.2f}")
        verdict = ("belastbar" if abs(best["t_geclustert"]) > 3
                   else "nicht von Rauschen zu unterscheiden")
        print(f"  Bewertung: {verdict}")
    if not swept.empty:
        row50 = swept[swept["hebel"] == 50]
        if not row50.empty:
            r = row50.iloc[0]
            print(f"  Hebel 50: {r['ausgeknockt_%']:.0f} % ausgeknockt, "
                  f"Ergebnis im Mittel {r['mittel_%']:+.0f} % pro Trade")

    if args.csv:
        measured.to_csv(args.csv, index=False)
        print(f"\nRohdaten geschrieben: {args.csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=dt.date.today().isoformat())
    parser.add_argument("--gap", type=float, default=0.04,
                        help="Mindest-Ueberacht-Gap, z.B. 0.04 fuer 4 Prozent")
    parser.add_argument("--volume", type=float, default=2.0,
                        help="Mindestvolumen als Vielfaches des Normalniveaus")
    parser.add_argument("--horizon", type=int, default=5,
                        help="Haltedauer in Handelstagen fuer die Hebelsimulation")
    parser.add_argument("--limit", type=int, default=None,
                        help="nur die ersten N Aktien laden (zum Testen)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--refresh", action="store_true", help="Cache ignorieren")
    parser.add_argument("--csv", default=None, help="Ereignisse als CSV ablegen")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
