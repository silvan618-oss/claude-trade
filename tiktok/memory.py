"""Gedaechtnis gegen Wiederholung.

Der teuerste Fehler eines Auto-Content-Systems ist, dass es sich wiederholt:
gleiches Tier, gleicher Hook, gleicher Kamerastil, gleicher Einstiegssatz.
TikTok bestraft das sofort.

Zwei Dateien, analog zum Trading-Bot:
    memory/videos.jsonl  — Ledger: jedes produzierte Video mit allen Parametern
    memory/used.json     — Kurzgedaechtnis je Kanal: Themen, Subjekte, Hook-Muster,
                           Stile und Eroeffnungssaetze, die schon verbraucht sind
    memory/video_lessons.md — Klartext-Regeln, die sich das System selbst schreibt
"""

import json
import os
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# Fuellwoerter, die beim Vergleich zweier Ideen nichts aussagen.
_STOPWORDS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen",
    "und", "oder", "aber", "wie", "was", "wer", "wo", "wann", "warum", "ist", "sind", "war",
    "im", "in", "am", "an", "auf", "mit", "von", "vom", "zu", "zum", "zur", "fuer", "ueber",
    "sich", "es", "er", "sie", "man", "nicht", "kein", "keine", "the", "a", "an", "of", "and",
    "to", "in", "on", "for", "with", "that", "this", "how", "why", "what", "is", "are",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    """Kleinschreibung, Umlaute aufgeloest, nur Buchstaben und Zahlen."""
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) > 2 and w not in _STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Jaccard-Aehnlichkeit zweier Texte zwischen 0 und 1."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass
class VideoRecord:
    channel: str
    topic: str
    subject: str
    hook: str
    style: str
    beats: list = field(default_factory=list)
    clips: list = field(default_factory=list)
    final_path: str = ""
    status: str = "planned"
    error: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=utc_now)
    finished_at: str | None = None

    @property
    def slug(self) -> str:
        base = normalize(self.topic).replace(" ", "-")[:60] or "video"
        return f"{self.created_at[:10]}-{base}-{self.id[:6]}"


class VideoMemory:
    # Ab dieser Aehnlichkeit gilt eine Idee als Wiederholung.
    SIMILARITY_LIMIT = 0.55
    # So viele vergangene Eintraege bekommt das Modell als Negativliste zu sehen.
    RECALL = 60

    def __init__(self, ledger_path: str, used_path: str, lessons_path: str = ""):
        self.ledger_path = ledger_path
        self.used_path = used_path
        self.lessons_path = lessons_path
        for path in (ledger_path, used_path, lessons_path):
            if path:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._used = self._load_used()

    # ---------- Ledger ----------

    def append(self, record: VideoRecord) -> None:
        with open(self.ledger_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def all_records(self) -> list[dict]:
        if not os.path.exists(self.ledger_path):
            return []
        with open(self.ledger_path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    # ---------- Kurzgedaechtnis ----------

    def _load_used(self) -> dict:
        if os.path.exists(self.used_path):
            with open(self.used_path, encoding="utf-8") as fh:
                return json.load(fh)
        return {}

    def _save_used(self) -> None:
        with open(self.used_path, "w", encoding="utf-8") as fh:
            json.dump(self._used, fh, ensure_ascii=False, indent=2)

    def channel_memory(self, channel: str) -> dict:
        return self._used.setdefault(
            channel, {"topics": [], "subjects": [], "hooks": [], "styles": [], "first_lines": []}
        )

    def remember(self, channel: str, idea: dict) -> None:
        """Merkt sich eine benutzte Idee, damit sie nie wieder kommt."""
        mem = self.channel_memory(channel)
        for key, value in (
            ("topics", idea.get("topic", "")),
            ("subjects", idea.get("subject", "")),
            ("hooks", idea.get("hook", "")),
            ("styles", idea.get("style", "")),
            ("first_lines", idea.get("first_line", "")),
        ):
            value = (value or "").strip()
            if value and value not in mem[key]:
                mem[key].append(value)
        self._save_used()

    def repeat_reason(self, channel: str, idea: dict) -> str:
        """Gibt den Grund zurueck, warum eine Idee eine Wiederholung ist — sonst ""."""
        mem = self.channel_memory(channel)
        checks = (
            ("topics", "topic", "Thema"),
            ("subjects", "subject", "Subjekt/Tier"),
            ("hooks", "hook", "Hook"),
            ("first_lines", "first_line", "Eroeffnungssatz"),
        )
        for key, field_name, label in checks:
            new = (idea.get(field_name) or "").strip()
            if not new:
                continue
            for old in mem[key]:
                if normalize(new) == normalize(old):
                    return f"{label} schon benutzt: {old!r}"
                if similarity(new, old) >= self.SIMILARITY_LIMIT:
                    return f"{label} zu aehnlich zu {old!r}"
        return ""

    def avoid_block(self, channel: str) -> str:
        """Negativliste fuer den Prompt — was es garantiert nicht nochmal geben darf."""
        mem = self.channel_memory(channel)
        if not any(mem.values()):
            return "(noch nichts produziert — freie Wahl)"
        lines = []
        for key, label in (
            ("subjects", "Bereits verwendete Subjekte/Tiere"),
            ("topics", "Bereits verwendete Themen"),
            ("hooks", "Bereits verwendete Hooks"),
            ("first_lines", "Bereits verwendete Eroeffnungssaetze"),
            ("styles", "Bereits verwendete Stile"),
        ):
            values = mem[key][-self.RECALL:]
            if values:
                lines.append(f"{label}:\n" + "\n".join(f"  - {v}" for v in values))
        return "\n".join(lines)

    # ---------- Lern-Datei ----------

    def lessons(self) -> str:
        if self.lessons_path and os.path.exists(self.lessons_path):
            with open(self.lessons_path, encoding="utf-8") as fh:
                return fh.read()
        return ""

    def add_lesson(self, lesson: str) -> None:
        if not self.lessons_path or not lesson.strip():
            return
        with open(self.lessons_path, "a", encoding="utf-8") as fh:
            fh.write(f"- [{utc_now()[:10]}] {lesson.strip()}\n")
