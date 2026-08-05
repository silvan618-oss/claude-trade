"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .state import Store

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help=f"path to config.toml (default: {DEFAULT_CONFIG})",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="povflow",
        description="Generate first-person POV shorts and a matching voice-over script.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="produce episodes")
    _add_common(run)
    run.add_argument("-n", "--count", type=int, default=1, help="episodes to produce")
    run.add_argument(
        "--dry-run", action="store_true",
        help="plan everything and write the scripts, generate no video, spend nothing",
    )
    run.add_argument(
        "--keep-intermediates", action="store_true",
        help="keep the per-clip working files after assembly",
    )

    costs = sub.add_parser("costs", help="show rates, budget caps and month-to-date spend")
    _add_common(costs)

    history = sub.add_parser("history", help="list produced episodes")
    _add_common(history)
    history.add_argument("-n", "--count", type=int, default=20)

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    from .pipeline import run_batch

    cfg = load_config(args.config)
    store = Store(cfg.state_db)

    if args.dry_run:
        print("DRY RUN — no video is generated and nothing is charged.\n")
    else:
        estimate = cfg.usd_per_episode * args.count
        print(f"About to generate {args.count} episode(s), "
              f"{cfg.episode_seconds}s each, estimated ${estimate:.2f} total.\n")

    results = run_batch(
        cfg, store, args.count, dry_run=args.dry_run,
        keep_intermediates=args.keep_intermediates,
    )

    if not results:
        print("\nNo episodes produced.")
        return 1

    print(f"\n{'=' * 60}")
    for result in results:
        print(f"\n{result.concept.title}")
        print(f"  folder: {result.directory}")
        if result.video_path:
            print(f"  video:  {result.video_path.name}  (silent cut, record over this)")
        elif result.dry_run:
            print("  video:  none (dry run)")
        else:
            print("  video:  not assembled — raw clips are in shots/")
        print(f"  script: {result.script_path.name}")

    total = sum(r.usd_spent for r in results)
    if total:
        print(f"\nSpent this run: ${total:.2f}")
        print(f"Month to date:  ${store.spend_this_month():.2f} "
              f"of ${cfg.max_usd_per_month:.2f}")
    return 0


def cmd_costs(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.state_db)
    spent = store.spend_this_month()

    print(f"Model:        {cfg.model} at {cfg.resolution}")
    print(f"Rate:         ${cfg.usd_per_second:.3f} per second")
    print(f"Episode:      {cfg.shots_per_episode} shots x {cfg.seconds_per_shot}s "
          f"= {cfg.episode_seconds}s -> ${cfg.usd_per_episode:.2f}")
    print(f"Run cap:      ${cfg.max_usd_per_run:.2f}")
    print(f"Month cap:    ${cfg.max_usd_per_month:.2f}")
    print(f"Spent (MTD):  ${spent:.2f}  ({spent / cfg.max_usd_per_month * 100:.0f}%)")
    remaining = max(0.0, cfg.max_usd_per_month - spent)
    print(f"Remaining:    ${remaining:.2f} "
          f"= about {int(remaining // cfg.usd_per_episode)} more episode(s)")
    print("\nKnown rates:")
    for key, rate in sorted(cfg.rates.items()):
        print(f"  {key:48s} ${rate:.3f}/s")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = Store(cfg.state_db)
    titles = store.recent_titles(args.count)
    if not titles:
        print("No episodes yet.")
        return 0
    print(f"Last {len(titles)} episode(s), newest first:\n")
    for title in titles:
        print(f"  {title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"run": cmd_run, "costs": cmd_costs, "history": cmd_history}
    try:
        return handlers[args.command](args)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
