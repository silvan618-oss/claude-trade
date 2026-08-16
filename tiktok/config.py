"""Zentrale Konfiguration — alles kommt aus Umgebungsvariablen (.env)."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, "true" if default else "false").lower() not in ("false", "0", "no")


@dataclass
class Config:
    # ---------- Claude als Kreativ-Gehirn ----------
    # "cli"  = Claude Code CLI (`claude -p`) und damit das eigene Abo-Kontingent
    # "api"  = Anthropic API, wird pro Token abgerechnet
    # "auto" = CLI wenn vorhanden, sonst API
    llm_backend: str = os.getenv("LLM_BACKEND", "auto")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_cli: str = os.getenv("CLAUDE_CLI", "claude")
    # Zwei Stufen, damit Kosten dort bleiben, wo Kreativitaet wirklich zaehlt.
    model_creative: str = os.getenv("MODEL_CREATIVE", "claude-opus-5")
    model_utility: str = os.getenv("MODEL_UTILITY", "claude-haiku-4-5-20251001")
    llm_timeout_seconds: int = _int("LLM_TIMEOUT_SECONDS", 600)

    # ---------- Video-Provider ----------
    # "higgsfield" = HTTP-API, "higgsfield_cli" = lokale Higgsfield-CLI,
    # "assisted"   = Prompts werden rausgeschrieben, Clips landen manuell im Job-Ordner
    video_provider: str = os.getenv("VIDEO_PROVIDER", "assisted")
    higgsfield_api_key: str = os.getenv("HIGGSFIELD_API_KEY", "")
    higgsfield_base_url: str = os.getenv("HIGGSFIELD_BASE_URL", "https://api.higgsfield.ai")
    # Endpunkte/Feldnamen sind bewusst auslagerbar, weil sich die API-Signatur
    # aendern kann — siehe providers/higgsfield.schema.json.
    higgsfield_schema: str = os.getenv("HIGGSFIELD_SCHEMA", "tiktok/providers/higgsfield.schema.json")
    higgsfield_cli: str = os.getenv("HIGGSFIELD_CLI", "higgsfield")
    video_model: str = os.getenv("VIDEO_MODEL", "seedance-2.5")
    clip_seconds: int = _int("CLIP_SECONDS", 10)
    # Eine Generierung gleichzeitig — mehr laesst der Plan ohnehin nicht zu.
    poll_interval_seconds: int = _int("POLL_INTERVAL_SECONDS", 20)
    generation_timeout_seconds: int = _int("GENERATION_TIMEOUT_SECONDS", 1800)

    # ---------- Stimme ----------
    voice_provider: str = os.getenv("VOICE_PROVIDER", "elevenlabs")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_model: str = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

    # ---------- Ausgabe ----------
    output_dir: str = os.getenv("OUTPUT_DIR", "output")
    channels_dir: str = os.getenv("CHANNELS_DIR", "channels")
    ledger_path: str = os.getenv("VIDEO_LEDGER_PATH", "memory/videos.jsonl")
    used_path: str = os.getenv("VIDEO_USED_PATH", "memory/used.json")
    lessons_path: str = os.getenv("VIDEO_LESSONS_PATH", "memory/video_lessons.md")

    # ---------- Dauerschleife ----------
    loop_pause_seconds: int = _int("LOOP_PAUSE_SECONDS", 60)
    max_videos_per_run: int = _int("MAX_VIDEOS_PER_RUN", 0)  # 0 = unbegrenzt
    # Harte Bremse gegen Ausreisser, wenn ueber die API abgerechnet wird.
    max_usd_per_run: float = _float("MAX_USD_PER_RUN", 0.0)  # 0 = kein Limit
    stop_file: str = os.getenv("STOP_FILE", "output/STOP")

    ffmpeg: str = os.getenv("FFMPEG", "ffmpeg")
    ffprobe: str = os.getenv("FFPROBE", "ffprobe")
    target_resolution: str = os.getenv("TARGET_RESOLUTION", "1080x1920")
    target_fps: int = _int("TARGET_FPS", 30)
    burn_subtitles: bool = _bool("BURN_SUBTITLES", False)

    extra: dict = field(default_factory=dict)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def width(self) -> int:
        return int(self.target_resolution.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.target_resolution.split("x")[1])


def load_config() -> Config:
    return Config()
