"""Ein Video von der Idee bis zur fertigen Datei — resumierbar.

Jeder Schritt schreibt seinen Stand nach `state.json`. Bricht etwas ab (Timeout,
Kontingent leer, Rechner aus), macht derselbe Aufruf genau dort weiter: schon
generierte Clips werden nicht neu erzeugt.

    output/<kanal>/<datum-thema-id>/
        state.json        Stand der Produktion
        script.json       Skript mit allen Beats
        clip_01.mp4 ...   die einzelnen Clips
        clip_01.prompt.txt  (im Assisted-Modus)
        voice_01.mp3 ...  Voiceover je Clip
        work/             Zwischenschritte des Schnitts
        final.mp4         das fertige Video
        post.md           Caption, Hashtags, Sprechtext zum Posten
"""

import json
import os
from dataclasses import asdict

from tiktok import creative
from tiktok.assemble import assemble
from tiktok.channels import Channel
from tiktok.config import Config
from tiktok.llm import LLM
from tiktok.memory import VideoMemory, VideoRecord, utc_now
from tiktok.providers.base import ClipResult


class Pipeline:
    def __init__(self, config: Config, channel: Channel, llm: LLM, memory: VideoMemory, provider, voice):
        self.config = config
        self.channel = channel
        self.llm = llm
        self.memory = memory
        self.provider = provider
        self.voice = voice

    # ---------- Zustand ----------

    @staticmethod
    def _load_state(job_dir: str) -> dict:
        path = os.path.join(job_dir, "state.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return {}

    @staticmethod
    def _save_state(job_dir: str, state: dict) -> None:
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "state.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)

    # ---------- Produktion ----------

    def produce(self, job_dir: str = "", music: str = "") -> str:
        state = self._load_state(job_dir) if job_dir else {}

        # 1. Idee — die einzige Stelle, an der Wiederholung verhindert wird.
        idea = state.get("idea")
        if not idea:
            idea = creative.generate_idea(self.llm, self.channel, self.memory)
            self.memory.remember(self.channel.slug, idea)
            print(f"[idee] {idea['topic']} — {idea['hook']}")

        record = VideoRecord(
            channel=self.channel.slug,
            topic=idea.get("topic", ""),
            subject=idea.get("subject", ""),
            hook=idea.get("hook", ""),
            style=idea.get("style", ""),
        )
        # Beim Fortsetzen bleiben ID und Datum gleich, damit der Ordner derselbe ist.
        record.id = state.get("id", record.id)
        record.created_at = state.get("created_at", record.created_at)
        job_dir = job_dir or os.path.join(self.config.output_dir, self.channel.slug, record.slug)
        os.makedirs(job_dir, exist_ok=True)
        state.update({"idea": idea, "id": record.id, "created_at": record.created_at,
                      "channel": self.channel.slug, "job_dir": job_dir})
        self._save_state(job_dir, state)

        # 2. Skript
        script = state.get("script")
        if not script:
            script = creative.generate_script(self.llm, self.channel, idea)
            state["script"] = script
            self._save_state(job_dir, state)
            with open(os.path.join(job_dir, "script.json"), "w", encoding="utf-8") as fh:
                json.dump(script, fh, ensure_ascii=False, indent=2)
        beats = script["beats"]
        print(f"[skript] {script.get('title', '')} — {len(beats)} Clips")

        # 3. Clips: der erste neu, jeder weitere als Fortsetzung des vorherigen.
        clips = [ClipResult(**c) for c in state.get("clips", [])]
        for index, beat in enumerate(beats):
            if index < len(clips) and os.path.exists(clips[index].path):
                continue
            prompt = creative.clip_prompt(self.channel, beat, index)
            out_path = os.path.join(job_dir, f"clip_{index + 1:02d}.mp4")
            print(f"[clip {index + 1}/{len(beats)}] {beat.get('role')} — generiere ...")

            if index == 0 or not getattr(self.provider, "supports_extend", False):
                clip = self.provider.generate(
                    prompt, self.channel.clip_seconds, self.channel.aspect_ratio, out_path
                )
            else:
                clip = self.provider.extend(
                    prompt, self.channel.clip_seconds, clips[index - 1], out_path
                )

            clips = clips[:index] + [clip]
            state["clips"] = [asdict(c) for c in clips]
            self._save_state(job_dir, state)

        # 4. Voiceover je Clip — so setzt der Text synchron zum Bildwechsel ein.
        narration = state.get("narration", [])
        if len(narration) != len(beats):
            narration = []
            for index, beat in enumerate(beats):
                text = str(beat.get("voiceover", "")).strip()
                out_path = os.path.join(job_dir, f"voice_{index + 1:02d}.mp3")
                if os.path.exists(out_path):
                    narration.append(out_path)
                    continue
                narration.append(self.voice.speak(text, out_path) if text else "")
            state["narration"] = narration
            self._save_state(job_dir, state)

        # 5. Schnitt
        print("[schnitt] normalisiere, haenge zusammen, mische Ton ...")
        final_path = assemble(
            self.config, job_dir, [c.path for c in clips], narration, beats, music=music
        )

        # 6. Alles, was zum Posten noch gebraucht wird
        self._write_post_notes(job_dir, script)
        record.beats = beats
        record.clips = [asdict(c) for c in clips]
        record.final_path = final_path
        record.status = "done"
        record.finished_at = utc_now()
        self.memory.append(record)
        state["final_path"] = final_path
        state["status"] = "done"
        self._save_state(job_dir, state)
        print(f"[fertig] {final_path}")
        return final_path

    def _write_post_notes(self, job_dir: str, script: dict) -> None:
        hashtags = " ".join(script.get("hashtags") or self.channel.hashtags)
        lines = [
            f"# {script.get('title', '')}",
            "",
            "## Caption",
            script.get("caption", ""),
            "",
            "## Hashtags",
            hashtags,
            "",
            "## Sprechtext",
            creative.full_voiceover(script),
            "",
            "## Beats",
        ]
        for i, beat in enumerate(script.get("beats", []), start=1):
            lines.append(
                f"{i}. [{beat.get('role')}] {beat.get('voiceover', '')}"
                + (f"  \n   Text im Bild: {beat['on_screen_text']}" if beat.get("on_screen_text") else "")
            )
        lines += ["", "## Noch offen", "- Musik drunterlegen", "- Auf TikTok posten"]
        with open(os.path.join(job_dir, "post.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
