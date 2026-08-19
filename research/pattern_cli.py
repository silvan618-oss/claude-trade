"""Kerzenmuster einzeln vermessen: was macht die naechste Kerze?

    python -m research.pattern_cli
    python -m research.pattern_cli --horizon 5 --split 2021-01-01
    python -m research.pattern_cli --raw       # ohne Marktbereinigung (zeigt den Drift-Effekt)
"""

from __future__ import annotations

import argparse
import datetime as dt
import warnings

import pandas as pd

from research import data
from research.events import prepare_all
from research.patterns import build_pattern_dataset, evaluate

# Bonferroni-Schwelle fuer rund 25 gleichzeitig getestete Muster, 5 % Niveau.
THRESHOLD = 2.8


def run(args: argparse.Namespace) -> int:
    warnings.filterwarnings("ignore")
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * args.years)
    symbols = data.UNIVERSE[: args.limit] if args.limit else data.UNIVERSE

    print(f"Lade {len(symbols)} Aktien ...")
    frames = data.load_universe(symbols + [data.BENCHMARK], start, end, verbose=False)
    benchmark = frames.pop(data.BENCHMARK, None)
    prepared = prepare_all(frames)
    prepared_benchmark = (prepare_all({data.BENCHMARK: benchmark})[data.BENCHMARK]
                          if benchmark is not None else None)

    dataset = build_pattern_dataset(prepared, horizon=args.horizon,
                                    benchmark=prepared_benchmark)
    column = "fwd" if args.raw or prepared_benchmark is None else "fwd_abn"

    result = evaluate(dataset, column=column)
    print(f"\n{len(dataset):,} Kerzen, {dataset['symbol'].nunique()} Aktien, "
          f"Horizont {args.horizon} Kerze(n)")
    print(f"Auswertung: {'roh' if column == 'fwd' else 'marktbereinigt'}")
    print(f"Basisrate: {result.attrs['basisrate_%']:.2f} %  <- das ist die Messlatte, nicht 50 %\n")
    print(result.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

    biggest = result["t_geclustert"].abs().max()
    print(f"\n{len(result)} Muster getestet -> belastbar erst ab |t| > {THRESHOLD}.")
    print(f"Groesster gemessener |t|: {biggest:.2f}"
          f"  {'-> nichts ueberschreitet die Schwelle' if biggest < THRESHOLD else ''}")

    if args.split:
        cut = pd.Timestamp(args.split)
        first = evaluate(dataset[dataset["date"] < cut], column=column).set_index("muster")
        second = evaluate(dataset[dataset["date"] >= cut], column=column).set_index("muster")
        joined = pd.DataFrame({
            "treffer_1H_%": first["treffer_%"], "t_1H": first["t_geclustert"],
            "treffer_2H_%": second["treffer_%"], "t_2H": second["t_geclustert"],
        }).dropna().sort_values("t_1H", ascending=False)

        print(f"\n=== Haelt es sich? Trennung bei {cut.date()} ===")
        print(joined.to_string(float_format=lambda v: f"{v:9.2f}"))
        correlation = joined["t_1H"].corr(joined["t_2H"])
        print(f"\nKorrelation der t-Werte zwischen den Haelften: {correlation:+.3f}")
        print("Waeren die Muster echt, muesste ein gutes Muster in beiden Haelften gut sein.")
        print("Ein Wert nahe null heisst: die erste Haelfte sagt nichts ueber die zweite.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=int, default=11)
    parser.add_argument("--horizon", type=int, default=1, help="Kerzen vorwaerts")
    parser.add_argument("--split", default="2021-01-01",
                        help="Datum fuer die Haelften-Probe, leer zum Abschalten")
    parser.add_argument("--raw", action="store_true", help="ohne Marktbereinigung")
    parser.add_argument("--limit", type=int, default=None)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
