"""Die Dauerschleife: produziert Video um Video, solange Kontingent da ist.

Verhalten bei Problemen:
  Kontingent leer   -> warten und es spaeter nochmal versuchen (nicht abbrechen)
  Generierung kaputt-> Job als fehlgeschlagen ablegen, naechstes Video starten
  Kostenlimit       -> sauber beenden
  Datei STOP        -> sauber beenden (fuer "bitte nach diesem Video aufhoeren")

Mehrere Kanaele werden reihum bedient, damit kein Account leer laeuft.
"""

import os
import time
import traceback

from tiktok.channels import Channel, load_channel
from tiktok.config import Config
from tiktok.llm import LLM, QuotaExhausted
from tiktok.memory import VideoMemory
from tiktok.pipeline import Pipeline
from tiktok.providers import build_provider
from tiktok.voice import build_voice

# Wartezeiten, wenn das Kontingent leer ist: erst kurz, dann laenger.
QUOTA_BACKOFF = [900, 1800, 3600, 3600]


class Runner:
    def __init__(self, config: Config, channel_slugs: list[str], music: str = ""):
        self.config = config
        self.music = music
        self.channels: list[Channel] = [
            load_channel(slug, config.channels_dir) for slug in channel_slugs
        ]
        if not self.channels:
            raise ValueError("Keine Kanaele angegeben.")
        self.llm = LLM(config)
        self.memory = VideoMemory(config.ledger_path, config.used_path, config.lessons_path)
        self.produced = 0
        self.failed = 0

    def _pipeline(self, channel: Channel) -> Pipeline:
        # Provider und Stimme haengen am Kanal, deshalb pro Video neu gebaut.
        return Pipeline(
            self.config,
            channel,
            self.llm,
            self.memory,
            build_provider(self.config),
            build_voice(self.config, channel),
        )

    def _should_stop(self) -> str:
        if os.path.exists(self.config.stop_file):
            return f"STOP-Datei gefunden ({self.config.stop_file})."
        if self.config.max_videos_per_run and self.produced >= self.config.max_videos_per_run:
            return f"{self.produced} Videos produziert — Limit erreicht."
        if self.config.max_usd_per_run and self.llm.spent_usd >= self.config.max_usd_per_run:
            return f"Kostenlimit erreicht ({self.llm.spent_usd:.2f} USD)."
        return ""

    def produce_one(self, channel: Channel) -> str:
        return self._pipeline(channel).produce(music=self.music)

    def run(self) -> None:
        print(
            f"[runner] Kanaele: {', '.join(c.slug for c in self.channels)} | "
            f"LLM: {self.llm.backend} | Video: {self.config.video_provider}"
        )
        quota_strikes = 0
        index = 0

        while True:
            reason = self._should_stop()
            if reason:
                print(f"[runner] Ende: {reason}")
                return

            channel = self.channels[index % len(self.channels)]
            index += 1
            try:
                self.produce_one(channel)
                self.produced += 1
                quota_strikes = 0
                print(
                    f"[runner] {self.produced} Videos fertig, {self.failed} Fehler, "
                    f"{self.llm.spent_usd:.2f} USD LLM-Kosten."
                )
                time.sleep(self.config.loop_pause_seconds)

            except QuotaExhausted as exc:
                wait = QUOTA_BACKOFF[min(quota_strikes, len(QUOTA_BACKOFF) - 1)]
                quota_strikes += 1
                print(f"[runner] Kontingent erschoepft ({str(exc)[:200]}). Warte {wait // 60} Minuten.")
                time.sleep(wait)

            except KeyboardInterrupt:
                print("\n[runner] Abbruch durch Nutzer.")
                return

            except Exception as exc:
                self.failed += 1
                print(f"[runner] Fehler bei {channel.slug}: {exc}")
                traceback.print_exc()
                # Aus Fehlern lernen, damit derselbe Griff nicht dauernd schiefgeht.
                self.memory.add_lesson(f"Fehler auf {channel.slug}: {str(exc)[:200]}")
                if self.failed >= 5 and self.produced == 0:
                    print("[runner] Fuenf Fehler ohne einen Erfolg — Setup pruefen. Ende.")
                    return
                time.sleep(self.config.loop_pause_seconds)
