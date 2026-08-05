"""Concept -> Veo prompts.

Each shot is generated independently, so continuity has to be carried in the
prompt text itself: the same location and light description is repeated in every
shot, and each shot after the first states what it continues from.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .ideas import Concept
from .style import IMPERFECTIONS, NEGATIVE_PROMPT, shot_style_suffix


@dataclass
class ShotPrompt:
    index: int
    prompt: str
    negative_prompt: str
    seconds: int


def _continuity_anchor(concept: Concept) -> str:
    """A short, stable description of the world, repeated in every shot."""
    opening = concept.shots[0]
    return (
        f"Continuous single location established at the start: {opening.action}. "
        f"Same time of day, same weather, same light throughout."
    )


def build_shot_prompt(concept: Concept, shot_index: int, cfg: Config) -> ShotPrompt:
    """Compose the full prompt for one shot. Pure — no network."""
    if not 1 <= shot_index <= len(concept.shots):
        raise IndexError(f"Shot {shot_index} out of range for {len(concept.shots)} shots")

    shot = concept.shots[shot_index - 1]
    parts: list[str] = []

    if shot_index == 1 and concept.hook_visual:
        # Frame 1 carries the whole video's retention; state it before anything else.
        parts.append(f"Opens immediately on: {concept.hook_visual}.")

    parts.append(shot.action.rstrip("."))

    if shot.camera:
        parts.append(f"Camera: {shot.camera}")

    if shot_index > 1:
        previous = concept.shots[shot_index - 2]
        parts.append(
            f"Continues directly from the previous moment: {previous.beat or previous.action}"
        )

    parts.append(_continuity_anchor(concept))

    if cfg.keep_ambient_audio and shot.ambient:
        parts.append(f"Ambient sound only, no voices: {shot.ambient}")
    else:
        parts.append("Ambient sound only, no voices")

    imperfection = IMPERFECTIONS[(shot_index - 1) % len(IMPERFECTIONS)]
    parts.append(shot_style_suffix(cfg.style_preset, imperfection))

    return ShotPrompt(
        index=shot_index,
        prompt=". ".join(p.strip().rstrip(".") for p in parts if p.strip()) + ".",
        negative_prompt=NEGATIVE_PROMPT,
        seconds=cfg.seconds_per_shot,
    )


def build_shotlist(concept: Concept, cfg: Config) -> list[ShotPrompt]:
    return [
        build_shot_prompt(concept, i + 1, cfg) for i in range(len(concept.shots))
    ]
