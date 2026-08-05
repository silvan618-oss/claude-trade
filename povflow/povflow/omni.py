"""Gemini Omni Flash backend.

The reason this backend exists: Omni's Interactions API chains turns via
`previous_interaction_id`, so shot 2 is generated with the model still holding
shot 1's scene. Veo generates every clip cold, which is where continuity breaks.

Omni is synchronous for small responses, so there is no long-running operation to
poll unless a clip exceeds the inline size limit and comes back as a hosted URI.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path

from .backend import Clip, GenerationError
from .config import Config
from .shotlist import ShotPrompt
from .state import Store


@dataclass
class ChainState:
    """Carries the previous interaction id so shots stay in one conversation."""

    interaction_id: str | None = None


def build_request(cfg: Config, shot: ShotPrompt, chain: ChainState) -> dict:
    """Assemble the Interactions API arguments. Pure — does not call the API."""
    prompt = shot.prompt
    if shot.negative_prompt:
        # Omni has no negative_prompt field; fold it into the instruction.
        prompt = f"{prompt}\n\nDo not include: {shot.negative_prompt}."

    request: dict = {
        "model": cfg.model,
        "input": prompt,
        "response_format": {"type": "video", "aspect_ratio": cfg.aspect_ratio},
        "generation_config": {"video_config": {"task": "text_to_video"}},
    }

    if cfg.chain_shots and chain.interaction_id:
        request["previous_interaction_id"] = chain.interaction_id
        # A chained turn continues an existing scene rather than starting one.
        request["generation_config"]["video_config"]["task"] = "edit"
        request["input"] = (
            "Continue the same continuous handheld take from the previous clip. "
            "Same location, same light, same subject, same camera and lens. "
            "Do not restart the scene or cut to a new place.\n\n"
            f"What happens next: {prompt}"
        )
    return request


def _write_video(interaction, dest: Path, client, poll_interval_s: int) -> None:
    """Persist the video from an interaction response, inline or by hosted URI."""
    output = getattr(interaction, "output_video", None)
    if output is None:
        raise GenerationError("Response contained no video output")

    data = getattr(output, "data", None)
    if data:
        payload = base64.b64decode(data) if isinstance(data, str) else data
        dest.write_bytes(payload)
        return

    # Clips over the inline size limit arrive as a Google-hosted file that has to
    # reach ACTIVE before it can be downloaded.
    uri = getattr(output, "uri", None) or getattr(output, "file_uri", None)
    if not uri:
        raise GenerationError("Response had neither inline video data nor a URI")

    for _ in range(60):
        file = client.files.get(name=uri)
        state = str(getattr(file, "state", "")).upper()
        if "ACTIVE" in state:
            client.files.download(file=file)
            file.save(str(dest))
            return
        if "FAILED" in state:
            raise GenerationError(f"Hosted file failed to process: {uri}")
        time.sleep(poll_interval_s)
    raise GenerationError(f"Hosted file never became ACTIVE: {uri}")


def generate_clip(
    cfg: Config, store: Store, shot: ShotPrompt, dest: Path,
    episode_id: int | None, chain: ChainState,
) -> Clip:
    """Generate one clip, extending the interaction chain. Records spend."""
    from google import genai

    client = genai.Client(api_key=cfg.api_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    chained = bool(cfg.chain_shots and chain.interaction_id)
    last_error: Exception | None = None

    for attempt in range(1, cfg.max_retries + 1):
        try:
            interaction = client.interactions.create(**build_request(cfg, shot, chain))
            _write_video(interaction, dest, client, cfg.poll_interval_s)

            if not dest.is_file() or dest.stat().st_size == 0:
                raise GenerationError(f"Downloaded clip is empty: {dest}")

            # Only advance the chain on success, so a retry never builds on a
            # turn that produced nothing usable.
            new_id = getattr(interaction, "id", None)
            if new_id:
                chain.interaction_id = new_id

            usd = cfg.usd_per_second * shot.seconds
            if chained:
                usd += cfg.chained_input_usd_per_shot
            store.record_spend(
                usd=usd, seconds=float(shot.seconds), model=cfg.model,
                episode_id=episode_id,
                note=f"shot {shot.index}{' (chained)' if chained else ''}",
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
