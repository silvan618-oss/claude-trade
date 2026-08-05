"""Episode history: idea de-duplication and month-to-date spend.

SQLite via the stdlib. The spend ledger is what makes the budget cap meaningful
across runs — without it every run would start from zero.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    logline     TEXT NOT NULL,
    concept     TEXT NOT NULL,
    idea_hash   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'planned',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_episodes_hash ON episodes(idea_hash);

CREATE TABLE IF NOT EXISTS spend (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id  INTEGER,
    usd         REAL NOT NULL,
    seconds     REAL NOT NULL,
    model       TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY(episode_id) REFERENCES episodes(id)
);
CREATE INDEX IF NOT EXISTS idx_spend_created ON spend(created_at);
"""

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_STOPWORDS = frozenset(
    """a an the and or of in on at to for with is are was were be been it its
    der die das ein eine und oder von im in auf zu fuer mit ist sind war""".split()
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str, max_len: int = 60) -> str:
    ascii_text = (
        text.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    slug = _SLUG_STRIP.sub("-", ascii_text).strip("-")
    return slug[:max_len].rstrip("-") or "episode"


def idea_fingerprint(title: str, logline: str) -> str:
    """Content hash that ignores word order and filler.

    Two ideas phrased differently but built from the same nouns collapse to the
    same fingerprint, which is the repetition that actually hurts a channel.
    """
    words = re.findall(r"[a-zäöüß0-9]+", f"{title} {logline}".lower())
    meaningful = sorted({w for w in words if w not in _STOPWORDS and len(w) > 2})
    return hashlib.sha256(" ".join(meaningful).encode("utf-8")).hexdigest()[:32]


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- episodes ---------------------------------------------------------

    def known_fingerprints(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT idea_hash FROM episodes").fetchall()
        return {r["idea_hash"] for r in rows}

    def recent_titles(self, limit: int = 40) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT title FROM episodes ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [r["title"] for r in rows]

    def add_episode(self, title: str, logline: str, concept: dict) -> tuple[int, str]:
        fingerprint = idea_fingerprint(title, logline)
        base_slug = slugify(title)
        with self._connect() as conn:
            slug = base_slug
            suffix = 2
            while conn.execute(
                "SELECT 1 FROM episodes WHERE slug = ?", (slug,)
            ).fetchone():
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            cur = conn.execute(
                "INSERT INTO episodes (slug, title, logline, concept, idea_hash, "
                "status, created_at) VALUES (?, ?, ?, ?, ?, 'planned', ?)",
                (slug, title, logline, json.dumps(concept, ensure_ascii=False),
                 fingerprint, _now()),
            )
            return int(cur.lastrowid), slug

    def set_status(self, episode_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE episodes SET status = ? WHERE id = ?", (status, episode_id)
            )

    # -- spend ------------------------------------------------------------

    def record_spend(
        self, usd: float, seconds: float, model: str,
        episode_id: int | None = None, note: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO spend (episode_id, usd, seconds, model, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (episode_id, usd, seconds, model, note, _now()),
            )

    def spend_this_month(self, today: date | None = None) -> float:
        today = today or datetime.now(timezone.utc).date()
        prefix = f"{today.year:04d}-{today.month:02d}"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(usd), 0.0) AS total FROM spend "
                "WHERE created_at LIKE ?",
                (f"{prefix}%",),
            ).fetchone()
        return float(row["total"])
