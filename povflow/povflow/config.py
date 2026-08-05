"""Configuration loading.

Config is TOML (stdlib `tomllib`) and secrets come from a `.env` file parsed
here, so the only third-party dependency in the whole project is `google-genai`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

BACKENDS = frozenset({"omni", "veo"})

# Per-second USD output rates, Gemini API, August 2026. Override in config if
# Google changes them — `povflow costs` prints what is actually being used.
DEFAULT_RATES: dict[str, float] = {
    "gemini-omni-flash-preview:720p": 0.10,
    "veo-3.1-lite-generate-preview:720p": 0.05,
    "veo-3.1-lite-generate-preview:1080p": 0.08,
    "veo-3.1-fast-generate-preview:720p": 0.10,
    "veo-3.1-fast-generate-preview:1080p": 0.12,
    "veo-3.1-generate-preview:720p": 0.40,
    "veo-3.1-generate-preview:1080p": 0.40,
}

# Omni billing details. Chained shots re-send the previous clip as context and
# that is billed as video input tokens, which the per-second rate does not cover.
OMNI_VIDEO_TOKENS_PER_SECOND = 5792   # 720p
OMNI_INPUT_USD_PER_1M_TOKENS = 1.50

# Hard limits of the Omni Flash preview model.
OMNI_MIN_CLIP_SECONDS = 3
OMNI_MAX_CLIP_SECONDS = 10
OMNI_RESOLUTIONS = frozenset({"720p"})


class ConfigError(Exception):
    """Raised when the config file is missing or internally inconsistent."""


@dataclass
class Config:
    backend: str
    chain_shots: bool

    niche: str
    style_preset: str
    audience: str
    language: str
    concept_brief: str
    forbidden: list[str]

    model: str
    idea_model: str
    resolution: str
    aspect_ratio: str
    seconds_per_shot: int
    shots_per_episode: int
    keep_ambient_audio: bool
    ambient_audio_gain_db: float

    max_usd_per_run: float
    max_usd_per_month: float
    rates: dict[str, float]

    output_dir: Path
    state_db: Path
    poll_interval_s: int
    max_retries: int

    api_key: str | None = field(default=None, repr=False)

    @property
    def rate_key(self) -> str:
        return f"{self.model}:{self.resolution}"

    @property
    def usd_per_second(self) -> float:
        rate = self.rates.get(self.rate_key)
        if rate is None:
            raise ConfigError(
                f"No price known for {self.rate_key!r}. Add it under [costs.rates] "
                f"in your config. Known: {sorted(self.rates)}"
            )
        return rate

    @property
    def chained_input_usd_per_shot(self) -> float:
        """Extra input cost each chained shot carries beyond the output rate."""
        if self.backend != "omni" or not self.chain_shots:
            return 0.0
        tokens = self.seconds_per_shot * OMNI_VIDEO_TOKENS_PER_SECOND
        return tokens / 1_000_000 * OMNI_INPUT_USD_PER_1M_TOKENS

    @property
    def usd_per_episode(self) -> float:
        output = self.usd_per_second * self.seconds_per_shot * self.shots_per_episode
        # The first shot starts the chain, so only the rest carry input cost.
        chained_shots = max(0, self.shots_per_episode - 1)
        return output + self.chained_input_usd_per_shot * chained_shots

    @property
    def episode_seconds(self) -> int:
        return self.seconds_per_shot * self.shots_per_episode


def load_env(path: Path) -> dict[str, str]:
    """Parse a minimal .env file. Real environment variables win over the file."""
    values: dict[str, str] = {}
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config(config_path: Path, env_path: Path | None = None) -> Config:
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")

    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)

    root = config_path.parent
    env_path = env_path or root / ".env"
    file_env = load_env(env_path)
    api_key = os.environ.get("GEMINI_API_KEY") or file_env.get("GEMINI_API_KEY")

    channel = raw.get("channel", {})
    video = raw.get("video", {})
    costs = raw.get("costs", {})
    paths = raw.get("paths", {})
    runtime = raw.get("runtime", {})

    rates = dict(DEFAULT_RATES)
    rates.update(costs.get("rates", {}))

    def _path(value: str) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else (root / p).resolve()

    backend = str(video.get("backend", "omni")).lower()
    default_model = (
        "gemini-omni-flash-preview" if backend == "omni"
        else "veo-3.1-fast-generate-preview"
    )

    cfg = Config(
        backend=backend,
        chain_shots=bool(video.get("chain_shots", True)),
        niche=channel.get("niche", "fantasy"),
        style_preset=channel.get("style_preset", "fantasy"),
        audience=channel.get("audience", "TikTok and Reels, 16-30"),
        language=channel.get("language", "de"),
        concept_brief=channel.get("concept_brief", ""),
        forbidden=list(channel.get("forbidden", [])),
        model=video.get("model", default_model),
        idea_model=video.get("idea_model", "gemini-2.5-flash"),
        resolution=video.get("resolution", "720p"),
        aspect_ratio=video.get("aspect_ratio", "9:16"),
        seconds_per_shot=int(video.get("seconds_per_shot", 8)),
        shots_per_episode=int(video.get("shots_per_episode", 5)),
        keep_ambient_audio=bool(video.get("keep_ambient_audio", True)),
        ambient_audio_gain_db=float(video.get("ambient_audio_gain_db", -18.0)),
        max_usd_per_run=float(costs.get("max_usd_per_run", 6.0)),
        max_usd_per_month=float(costs.get("max_usd_per_month", 120.0)),
        rates=rates,
        output_dir=_path(paths.get("output_dir", "output")),
        state_db=_path(paths.get("state_db", "state/povflow.sqlite3")),
        poll_interval_s=int(runtime.get("poll_interval_s", 15)),
        max_retries=int(runtime.get("max_retries", 3)),
        api_key=api_key,
    )

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.backend not in BACKENDS:
        raise ConfigError(
            f"backend must be one of {sorted(BACKENDS)}, got {cfg.backend!r}"
        )
    if cfg.shots_per_episode < 1:
        raise ConfigError("shots_per_episode must be at least 1")
    if cfg.seconds_per_shot < 1:
        raise ConfigError("seconds_per_shot must be at least 1")
    if cfg.aspect_ratio not in {"9:16", "16:9"}:
        raise ConfigError(f"aspect_ratio must be '9:16' or '16:9', got {cfg.aspect_ratio!r}")
    if cfg.resolution not in {"720p", "1080p"}:
        raise ConfigError(f"resolution must be '720p' or '1080p', got {cfg.resolution!r}")
    if cfg.max_usd_per_run <= 0 or cfg.max_usd_per_month <= 0:
        raise ConfigError("Budget caps must be positive")

    if cfg.backend == "omni":
        if cfg.resolution not in OMNI_RESOLUTIONS:
            raise ConfigError(
                f"Gemini Omni Flash only outputs 720p, config says {cfg.resolution!r}. "
                f'Set resolution = "720p", or use backend = "veo" for 1080p.'
            )
        if not OMNI_MIN_CLIP_SECONDS <= cfg.seconds_per_shot <= OMNI_MAX_CLIP_SECONDS:
            raise ConfigError(
                f"Gemini Omni Flash produces {OMNI_MIN_CLIP_SECONDS}-"
                f"{OMNI_MAX_CLIP_SECONDS}s clips, config says {cfg.seconds_per_shot}s."
            )

    # Catch an impossible budget at load time rather than after paying for shot 1.
    if cfg.usd_per_episode > cfg.max_usd_per_run:
        raise ConfigError(
            f"One episode costs about ${cfg.usd_per_episode:.2f} "
            f"({cfg.shots_per_episode} shots x {cfg.seconds_per_shot}s at "
            f"${cfg.usd_per_second:.2f}/s) which is over max_usd_per_run of "
            f"${cfg.max_usd_per_run:.2f}. Raise the cap or shorten the episode."
        )
