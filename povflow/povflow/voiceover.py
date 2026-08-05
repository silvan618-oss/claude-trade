"""Voice-over deliverables.

The creator records against a finished silent cut, so the script has to be keyed
to real timecodes and has to warn when a line is too long to actually say in the
time its shot is on screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ideas import Concept

# Conversational delivery, roughly 150 words per minute.
WORDS_PER_SECOND = 2.5


@dataclass
class VoLine:
    shot: int
    start_s: float
    end_s: float
    text: str

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def spoken_estimate_s(self) -> float:
        return self.word_count / WORDS_PER_SECOND

    @property
    def is_too_long(self) -> bool:
        # 10% headroom before flagging; delivery speed varies.
        return self.spoken_estimate_s > self.duration_s * 1.1


def format_timecode(seconds: float, *, srt: bool = False) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    if srt:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
    return f"{minutes + hours * 60:02d}:{secs:02d}.{ms // 100}"


def build_vo_lines(concept: Concept, seconds_per_shot: int) -> list[VoLine]:
    """Key each voice-over line to its shot's position in the cut. Pure."""
    lines: list[VoLine] = []
    for i, shot in enumerate(concept.shots):
        text = concept.voiceover[i] if i < len(concept.voiceover) else ""
        lines.append(
            VoLine(
                shot=shot.index,
                start_s=i * seconds_per_shot,
                end_s=(i + 1) * seconds_per_shot,
                text=text.strip(),
            )
        )
    return lines


def render_script(concept: Concept, lines: list[VoLine]) -> str:
    """Human-readable recording script. Pure."""
    total = lines[-1].end_s if lines else 0
    out = [
        concept.title,
        "=" * len(concept.title),
        "",
        f"Logline: {concept.logline}",
        f"Length:  {format_timecode(total)} ({int(total)}s)",
        "",
        "Record against the silent cut. Timecodes are where each line starts.",
        "",
    ]
    for line in lines:
        flag = ""
        if line.is_too_long:
            flag = (f"   [TOO LONG: ~{line.spoken_estimate_s:.1f}s of speech in a "
                    f"{line.duration_s:.0f}s shot — cut words]")
        out += [
            f"[{format_timecode(line.start_s)}] Shot {line.shot}"
            f"  ({line.word_count} words){flag}",
            f"  {line.text or '(no line — let the ambient carry this shot)'}",
            "",
        ]
    if concept.caption:
        out += ["-" * 40, f"Caption: {concept.caption}"]
    if concept.hashtags:
        out.append("Hashtags: " + " ".join(concept.hashtags))
    return "\n".join(out) + "\n"


def render_srt(lines: list[VoLine]) -> str:
    """SRT for loading into an editor as a recording guide. Pure."""
    blocks = []
    for i, line in enumerate(lines, start=1):
        if not line.text:
            continue
        blocks.append(
            f"{i}\n"
            f"{format_timecode(line.start_s, srt=True)} --> "
            f"{format_timecode(line.end_s, srt=True)}\n"
            f"{line.text}\n"
        )
    return "\n".join(blocks)
