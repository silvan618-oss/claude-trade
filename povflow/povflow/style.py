"""The look: authentic first-person phone footage.

Everything here exists to fight Veo's default instinct, which is to produce
polished cinematic footage on a stabilised rig. Handheld phone POV needs the
opposite, and it needs to be identical across every clip of an episode or the
cuts read as different cameras.
"""

from __future__ import annotations

# Injected into every shot prompt. Order matters: camera identity first, because
# the leading tokens carry the most weight in the generated look.
POV_STYLE_DNA = (
    "filmed on a modern smartphone held in one hand, first-person POV, "
    "camera at eye level roughly at arm's length, "
    "natural handheld shake and small involuntary corrections, "
    "slight motion blur on fast pans, rolling-shutter wobble, "
    "autofocus hunting for a moment before it locks, "
    "unpolished amateur phone footage, natural available light, "
    "slightly blown-out highlights, no colour grading, "
    "vertical 9:16 framing"
)

# Speech is excluded on purpose: the creator records the voice-over, and any
# generated dialogue would fight it. Ambient sound is kept as a bed.
NEGATIVE_PROMPT = (
    "dialogue, speech, talking, narration, voiceover, singing, "
    "subtitles, captions, text overlay, watermark, logo, "
    "cinematic colour grading, teal and orange, film grain, anamorphic lens flare, "
    "tripod, gimbal, stabilised camera, dolly, crane shot, drone shot, "
    "professional studio lighting, shallow depth of field bokeh portrait, "
    "letterboxing, black bars, split screen, collage"
)

# Presets shift the mood without touching the camera identity above.
STYLE_PRESETS: dict[str, str] = {
    "fantasy": (
        "a real, physically present fantasy world, practical-effects realism "
        "rather than glossy CGI, weight and scale in every creature, "
        "grounded and slightly frightening"
    ),
    "wildlife": (
        "a real wildlife encounter documented by an amateur, "
        "the animal behaves like an actual animal and not a character, "
        "the moment feels lucky and unrepeatable"
    ),
    "urban": (
        "a real street-level moment in a recognisable modern city, "
        "bystanders and traffic present, nothing staged"
    ),
    "survival": (
        "a real remote wilderness location, harsh weather, "
        "genuine physical difficulty, no comfort"
    ),
}

# Small, deliberate imperfections. One is picked per shot so an episode does not
# look like the same frame regenerated five times.
IMPERFECTIONS: tuple[str, ...] = (
    "a thumb briefly clipping the corner of the frame",
    "the camera dipping toward the ground for a moment before coming back up",
    "a quick over-correction after a too-fast pan",
    "a breath-driven bounce in the framing",
    "the horizon sitting a few degrees off level",
    "a short stumble in the operator's footing",
)


def shot_style_suffix(preset: str, imperfection: str | None = None) -> str:
    """Build the style block appended to a single shot's action description."""
    parts = [POV_STYLE_DNA]
    world = STYLE_PRESETS.get(preset)
    if world:
        parts.append(world)
    if imperfection:
        parts.append(imperfection)
    return ", ".join(parts)
