"""Kanalprofile — die "Bibel" je Account.

Ein Profil legt fest, wie ein Kanal aussieht, klingt und denkt: Persona,
visueller Stil, Stimme, Videolaenge, thematischer Korridor. Alles, was pro
Kanal konstant bleibt, steht hier — damit die Videos untereinander wie eine
Serie wirken und nicht wie 50 zufaellige Clips.
"""

import json
import os
from dataclasses import dataclass, field


@dataclass
class Channel:
    slug: str
    name: str
    language: str = "de"
    persona: str = ""
    # Die Kanal-Bibel: was dieser Account ist, fuer wen, mit welchem Versprechen.
    bible: str = ""
    # Wird an JEDEN Clip-Prompt angehaengt — sorgt fuer den Wiedererkennungswert.
    visual_style: str = ""
    negative_prompt: str = ""
    # Thematischer Korridor, aus dem Ideen kommen duerfen.
    domains: list[str] = field(default_factory=list)
    # Ideen-Winkel, die rotiert werden, damit nicht jedes Video gleich gebaut ist.
    angles: list[str] = field(default_factory=list)
    target_seconds: int = 40
    clip_seconds: int = 10
    # Sprechgeschwindigkeit fuer das Wortbudget je Clip (Deutsch: ~2,4 Woerter/s).
    words_per_second: float = 2.4
    voice: dict = field(default_factory=dict)
    hashtags: list[str] = field(default_factory=list)
    cta: str = ""
    aspect_ratio: str = "9:16"

    @property
    def clip_count(self) -> int:
        return max(1, round(self.target_seconds / self.clip_seconds))

    def word_budget(self, seconds: float) -> int:
        return max(1, round(seconds * self.words_per_second))

    @classmethod
    def from_dict(cls, data: dict) -> "Channel":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def load_channel(slug: str, channels_dir: str = "channels") -> Channel:
    path = slug if slug.endswith(".json") else os.path.join(channels_dir, f"{slug}.json")
    if not os.path.exists(path):
        available = ", ".join(list_channels(channels_dir)) or "(keine)"
        raise FileNotFoundError(f"Kanalprofil {path} nicht gefunden. Vorhanden: {available}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("slug", os.path.splitext(os.path.basename(path))[0])
    return Channel.from_dict(data)


def list_channels(channels_dir: str = "channels") -> list[str]:
    if not os.path.isdir(channels_dir):
        return []
    return sorted(
        os.path.splitext(f)[0] for f in os.listdir(channels_dir) if f.endswith(".json")
    )
