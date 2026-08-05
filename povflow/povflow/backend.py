"""Shared generation primitives.

Both backends produce Clips and both are subject to the same budget rules, so
those live here rather than in either backend module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .state import Store


class BudgetExceeded(Exception):
    """Raised before spending money that would break a configured cap."""


class GenerationError(Exception):
    """Raised when a backend fails to produce a clip after all retries."""


@dataclass
class Clip:
    index: int
    path: Path
    seconds: float
    usd: float


def check_budget(cfg: Config, store: Store, planned_usd: float) -> None:
    """Refuse a run that would break the run cap or the month cap."""
    if planned_usd > cfg.max_usd_per_run + 1e-9:
        raise BudgetExceeded(
            f"This run would cost about ${planned_usd:.2f}, over the "
            f"max_usd_per_run cap of ${cfg.max_usd_per_run:.2f}."
        )
    spent = store.spend_this_month()
    if spent + planned_usd > cfg.max_usd_per_month + 1e-9:
        raise BudgetExceeded(
            f"Month-to-date spend is ${spent:.2f}. This run would add "
            f"${planned_usd:.2f} and break the monthly cap of "
            f"${cfg.max_usd_per_month:.2f}."
        )
