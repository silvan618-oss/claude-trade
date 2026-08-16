"""End-to-End-Test der Pipeline mit Attrappen statt echter Dienste.

Geprueft wird die Verdrahtung: Idee -> Skript -> Clip-Kette per extend ->
Voiceover -> Schnitt, und dass ein abgebrochener Job genau dort weitermacht.
"""

import json
import os

import pytest

from tiktok import pipeline as pipeline_module
from tiktok.channels import Channel
from tiktok.config import Config
from tiktok.memory import VideoMemory
from tiktok.pipeline import Pipeline
from tiktok.providers.base import ClipResult


class FakeLLM:
    """Liefert eine feste Idee und ein gueltiges Skript."""

    def __init__(self, clips: int = 4):
        self.clips = clips
        self.calls = []

    def json(self, system, prompt, tier="creative", temperature=1.0):
        self.calls.append(tier)
        if "Entwickle EINE neue Videoidee" in prompt:
            return {
                "topic": "Jagd des Wanderfalken",
                "subject": "Wanderfalke",
                "hook": "schneller als ein Rennwagen",
                "first_line": "Nichts faellt schneller.",
                "style": "Zeitlupe aus der Luft",
                "angle": "Zahl, die absurd klingt",
                "payoff": "389 km/h",
                "why_it_works": "Zahl loest die Schleife erst am Ende",
            }
        return {
            "title": "Wanderfalke",
            "caption": "389 km/h im Sturzflug",
            "hashtags": ["#tiere"],
            "beats": [
                {
                    "voiceover": f"Satz {i} mit genug Woertern fuer das Budget dieses Clips hier",
                    "video_prompt": f"peregrine falcon shot {i}",
                    "camera": f"kamera {i}",
                    "on_screen_text": "",
                }
                for i in range(self.clips)
            ],
        }


class FakeProvider:
    name = "fake"
    supports_extend = True

    def __init__(self):
        self.generated = 0
        self.extended = 0
        self.anchors = []

    def _write(self, out_path, prompt, index):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(b"video")
        return ClipResult(index=index, path=out_path, prompt=prompt, video_id=out_path, seconds=10)

    def generate(self, prompt, seconds, aspect_ratio, out_path):
        self.generated += 1
        return self._write(out_path, prompt, 0)

    def extend(self, prompt, seconds, source, out_path):
        self.extended += 1
        self.anchors.append(source.path)
        return self._write(out_path, prompt, source.index + 1)


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text, out_path):
        self.spoken.append(text)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(b"audio")
        return out_path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = Config()
    config.output_dir = str(tmp_path / "output")
    channel = Channel(
        slug="test", name="Test", visual_style="cinematic", target_seconds=40, clip_seconds=10
    )
    memory = VideoMemory(
        str(tmp_path / "videos.jsonl"), str(tmp_path / "used.json"), str(tmp_path / "lessons.md")
    )
    calls = {"assemble": 0}

    def fake_assemble(config, job_dir, clip_paths, narration_paths, beats, music="", final_name="final.mp4"):
        calls["assemble"] += 1
        calls["clips"] = list(clip_paths)
        calls["narration"] = list(narration_paths)
        final = os.path.join(job_dir, final_name)
        with open(final, "wb") as fh:
            fh.write(b"final")
        return final

    monkeypatch.setattr(pipeline_module, "assemble", fake_assemble)
    return config, channel, memory, calls


def test_produce_baut_ein_vollstaendiges_video(setup):
    config, channel, memory, calls = setup
    llm, provider, voice = FakeLLM(), FakeProvider(), FakeVoice()

    final = Pipeline(config, channel, llm, memory, provider, voice).produce()

    assert os.path.exists(final)
    # Erster Clip neu, alle weiteren als Fortsetzung.
    assert provider.generated == 1
    assert provider.extended == 3
    # Jedes extend haengt am direkt vorherigen Clip.
    assert [os.path.basename(a) for a in provider.anchors] == [
        "clip_01.mp4", "clip_02.mp4", "clip_03.mp4",
    ]
    assert len(voice.spoken) == 4
    assert calls["assemble"] == 1
    assert len(calls["clips"]) == 4


def test_produce_schreibt_post_notizen_und_ledger(setup):
    config, channel, memory, _ = setup
    Pipeline(config, channel, FakeLLM(), memory, FakeProvider(), FakeVoice()).produce()

    job_dir = os.path.dirname(memory.all_records()[0]["final_path"])
    post = open(os.path.join(job_dir, "post.md"), encoding="utf-8").read()
    assert "## Caption" in post and "389 km/h" in post
    assert "Musik drunterlegen" in post

    record = memory.all_records()[0]
    assert record["channel"] == "test" and record["status"] == "done"
    assert len(record["clips"]) == 4


def test_idee_wird_fuer_kuenftige_videos_gesperrt(setup):
    config, channel, memory, _ = setup
    Pipeline(config, channel, FakeLLM(), memory, FakeProvider(), FakeVoice()).produce()
    assert memory.repeat_reason("test", {"subject": "Wanderfalke"})


def test_resume_generiert_fertige_clips_nicht_neu(setup):
    config, channel, memory, _ = setup
    provider = FakeProvider()
    pipeline = Pipeline(config, channel, FakeLLM(), memory, provider, FakeVoice())
    final = pipeline.produce()
    job_dir = os.path.dirname(final)

    # Abbruch simulieren: die letzten beiden Clips fehlen wieder.
    for name in ("clip_03.mp4", "clip_04.mp4"):
        os.remove(os.path.join(job_dir, name))
    before_generated, before_extended = provider.generated, provider.extended

    Pipeline(config, channel, FakeLLM(), memory, provider, FakeVoice()).produce(job_dir=job_dir)

    assert provider.generated == before_generated  # Clip 1 bleibt unangetastet
    assert provider.extended == before_extended + 2  # nur die zwei fehlenden Clips


def test_resume_erzeugt_keine_zweite_idee(setup):
    config, channel, memory, _ = setup
    llm = FakeLLM()
    pipeline = Pipeline(config, channel, llm, memory, FakeProvider(), FakeVoice())
    job_dir = os.path.dirname(pipeline.produce())
    calls_before = len(llm.calls)

    Pipeline(config, channel, llm, memory, FakeProvider(), FakeVoice()).produce(job_dir=job_dir)
    # Idee und Skript stehen im state.json — kein weiterer LLM-Aufruf noetig.
    assert len(llm.calls) == calls_before


def test_state_json_haelt_den_kompletten_stand(setup):
    config, channel, memory, _ = setup
    final = Pipeline(config, channel, FakeLLM(), memory, FakeProvider(), FakeVoice()).produce()
    state = json.load(open(os.path.join(os.path.dirname(final), "state.json"), encoding="utf-8"))
    assert state["status"] == "done"
    assert len(state["clips"]) == 4 and len(state["narration"]) == 4
    assert state["idea"]["subject"] == "Wanderfalke"
