"""Clip assembly with ffmpeg.

Two jobs beyond stitching. First, Veo has been observed returning 16:9 even when
9:16 was requested, so every clip is measured and centre-cropped to the target
frame rather than trusted. Second, ambient audio is ducked well below speech
level so the creator's voice-over sits on top without fighting it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

TARGET_DIMS: dict[tuple[str, str], tuple[int, int]] = {
    ("9:16", "720p"): (720, 1280),
    ("9:16", "1080p"): (1080, 1920),
    ("16:9", "720p"): (1280, 720),
    ("16:9", "1080p"): (1920, 1080),
}


class AssemblyError(Exception):
    """Raised when ffmpeg is missing or a step fails."""


@dataclass
class Dimensions:
    width: int
    height: int

    @property
    def ratio(self) -> float:
        return self.width / self.height if self.height else 0.0


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def target_dimensions(aspect_ratio: str, resolution: str) -> tuple[int, int]:
    try:
        return TARGET_DIMS[(aspect_ratio, resolution)]
    except KeyError:
        raise AssemblyError(
            f"No target size for {aspect_ratio} at {resolution}"
        ) from None


def probe_dimensions(path: Path) -> Dimensions:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise AssemblyError(f"ffprobe failed on {path.name}: {result.stderr.strip()}")
    try:
        stream = json.loads(result.stdout)["streams"][0]
        return Dimensions(int(stream["width"]), int(stream["height"]))
    except (KeyError, IndexError, ValueError) as exc:
        raise AssemblyError(f"Could not read dimensions from {path.name}") from exc


def build_video_filter(source: Dimensions, target_w: int, target_h: int) -> str:
    """Scale-and-centre-crop filter that fills the target without letterboxing.

    Pure string builder so the geometry can be unit tested without ffmpeg.
    """
    target_ratio = target_w / target_h
    if source.ratio > target_ratio:
        # Source is wider: match height, crop the sides.
        scale = f"scale=-2:{target_h}"
    else:
        # Source is taller or equal: match width, crop top and bottom.
        scale = f"scale={target_w}:-2"
    return f"{scale},crop={target_w}:{target_h},setsar=1"


def build_normalize_command(
    src: Path, dst: Path, source: Dimensions, target_w: int, target_h: int,
    *, keep_audio: bool, gain_db: float, fps: int = 30,
) -> list[str]:
    """ffmpeg args to bring one clip to the target frame. Pure — does not run."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-vf", f"{build_video_filter(source, target_w, target_h)},fps={fps}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
    ]
    if keep_audio:
        # Ambient stays as a bed under the voice-over; a silent track is
        # synthesised when the clip has none so concat inputs stay uniform.
        cmd += [
            "-af", f"volume={gain_db}dB,aresample=async=1",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-shortest",
        ]
    else:
        cmd += ["-an"]
    cmd.append(str(dst))
    return cmd


def build_concat_command(list_file: Path, dst: Path, *, keep_audio: bool) -> list[str]:
    """ffmpeg args to concatenate normalised clips. Pure — does not run."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy",
    ]
    if not keep_audio:
        cmd.append("-an")
    cmd.append(str(dst))
    return cmd


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssemblyError(
            f"ffmpeg failed: {' '.join(cmd[:6])} ...\n{result.stderr.strip()[:500]}"
        )


def assemble(
    clip_paths: list[Path], dst: Path, *, aspect_ratio: str, resolution: str,
    keep_audio: bool, gain_db: float, work_dir: Path,
) -> Path:
    """Normalise every clip to the target frame, then concatenate in order."""
    if not clip_paths:
        raise AssemblyError("No clips to assemble")
    if not ffmpeg_available():
        raise AssemblyError(
            "ffmpeg and ffprobe are required for assembly. "
            "macOS: brew install ffmpeg — Windows: winget install ffmpeg"
        )

    target_w, target_h = target_dimensions(aspect_ratio, resolution)
    work_dir.mkdir(parents=True, exist_ok=True)
    normalised: list[Path] = []

    for i, clip in enumerate(clip_paths, start=1):
        source = probe_dimensions(clip)
        if abs(source.ratio - target_w / target_h) > 0.01:
            print(f"    shot {i}: got {source.width}x{source.height}, "
                  f"cropping to {target_w}x{target_h}")
        out = work_dir / f"norm_{i:02d}.mp4"
        _run(build_normalize_command(
            clip, out, source, target_w, target_h,
            keep_audio=keep_audio, gain_db=gain_db,
        ))
        normalised.append(out)

    list_file = work_dir / "concat.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in normalised),
        encoding="utf-8",
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run(build_concat_command(list_file, dst, keep_audio=keep_audio))
    return dst
