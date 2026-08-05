"""Veo 3.1 clip generation.

Google bills per successfully generated second, so the budget check happens
before each request and the ledger is written immediately after each success.
A crash mid-episode therefore cannot lose spend that already happened.
"""

from __future__ import annotations

import time
from pathlib import Path

from .backend import Clip, GenerationError
from .config import Config
from .shotlist import ShotPrompt
from .state import Store


def _build_video_config(cfg: Config, shot: ShotPrompt):
    from google.genai import types

    kwargs: dict[str, object] = {
        "aspect_ratio": cfg.aspect_ratio,
        "resolution": cfg.resolution,
        "negative_prompt": shot.negative_prompt,
        "number_of_videos": 1,
    }
    # duration_seconds is not accepted by every Veo revision; drop it rather than
    # fail the whole run on an unknown field.
    try:
        return types.GenerateVideosConfig(duration_seconds=shot.seconds, **kwargs)
    except (TypeError, ValueError):
        return types.GenerateVideosConfig(**kwargs)


def generate_clip(
    cfg: Config, store: Store, shot: ShotPrompt, dest: Path, episode_id: int | None
) -> Clip:
    """Generate one clip, with retries. Records spend on success."""
    from google import genai

    client = genai.Client(api_key=cfg.api_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, cfg.max_retries + 1):
        try:
            operation = client.models.generate_videos(
                model=cfg.model,
                prompt=shot.prompt,
                config=_build_video_config(cfg, shot),
            )

            waited = 0
            while not operation.done:
                time.sleep(cfg.poll_interval_s)
                waited += cfg.poll_interval_s
                if waited > 900:
                    raise GenerationError(f"Shot {shot.index} timed out after 15 minutes")
                operation = client.operations.get(operation)

            if getattr(operation, "error", None):
                raise GenerationError(f"Veo reported: {operation.error}")

            videos = getattr(operation.response, "generated_videos", None) or []
            if not videos:
                raise GenerationError("Veo returned no video in the response")

            video = videos[0].video
            client.files.download(file=video)
            video.save(str(dest))

            if not dest.is_file() or dest.stat().st_size == 0:
                raise GenerationError(f"Downloaded clip is empty: {dest}")

            usd = cfg.usd_per_second * shot.seconds
            store.record_spend(
                usd=usd, seconds=float(shot.seconds), model=cfg.model,
                episode_id=episode_id, note=f"shot {shot.index}",
            )
            return Clip(index=shot.index, path=dest, seconds=float(shot.seconds), usd=usd)

        except Exception as exc:  # noqa: BLE001 - retry any transient API failure
            last_error = exc
            if attempt < cfg.max_retries:
                backoff = 2 ** attempt
                print(f"    shot {shot.index} attempt {attempt} failed ({exc}); "
                      f"retrying in {backoff}s")
                time.sleep(backoff)

    raise GenerationError(
        f"Shot {shot.index} failed after {cfg.max_retries} attempts: {last_error}"
    ) from last_error
