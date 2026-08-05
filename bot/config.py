"""Zentrale Konfiguration — alles kommt aus Umgebungsvariablen (.env)."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class Config:
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_paper: bool = os.getenv("ALPACA_PAPER", "true").lower() != "false"

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    symbols: list[str] = field(
        default_factory=lambda: _split_symbols(os.getenv("SYMBOLS", "AAPL,MSFT,SPY"))
    )
    fast_ma: int = int(os.getenv("FAST_MA", "9"))
    slow_ma: int = int(os.getenv("SLOW_MA", "21"))
    # Positionsgroesse als Prozent des Kapitals (Video-Empfehlung: 1-3 %)
    risk_pct: float = float(os.getenv("RISK_PCT", "2.0"))
    loop_interval_seconds: int = int(os.getenv("LOOP_INTERVAL_SECONDS", "300"))

    ledger_path: str = os.getenv("LEDGER_PATH", "memory/ledger.jsonl")
    lessons_path: str = os.getenv("LESSONS_PATH", "memory/lessons.md")

    @property
    def has_alpaca(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)
