"""Assisted-Modus: Prompts raus, Clips rein.

Ohne API-Zugang bleibt der Weg ueber die Weboberflaeche. Statt den Browser
fernzusteuern (das verstoesst gegen die Nutzungsbedingungen und ist genau das,
was Anbieter als Bot erkennen), macht dieser Provider die Handarbeit so klein
wie moeglich:

  1. Er schreibt den fertigen Prompt in den Job-Ordner — copy&paste-fertig,
     inklusive der Einstellungen, die im Interface gesetzt werden muessen.
  2. Er wartet, bis die fertige Datei im Ordner liegt (`clip_01.mp4` usw.).
  3. Sobald sie da ist, laeuft die Pipeline von allein weiter: naechster Prompt,
     Voiceover, Schnitt, fertiges Video.

Aus 20 Minuten Arbeit pro Video werden so ein paar Klicks — und alles davor und
danach passiert automatisch.
"""

import os
import time

from tiktok.config import Config
from tiktok.providers.base import ClipResult, GenerationFailed

VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".m4v")


class AssistedProvider:
    name = "assisted"
    supports_extend = True

    def __init__(self, config: Config):
        self.config = config
        self.poll = max(5, config.poll_interval_seconds)

    def generate(self, prompt: str, seconds: int, aspect_ratio: str, out_path: str) -> ClipResult:
        return self._await_clip(prompt, seconds, out_path, aspect_ratio, source=None)

    def extend(self, prompt: str, seconds: int, source: ClipResult, out_path: str) -> ClipResult:
        return self._await_clip(prompt, seconds, out_path, "", source=source)

    def _await_clip(self, prompt: str, seconds: int, out_path: str, aspect_ratio: str, source: ClipResult | None) -> ClipResult:
        folder = os.path.dirname(out_path) or "."
        os.makedirs(folder, exist_ok=True)
        stem = os.path.splitext(os.path.basename(out_path))[0]
        index = int(stem.split("_")[-1] or 0)

        instructions = self._instructions(prompt, seconds, aspect_ratio, source, out_path)
        with open(os.path.join(folder, f"{stem}.prompt.txt"), "w", encoding="utf-8") as fh:
            fh.write(instructions)
        print(f"\n{instructions}\n", flush=True)

        deadline = time.monotonic() + self.config.generation_timeout_seconds
        while time.monotonic() < deadline:
            found = self._find_clip(folder, stem, out_path)
            if found:
                return ClipResult(
                    index=index,
                    path=found,
                    prompt=prompt,
                    video_id=found,
                    seconds=float(seconds),
                )
            time.sleep(self.poll)

        raise GenerationFailed(
            f"Kein Clip fuer {stem} in {folder} innerhalb von "
            f"{self.config.generation_timeout_seconds}s. Datei ablegen und Job erneut starten "
            "(bereits fertige Clips werden uebersprungen)."
        )

    @staticmethod
    def _find_clip(folder: str, stem: str, out_path: str) -> str:
        """Akzeptiert den exakten Dateinamen oder eine Datei, die mit dem Stamm beginnt."""
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(VIDEO_SUFFIXES):
                continue
            if name.startswith(stem) and os.path.getsize(os.path.join(folder, name)) > 0:
                return os.path.join(folder, name)
        return ""

    def _instructions(self, prompt: str, seconds: int, aspect_ratio: str, source: ClipResult | None, out_path: str) -> str:
        stem = os.path.basename(out_path)
        mode = (
            f"EXTEND vom vorherigen Clip ({os.path.basename(source.path)})"
            if source
            else "NEUE Generierung (Text-to-Video)"
        )
        return (
            "=" * 72
            + f"\n{mode}\n"
            + "=" * 72
            + f"\nModell:  {self.config.video_model}"
            + f"\nLaenge:  {seconds}s"
            + f"\nFormat:  {aspect_ratio or '9:16 (wie der vorherige Clip)'}"
            + "\n\nPROMPT (kopieren):\n"
            + "-" * 72
            + f"\n{prompt}\n"
            + "-" * 72
            + f"\n\nFertigen Clip hier ablegen:\n  {out_path}\n"
            f"Die Pipeline prueft alle {self.poll}s und laeuft dann von allein weiter."
        )
