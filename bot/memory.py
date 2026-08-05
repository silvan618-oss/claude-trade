"""Das Zwei-Datei-Gedaechtnis — der wichtigste Baustein aus dem Video.

Datei 1: Ledger (memory/ledger.jsonl)
    Loggt jeden Trade mit allen Parametern als eine JSON-Zeile.
    Append-only, damit nichts verloren geht.

Datei 2: Lern-Datei (memory/lessons.md)
    Klartext-Regeln, die sich der Bot selbst schreibt, wenn ein Trade
    fehlschlaegt. Wird vor jedem neuen Trade wieder eingelesen, damit
    derselbe Fehler nicht zweimal passiert.

Fuer High-Frequency-Setups laesst sich diese Schicht 1:1 gegen eine
Cloud-Datenbank wie Supabase tauschen — die Schnittstelle bleibt gleich.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Trade:
    symbol: str
    side: str  # "long" (Short-Seite bewusst weggelassen fuer den Start)
    qty: float
    entry_price: float
    strategy: str
    params: dict = field(default_factory=dict)
    reason: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    opened_at: str = field(default_factory=_now)
    closed_at: str | None = None
    exit_price: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    status: str = "open"  # "open" | "closed"


class Memory:
    def __init__(self, ledger_path: str, lessons_path: str):
        self.ledger_path = ledger_path
        self.lessons_path = lessons_path
        os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(lessons_path) or ".", exist_ok=True)

    # ---------- Ledger ----------

    def log_trade(self, trade: Trade) -> None:
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(trade), ensure_ascii=False) + "\n")

    def all_trades(self) -> list[Trade]:
        if not os.path.exists(self.ledger_path):
            return []
        trades: dict[str, Trade] = {}
        with open(self.ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                # Spaetere Eintraege mit derselben ID ueberschreiben fruehere
                # (Open-Eintrag wird durch Close-Eintrag ersetzt).
                trades[data["id"]] = Trade(**data)
        return list(trades.values())

    def open_trade(self, symbol: str) -> Trade | None:
        for trade in self.all_trades():
            if trade.symbol == symbol and trade.status == "open":
                return trade
        return None

    def close_trade(self, trade: Trade, exit_price: float) -> Trade:
        trade.exit_price = exit_price
        trade.closed_at = _now()
        trade.pnl = round((exit_price - trade.entry_price) * trade.qty, 2)
        trade.pnl_pct = round(
            (exit_price - trade.entry_price) / trade.entry_price * 100, 2
        )
        trade.status = "closed"
        self.log_trade(trade)
        return trade

    def stats(self) -> dict:
        closed = [t for t in self.all_trades() if t.status == "closed"]
        wins = [t for t in closed if (t.pnl or 0) > 0]
        return {
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(closed) - len(wins),
            "total_pnl": round(sum(t.pnl or 0 for t in closed), 2),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
        }

    # ---------- Lern-Datei ----------

    def read_lessons(self) -> str:
        if not os.path.exists(self.lessons_path):
            return ""
        with open(self.lessons_path, encoding="utf-8") as f:
            return f.read()

    def add_lesson(self, lesson: str) -> None:
        header_needed = not os.path.exists(self.lessons_path)
        with open(self.lessons_path, "a", encoding="utf-8") as f:
            if header_needed:
                f.write(
                    "# Lessons Learned\n\n"
                    "Regeln, die sich der Bot aus fehlgeschlagenen Trades "
                    "selbst geschrieben hat. Wird vor jedem Trade gelesen.\n"
                )
            f.write(f"\n## {_now()}\n{lesson.strip()}\n")
