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
    starts_new_chain: bool = False


def chain_starts(shot_count: int, max_chain_length: int) -> set[int]:
    """Shot indices that begin a fresh continuity chain.

    Continuity degrades with every link, so a minute-long episode is broken into
    bounded runs rather than one chain of seven. The breaks double as scene cuts,
    which a 60-second video needs anyway — an unbroken single take that long
    reads as monotonous.
    """
    if max_chain_length < 1:
        return {1}
    return {i for i in range(1, shot_count + 1) if (i - 1) % max_chain_length == 0}


def _continuity_anchor(concept: Concept) -> str:
    """A short, stable description of the world, repeated in every shot."""
    opening = concept.shots[0]
    return (
        f"Continuous single location established at the start: {opening.action}. "
        f"Same time of day, same weather, same light throughout."
    )


def build_shot_prompt(
    concept: Concept, shot_index: int, cfg: Config, *, new_chain: bool = False
) -> ShotPrompt:
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

    if shot_index > 1 and not new_chain:
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
        starts_new_chain=new_chain,
    )


def build_shotlist(concept: Concept, cfg: Config) -> list[ShotPrompt]:
    starts = chain_starts(len(concept.shots), cfg.max_chain_length)
    return [
        build_shot_prompt(concept, i + 1, cfg, new_chain=(i + 1) in starts)
        for i in range(len(concept.shots))
    ]
