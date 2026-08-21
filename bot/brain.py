"""Das "Gehirn": Claude prueft Setups gegen die Lern-Datei und schreibt
nach verlorenen Trades neue Lektionen.

Ohne ANTHROPIC_API_KEY laeuft ein regelbasierter Fallback, damit der Bot
auch offline/im Test funktioniert — dann ohne echtes Lernen per LLM.
"""

import json

from bot.memory import Trade
from bot.strategy import Signal

MODEL = "claude-opus-5"

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["approve", "reason"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are the risk brain of a paper-trading bot. The bot trades a "
    "moving-average-crossover strategy, optionally confirmed by clusters of "
    "insider and congressional buying taken from public disclosures (SEC "
    "Form 4, STOCK Act reports). You are given the bot's self-written lessons "
    "file (rules learned from past losing trades) and a new trade setup. Your "
    "job is to veto setups that repeat a documented mistake and approve setups "
    "that don't conflict with any lesson. Be strict about applying the "
    "lessons, but do not invent new rules that are not in the file. When "
    "disclosure data is included, remember it is always reported with a delay "
    "— treat a large filing lag as weak evidence, not as a live signal. Keep "
    "reasons to one or two sentences."
)


class Brain:
    def __init__(self, api_key: str = ""):
        self.client = None
        if api_key:
            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key)

    # ---------- Pre-Trade-Check ----------

    def evaluate_setup(
        self, symbol: str, signal: Signal, lessons: str, context: str = ""
    ) -> dict:
        """Prueft ein Setup gegen die Lern-Datei. Gibt {approve, reason} zurueck.

        `context` nimmt Zusatzinfos zum Setup auf — z. B. das Insider-Cluster,
        das den Einstieg ausgeloest bzw. bestaetigt hat.
        """
        if self.client is None:
            return {"approve": True, "reason": "No LLM configured — rule-based mode approves all signals."}

        prompt = (
            f"Lessons file:\n---\n{lessons or '(empty — no lessons yet)'}\n---\n\n"
            f"New setup: {signal.action.upper()} {symbol} at {signal.price:.2f}. "
            f"Fast MA {signal.fast_ma:.2f}, slow MA {signal.slow_ma:.2f}.\n"
            + (f"Disclosure data: {context}\n" if context else "")
            + "\nShould this trade be taken?"
        )
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": DECISION_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return {"approve": False, "reason": "Model refused to evaluate this setup."}
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    # ---------- Post-Trade-Review ----------

    def review_losing_trade(self, trade: Trade, lessons: str) -> str:
        """Formuliert nach einem Verlust-Trade eine neue Lektion (Klartext)."""
        if self.client is None:
            return (
                f"{trade.strategy} {trade.side} on {trade.symbol} lost "
                f"{trade.pnl_pct}% (entry {trade.entry_price}, exit {trade.exit_price}). "
                "Review whether the crossover happened in a choppy/sideways market — "
                "consider requiring a wider MA spread before entering."
            )

        prompt = (
            f"Existing lessons file:\n---\n{lessons or '(empty)'}\n---\n\n"
            f"This trade just closed at a loss:\n{json.dumps(trade.__dict__, ensure_ascii=False, indent=2)}\n\n"
            "Write ONE new lesson for the lessons file: a concrete, checkable rule "
            "for future trades that would have avoided or reduced this loss. "
            "Plain text, max 3 sentences. If the existing lessons already cover this "
            "failure, refine the closest existing lesson instead of repeating it. "
            "Reply with the lesson text only."
        )
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return (
                f"Trade {trade.id} on {trade.symbol} lost {trade.pnl_pct}% — "
                "model review unavailable, manual review recommended."
            )
        return next(b.text for b in response.content if b.type == "text").strip()
