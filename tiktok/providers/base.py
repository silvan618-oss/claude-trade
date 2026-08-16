"""Gemeinsames Interface aller Video-Provider."""

import os
import shutil
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


class GenerationFailed(RuntimeError):
    """Der Provider hat den Job abgelehnt oder er ist fehlgeschlagen."""


class ProviderBusy(RuntimeError):
    """Es laeuft schon eine Generierung — bei Plaenen mit nur einem Slot normal."""


@dataclass
class ClipResult:
    """Ein fertiger Clip. `video_id` ist der Anker fuer das naechste extend."""

    index: int
    path: str
    prompt: str
    job_id: str = ""
    video_id: str = ""
    url: str = ""
    seconds: float = 0.0
    meta: dict = field(default_factory=dict)


class VideoProvider(Protocol):
    name: str
    # Kann der Provider an einen bestehenden Clip anhaengen (statt neu zu starten)?
    supports_extend: bool

    def generate(self, prompt: str, seconds: int, aspect_ratio: str, out_path: str) -> ClipResult:
        ...

    def extend(self, prompt: str, seconds: int, source: ClipResult, out_path: str) -> ClipResult:
        ...


def download(url: str, out_path: str) -> str:
    """Laedt eine Videodatei herunter (oder kopiert sie, wenn es ein lokaler Pfad ist)."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if url.startswith(("http://", "https://")):
        with urllib.request.urlopen(url, timeout=300) as response, open(out_path, "wb") as fh:
            shutil.copyfileobj(response, fh)
    else:
        shutil.copyfile(url, out_path)
    return out_path
