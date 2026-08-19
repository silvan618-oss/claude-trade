"""Mustererkennung testen: lernt ein Modell die Zukunft oder die Vergangenheit auswendig?

    python -m research.ml_cli
    python -m research.ml_cli --model rf --train-years 6 --test-months 12
    python -m research.ml_cli --shuffle          # Kontrollprobe mit Zufallsziel
"""

from __future__ import annotations

import argparse
import datetime as dt
import warnings

from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research import data
from research.events import prepare_all
from research.ml import build_dataset, feature_columns, trade_top_decile, walk_forward

MODELS = {
    "gb": ("Gradient Boosting",
           lambda: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05,
                                                  max_depth=6, random_state=0)),
    "rf": ("Random Forest",
           lambda: RandomForestClassifier(n_estimators=150, min_samples_leaf=5,
                                          n_jobs=-1, random_state=0)),
    "lr": ("Logistische Regression",
           lambda: make_pipeline(SimpleImputer(), StandardScaler(),
                                 LogisticRegression(max_iter=1000))),
}


def run(args: argparse.Namespace) -> int:
    warnings.filterwarnings("ignore")
    label, factory = MODELS[args.model]

    end = dt.date.today()
    start = end - dt.timedelta(days=365 * args.years)
    symbols = data.UNIVERSE[: args.limit] if args.limit else data.UNIVERSE

    print(f"Lade {len(symbols)} Aktien ...")
    frames = data.load_universe(symbols + [data.BENCHMARK], start, end, verbose=False)
    benchmark = frames.pop(data.BENCHMARK, None)
    prepared = prepare_all(frames)
    prepared_benchmark = prepare_all({data.BENCHMARK: benchmark})[data.BENCHMARK] if benchmark is not None else None

    dataset = build_dataset(prepared, prepared_benchmark)
    base_rate = dataset["ziel_hoch"].mean() * 100
    print(f"{len(dataset):,} Zeilen, {len(feature_columns(dataset))} Merkmale, "
          f"{dataset['symbol'].nunique()} Aktien")
    print(f"Basisrate: {base_rate:.2f} % der Tage steigen -- so gut ist 'immer aufwaerts tippen'\n")

    if args.shuffle:
        print("KONTROLLPROBE: Ziel wird durchgewuerfelt. Es gibt nichts zu lernen.\n")

    print(f"Walk-Forward mit {label} "
          f"(Training {args.train_years} Jahre, Test {args.test_months} Monate):")
    result = walk_forward(dataset, factory, train_years=args.train_years,
                          test_months=args.test_months, shuffle_target=args.shuffle)

    gap = (result.mean_in_sample - result.mean_out_sample) * 100
    print(f"\n  Im Training:  {result.mean_in_sample*100:6.2f} %")
    print(f"  Ungesehen:    {result.mean_out_sample*100:6.2f} %   "
          f"(Basisrate {base_rate:.2f} %)")
    print(f"  Luecke:       {gap:6.2f} Prozentpunkte")
    if gap > 5:
        print("  -> Die Luecke ist das Auswendiglernen. Sie sagt nichts ueber Koennen aus.")

    print("\nHandel: taeglich das zuversichtlichste Zehntel")
    for cost in (0.0, args.cost_bp):
        stats = trade_top_decile(result.predictions, cost_bp=cost)
        if stats:
            print(f"  bei {cost:4.0f} bp Kosten: Treffer {stats['trefferquote_%']:5.2f} %  "
                  f"Mittel {stats['mittel_bp']:+6.2f} bp  Sharpe {stats['sharpe']:+5.2f}  "
                  f"Kapital x{stats['kapital_faktor']:.3f}")
    print("\nVergleiche das Ergebnis IMMER mit --shuffle. Was der Zufall auch schafft, "
          "ist kein Koennen.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(MODELS), default="gb")
    parser.add_argument("--years", type=int, default=11, help="Historie in Jahren")
    parser.add_argument("--train-years", type=int, default=4)
    parser.add_argument("--test-months", type=int, default=12)
    parser.add_argument("--cost-bp", type=float, default=10.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--shuffle", action="store_true",
                        help="Ziel durchwuerfeln (Kontrollprobe)")
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
