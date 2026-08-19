"""Muster selbst suchen statt aus dem Lehrbuch nehmen.

    python -m research.discovery_cli
    python -m research.discovery_cli --kind candle --window 4
    python -m research.discovery_cli --shuffle     # Kontrolllauf ohne echtes Signal
"""

from __future__ import annotations

import argparse
import datetime as dt
import warnings

import numpy as np

from research import data
from research.discovery import (benjamini_hochberg, build_motif_dataset, mine,
                                validate_out_of_sample)
from research.events import prepare_all


def run(args: argparse.Namespace) -> int:
    warnings.filterwarnings("ignore")
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * args.years)
    symbols = data.UNIVERSE[: args.limit] if args.limit else data.UNIVERSE

    print(f"Lade {len(symbols)} Aktien ...")
    frames = data.load_universe(symbols + [data.BENCHMARK], start, end, verbose=False)
    benchmark = frames.pop(data.BENCHMARK)
    prepared = prepare_all(frames)
    prepared_benchmark = prepare_all({data.BENCHMARK: benchmark})[data.BENCHMARK]

    dataset = build_motif_dataset(prepared, prepared_benchmark, window=args.window,
                                  alphabet=args.alphabet, kind=args.kind,
                                  horizon=args.horizon)
    if args.shuffle:
        rng = np.random.default_rng(args.seed)
        dataset = dataset.copy()
        dataset["fwd_abn"] = rng.permutation(dataset["fwd_abn"].to_numpy())
        print("KONTROLLLAUF: Zielwerte durchgewuerfelt. Es GIBT nichts zu finden.\n")

    print(f"{len(dataset):,} Beobachtungen, {dataset['muster'].nunique()} verschiedene Muster")

    found = mine(dataset, min_count=args.min_count)
    if found.empty:
        raise SystemExit("kein Muster kommt oft genug vor -- Fenster verkleinern")

    corrected = benjamini_hochberg(found, alpha=args.alpha)
    nominal = int((found["p"] < 0.05).sum())
    survivors = int(corrected["besteht_fdr"].sum())

    print(f"\n{len(found)} Muster haeufig genug fuer einen Test")
    print(f"  nominell signifikant (p < 0.05): {nominal}")
    print(f"  nach FDR-Korrektur:              {survivors}")
    print(f"  bester t-Wert:                   {found['t'].abs().max():.2f}")
    print(f"\n  Erwartung bei reinem Zufall: rund {len(found) * 0.05:.0f} nominelle Treffer.")

    print("\nDie 10 staerksten Muster (vor Korrektur):")
    print(found.head(10).to_string(index=False, float_format=lambda v: f"{v:8.2f}"))

    if args.split:
        result = validate_out_of_sample(dataset, args.split, min_count=args.min_count,
                                        alpha=args.alpha, top_k=args.top_k)
        checked = result["geprueft"]
        if not checked.empty:
            held = int(checked["haelt"].sum())
            print(f"\n=== Im Training gesucht, ab {args.split} geprueft ===")
            print(checked.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))
            print(f"\n  Vorzeichen gehalten: {held} von {len(checked)} "
                  f"({held/len(checked)*100:.0f} %)")
            print("  Bei reinem Zufall waeren es rund 50 %.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("shape", "candle"), default="shape")
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--alphabet", type=int, choices=(3, 4, 5), default=4)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--min-count", type=int, default=200)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--split", default="2021-01-01")
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--years", type=int, default=11)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
