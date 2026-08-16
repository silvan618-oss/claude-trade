"""Die Stimme "Silver".

Zwei Wege, beide ueber ElevenLabs:

  tts   Text -> Sprache. Der Standard, weil vollautomatisch.
  sts   Speech-to-Speech: eine vorhandene Aufnahme wird auf die Zielstimme
        umgelegt. Sinnvoll, wenn die Betonung von einer echten Aufnahme kommen
        soll, die Stimme aber Silver sein muss.

Ohne API-Key laeuft ein Null-Provider: die Pipeline erzeugt dann ein Video ohne
Voiceover und legt den Sprechtext als .txt daneben.
"""

import json
import os
import urllib.error
import urllib.request
import uuid

from tiktok.channels import Channel
from tiktok.config import Config

API_BASE = "https://api.elevenlabs.io/v1"


class VoiceError(RuntimeError):
    pass


class NullVoice:
    """Kein Key, keine Stimme — der Text wird nur mitgeschrieben."""

    name = "none"
    available = False

    def speak(self, text: str, out_path: str) -> str:
        with open(os.path.splitext(out_path)[0] + ".txt", "w", encoding="utf-8") as fh:
            fh.write(text)
        return ""


class ElevenLabsVoice:
    name = "elevenlabs"
    available = True

    def __init__(self, config: Config, channel: Channel):
        self.config = config
        self.voice = channel.voice or {}
        self.voice_id = self.voice.get("voice_id", "")
        if not config.elevenlabs_api_key:
            raise VoiceError("ELEVENLABS_API_KEY fehlt.")
        if not self.voice_id:
            raise VoiceError(
                f"Im Kanalprofil fehlt voice.voice_id — die Stimmen-ID von Silver eintragen."
            )

    def _settings(self) -> dict:
        return {
            "stability": self.voice.get("stability", 0.45),
            "similarity_boost": self.voice.get("similarity_boost", 0.8),
            "style": self.voice.get("style", 0.35),
            "use_speaker_boost": True,
            "speed": self.voice.get("speed", 1.0),
        }

    def speak(self, text: str, out_path: str) -> str:
        """Text-to-Speech in die Zielstimme."""
        body = json.dumps(
            {
                "text": text,
                "model_id": self.config.elevenlabs_model,
                "voice_settings": self._settings(),
            }
        ).encode()
        request = urllib.request.Request(
            f"{API_BASE}/text-to-speech/{self.voice_id}", data=body, method="POST"
        )
        request.add_header("xi-api-key", self.config.elevenlabs_api_key)
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "audio/mpeg")
        return self._download(request, out_path)

    def convert(self, audio_path: str, out_path: str) -> str:
        """Speech-to-Speech: vorhandene Aufnahme auf die Zielstimme umlegen."""
        with open(audio_path, "rb") as fh:
            audio = fh.read()
        fields = {
            "model_id": os.getenv("ELEVENLABS_STS_MODEL", "eleven_multilingual_sts_v2"),
            "voice_settings": json.dumps(self._settings()),
        }
        body, content_type = _multipart(fields, "audio", os.path.basename(audio_path), audio)
        request = urllib.request.Request(
            f"{API_BASE}/speech-to-speech/{self.voice_id}", data=body, method="POST"
        )
        request.add_header("xi-api-key", self.config.elevenlabs_api_key)
        request.add_header("Content-Type", content_type)
        request.add_header("Accept", "audio/mpeg")
        return self._download(request, out_path)

    @staticmethod
    def _download(request, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        try:
            with urllib.request.urlopen(request, timeout=300) as response, open(out_path, "wb") as fh:
                fh.write(response.read())
        except urllib.error.HTTPError as exc:
            raise VoiceError(
                f"ElevenLabs HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}"
            ) from exc
        return out_path


def _multipart(fields: dict, file_field: str, filename: str, content: bytes) -> tuple[bytes, str]:
    """Minimaler multipart/form-data-Encoder — spart die requests-Abhaengigkeit."""
    boundary = f"----tiktok{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: audio/mpeg\r\n\r\n".encode()
    )
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def build_voice(config: Config, channel: Channel):
    provider = (channel.voice.get("provider") or config.voice_provider).lower()
    if provider in ("none", "off", ""):
        return NullVoice()
    if provider == "elevenlabs":
        try:
            return ElevenLabsVoice(config, channel)
        except VoiceError as exc:
            print(f"[voice] {exc} — Video wird ohne Voiceover gebaut.")
            return NullVoice()
    raise VoiceError(f"Unbekannter VOICE_PROVIDER: {provider}")
