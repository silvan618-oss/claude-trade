"""Claude als Kreativ-Gehirn — mit zwei Backends.

"cli":  ruft die Claude Code CLI auf (`claude -p`). Laeuft ueber das eigene
        Abo-Kontingent, kostet also nichts extra, solange Kontingent da ist.
        Ist das Kontingent aufgebraucht, meldet die CLI das — die Dauerschleife
        pausiert dann, statt Geld zu verbrennen.
"api":  Anthropic API mit Key, wird pro Token abgerechnet. Zuverlaessiger fuer
        24/7, aber eben kostenpflichtig.

Beide liefern JSON zurueck. Kostenseitig gibt es zwei Modellstufen:
`creative` (teuer, fuer Ideen und Skripte) und `utility` (guenstig, fuer
Metadaten, Titel, Hashtags, Kurzchecks).
"""

import json
import re
import shutil
import subprocess

from tiktok.config import Config


class QuotaExhausted(RuntimeError):
    """Kontingent/Rate-Limit erreicht — die Dauerschleife soll warten, nicht abbrechen."""


class LLMError(RuntimeError):
    pass


# Muster, an denen sich ein erschoepftes Kontingent erkennen laesst.
_QUOTA_MARKERS = (
    "usage limit",
    "rate limit",
    "rate_limit",
    "quota",
    "overloaded",
    "429",
    "resets at",
    "insufficient credit",
)


def _looks_like_quota(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _QUOTA_MARKERS)


def extract_json(text: str) -> dict:
    """Holt das erste JSON-Objekt aus einer Modellantwort.

    Modelle packen JSON gern in ```json-Bloecke oder schreiben einen Satz davor —
    beides faengt diese Funktion ab.
    """
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    for candidate in candidates:
        candidate = candidate.strip()
        start = candidate.find("{")
        if start == -1:
            continue
        # Von hinten nach vorn probieren: die letzte schliessende Klammer ist
        # bei sauberen Antworten das Ende des Objekts.
        for end in range(len(candidate), start, -1):
            if candidate[end - 1] != "}":
                continue
            try:
                return json.loads(candidate[start:end])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Keine gueltige JSON-Antwort im Modelloutput:\n{text[:800]}")


class LLM:
    """Duennes Interface: rein Prompt, raus JSON."""

    def __init__(self, config: Config):
        self.config = config
        self.backend = self._pick_backend(config)
        self._client = None
        # Grobe Kostenschaetzung fuer den API-Pfad, damit MAX_USD_PER_RUN greift.
        self.spent_usd = 0.0

    @staticmethod
    def _pick_backend(config: Config) -> str:
        backend = config.llm_backend.lower()
        if backend != "auto":
            return backend
        if shutil.which(config.claude_cli):
            return "cli"
        if config.has_anthropic:
            return "api"
        raise LLMError(
            "Kein LLM-Backend: weder die Claude-CLI gefunden noch ANTHROPIC_API_KEY gesetzt."
        )

    def model_for(self, tier: str) -> str:
        return self.config.model_creative if tier == "creative" else self.config.model_utility

    # ---------- oeffentliche API ----------

    def json(self, system: str, prompt: str, tier: str = "creative", temperature: float = 1.0) -> dict:
        """Fragt das Modell und parst die Antwort als JSON."""
        raw = self.text(system, prompt, tier=tier, temperature=temperature)
        return extract_json(raw)

    def text(self, system: str, prompt: str, tier: str = "creative", temperature: float = 1.0) -> str:
        if self.backend == "cli":
            return self._via_cli(system, prompt, tier)
        return self._via_api(system, prompt, tier, temperature)

    # ---------- Backends ----------

    def _via_cli(self, system: str, prompt: str, tier: str) -> str:
        """Claude Code CLI im Print-Modus — laeuft auf dem Abo-Kontingent."""
        cmd = [
            self.config.claude_cli,
            "-p",
            prompt,
            "--model",
            self.model_for(tier),
            "--output-format",
            "json",
            "--append-system-prompt",
            system,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.llm_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"Claude-CLI Timeout nach {self.config.llm_timeout_seconds}s") from exc

        combined = f"{proc.stdout}\n{proc.stderr}"
        if proc.returncode != 0:
            if _looks_like_quota(combined):
                raise QuotaExhausted(combined.strip()[:500])
            raise LLMError(f"Claude-CLI Fehler ({proc.returncode}): {combined.strip()[:500]}")

        # --output-format json liefert einen Umschlag mit dem Ergebnis in "result".
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return proc.stdout
        if isinstance(envelope, dict):
            if envelope.get("is_error") and _looks_like_quota(str(envelope)):
                raise QuotaExhausted(str(envelope)[:500])
            self.spent_usd += float(envelope.get("total_cost_usd") or 0.0)
            result = envelope.get("result")
            if isinstance(result, str):
                return result
        return proc.stdout

    def _via_api(self, system: str, prompt: str, tier: str, temperature: float) -> str:
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_api_key)

        try:
            response = self._client.messages.create(
                model=self.model_for(tier),
                max_tokens=8000,
                temperature=temperature,
                # Der Kanal-"Bibel"-Teil steckt im System-Prompt und wiederholt
                # sich bei jedem Video — Caching spart dort echtes Geld.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # anthropic.RateLimitError u. a.
            if _looks_like_quota(str(exc)):
                raise QuotaExhausted(str(exc)[:500]) from exc
            raise

        self.spent_usd += self._estimate_cost(tier, response)
        return "".join(block.text for block in response.content if block.type == "text")

    # Preise pro 1M Token (Stand Doku); nur fuer die Kostenbremse, nicht fuer die Buchhaltung.
    _PRICES = {
        "creative": (5.0, 25.0),
        "utility": (1.0, 5.0),
    }

    def _estimate_cost(self, tier: str, response) -> float:
        price_in, price_out = self._PRICES.get(tier, self._PRICES["utility"])
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0.0
        return (
            getattr(usage, "input_tokens", 0) * price_in
            + getattr(usage, "output_tokens", 0) * price_out
        ) / 1_000_000
