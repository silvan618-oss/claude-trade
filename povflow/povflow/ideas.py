"""Episode concepts.

An episode is one finished short: a hook, a handful of shots, and a voice-over
script keyed to those shots. Concepts come back as JSON so the rest of the
pipeline never has to parse prose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .state import Store, idea_fingerprint


class IdeaError(Exception):
    """Raised when the model returns something unusable."""


@dataclass
class Shot:
    index: int
    beat: str
    action: str
    camera: str
    ambient: str


@dataclass
class Concept:
    title: str
    logline: str
    hook_visual: str
    shots: list[Shot]
    voiceover: list[str]
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        return idea_fingerprint(self.title, self.logline)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "logline": self.logline,
            "hook_visual": self.hook_visual,
            "shots": [vars(s) for s in self.shots],
            "voiceover": self.voiceover,
            "caption": self.caption,
            "hashtags": self.hashtags,
        }


IDEA_SYSTEM_PROMPT = """\
You write concepts for vertical short-form videos that look like genuine
first-person phone footage. The creator records a voice-over on top afterwards,
so nobody speaks on camera and no dialogue is ever generated.

Hard rules:
- The very first frame must already show something a viewer cannot scroll past.
  Never open on an establishing shot, a title card, or a slow reveal.
- Every shot is a single continuous handheld take from the creator's own eyes.
- Shots must connect physically. Shot 2 continues from where shot 1 ended, in
  the same location, same light, same weather. This is one walk, not a montage.
- Describe only what a camera can see and hear. No inner thoughts, no backstory
  that is not visible, no on-screen text.
- The voice-over line for a shot is what the creator says while that shot plays.
  Written to be read aloud in {seconds} seconds: roughly {words} words, spoken
  language, no stage directions.
- The last shot ends on an unresolved beat that makes a rewatch or a part 2
  feel necessary.

Answer with a JSON array only. No prose, no markdown fences.
Each element:
{{
  "title": "short internal name",
  "logline": "one sentence, what happens",
  "hook_visual": "exactly what is visible in frame 1",
  "shots": [
    {{
      "beat": "what this shot accomplishes",
      "action": "what physically happens, camera-visible only",
      "camera": "how the phone moves during the take",
      "ambient": "diegetic sound present, no speech"
    }}
  ],
  "voiceover": ["line for shot 1", "line for shot 2"],
  "caption": "platform caption",
  "hashtags": ["#tag"]
}}
"""


def build_idea_prompt(cfg: Config, n: int, avoid_titles: list[str]) -> tuple[str, str]:
    """Return (system_prompt, user_prompt). Pure — no network."""
    words_per_shot = max(8, int(cfg.seconds_per_shot * 2.4))
    system = IDEA_SYSTEM_PROMPT.format(
        seconds=cfg.seconds_per_shot, words=words_per_shot
    )

    lines = [
        f"Niche: {cfg.niche}",
        f"World / style: {cfg.style_preset}",
        f"Audience: {cfg.audience}",
        f"Voice-over language: {cfg.language}",
        f"Produce {n} concept(s), each with exactly {cfg.shots_per_episode} shots "
        f"and exactly {cfg.shots_per_episode} voice-over lines.",
    ]
    if cfg.concept_brief:
        lines.append(f"Channel brief: {cfg.concept_brief}")
    if cfg.forbidden:
        lines.append("Never include: " + ", ".join(cfg.forbidden))
    if avoid_titles:
        lines.append(
            "Already produced, do not repeat these premises: "
            + "; ".join(avoid_titles[:40])
        )
    return system, "\n".join(lines)


def _extract_json_array(text: str) -> list[Any]:
    """Pull a JSON array out of a model response that may be wrapped in prose."""
    cleaned = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.MULTILINE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            raise IdeaError(f"No JSON array in model response: {text[:300]!r}") from None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise IdeaError(f"Malformed JSON from model: {exc}") from exc

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise IdeaError(f"Expected a JSON array, got {type(parsed).__name__}")
    return parsed


def parse_concepts(raw: str, shots_expected: int) -> list[Concept]:
    """Turn a model response into validated Concepts. Pure — no network."""
    concepts: list[Concept] = []
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        raw_shots = item.get("shots") or []
        if not isinstance(raw_shots, list) or not raw_shots:
            continue

        shots = [
            Shot(
                index=i + 1,
                beat=str(s.get("beat", "")).strip(),
                action=str(s.get("action", "")).strip(),
                camera=str(s.get("camera", "")).strip(),
                ambient=str(s.get("ambient", "")).strip(),
            )
            for i, s in enumerate(raw_shots)
            if isinstance(s, dict) and str(s.get("action", "")).strip()
        ]
        if not shots:
            continue

        # The model occasionally drifts off the requested count. Trim rather than
        # reject, so one sloppy element does not cost a whole generation round.
        shots = shots[:shots_expected]

        vo = [str(v).strip() for v in (item.get("voiceover") or []) if str(v).strip()]
        vo = vo[: len(shots)]
        vo += [""] * (len(shots) - len(vo))

        title = str(item.get("title", "")).strip()
        logline = str(item.get("logline", "")).strip()
        if not title or not logline:
            continue

        concepts.append(
            Concept(
                title=title,
                logline=logline,
                hook_visual=str(item.get("hook_visual", "")).strip(),
                shots=shots,
                voiceover=vo,
                caption=str(item.get("caption", "")).strip(),
                hashtags=[str(h).strip() for h in (item.get("hashtags") or [])],
            )
        )
    return concepts


def drop_duplicates(concepts: list[Concept], known: set[str]) -> list[Concept]:
    """Remove concepts matching history or each other. Pure — no network."""
    seen = set(known)
    unique: list[Concept] = []
    for concept in concepts:
        fp = concept.fingerprint
        if fp in seen:
            continue
        seen.add(fp)
        unique.append(concept)
    return unique


# Distinct placeholder premises. They must not collapse to one fingerprint, or a
# multi-episode dry run would preview a single episode.
_STUB_PREMISES: tuple[tuple[str, str, str], ...] = (
    ("forest", "a treeline at dusk", "something heavy moving between the trunks"),
    ("harbour", "an empty concrete pier", "a wake cutting toward the shore"),
    ("tunnel", "a flooded service tunnel", "reflections that do not match the walls"),
    ("ridge", "a bare mountain ridge in fog", "a silhouette standing where nothing should"),
    ("field", "a frozen field before sunrise", "tracks appearing in the frost ahead"),
)


def stub_concepts(cfg: Config, n: int) -> list[Concept]:
    """Deterministic offline concepts so `--dry-run` works without an API key."""
    out: list[Concept] = []
    for i in range(n):
        place, setting, event = _STUB_PREMISES[i % len(_STUB_PREMISES)]
        shots = [
            Shot(
                index=j + 1,
                beat=f"[DRY RUN] {place} beat {j + 1}",
                action=(
                    f"[DRY RUN] {setting}; {event}, closer than in the shot before"
                ),
                camera="handheld, pushing forward, one small correction",
                ambient="wind, footsteps on gravel, a distant low rumble",
            )
            for j in range(cfg.shots_per_episode)
        ]
        out.append(
            Concept(
                title=f"[DRY RUN] {place} encounter",
                logline=f"Offline placeholder set at {setting}: {event}.",
                hook_visual=f"[DRY RUN] {event}, already filling frame 1",
                shots=shots,
                voiceover=[
                    f"[DRY RUN] {place} voice-over line {j + 1}."
                    for j in range(len(shots))
                ],
                caption=f"[DRY RUN] {place} caption",
                hashtags=["#dryrun"],
            )
        )
    return out


def generate_concepts(cfg: Config, store: Store, n: int, *, dry_run: bool = False) -> list[Concept]:
    """Generate `n` de-duplicated concepts."""
    if dry_run:
        return drop_duplicates(stub_concepts(cfg, n), store.known_fingerprints())

    if not cfg.api_key:
        raise IdeaError(
            "GEMINI_API_KEY is not set. Put it in povflow/.env or run with --dry-run."
        )

    from google import genai  # imported lazily so --dry-run needs no dependency
    from google.genai import types

    client = genai.Client(api_key=cfg.api_key)
    known = store.known_fingerprints()
    avoid = store.recent_titles()
    collected: list[Concept] = []

    # Over-ask, then filter: de-duplication usually eats a couple of candidates.
    for attempt in range(3):
        system, user = build_idea_prompt(cfg, n + 2, avoid + [c.title for c in collected])
        response = client.models.generate_content(
            model=cfg.idea_model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=1.0 if attempt == 0 else 1.2,
                response_mime_type="application/json",
            ),
        )
        text = getattr(response, "text", "") or ""
        if not text.strip():
            continue

        fresh = drop_duplicates(
            parse_concepts(text, cfg.shots_per_episode),
            known | {c.fingerprint for c in collected},
        )
        collected.extend(fresh)
        if len(collected) >= n:
            break

    if not collected:
        raise IdeaError("Model returned no usable concepts after 3 attempts.")
    return collected[:n]
