"""Schnitt und Export mit ffmpeg — der Teil, den sonst CapCut macht.

Ablauf:
  1. Jeden Clip auf dasselbe Format normalisieren (9:16, gleiche fps, gleicher
     Audio-Stream). Nur dann laesst sich verlustfrei aneinanderhaengen.
  2. Clips zusammenfuegen (concat-Demuxer, kein Neukodieren).
  3. Voiceover-Segmente an die Clipgrenzen legen und ueber den Originalton mischen.
  4. Optional Musik druntermischen und Untertitel einbrennen.

Alle Kommandos werden von reinen Funktionen gebaut (`*_args`), damit sie sich
ohne installiertes ffmpeg testen lassen.
"""

import json
import os
import subprocess

from tiktok.config import Config

# Der Originalton der Clips bleibt als Atmosphaere leise drunter.
AMBIENT_VOLUME = float(os.getenv("AMBIENT_VOLUME", "0.18"))
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.25"))


class AssemblyError(RuntimeError):
    pass


def run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssemblyError(f"{args[0]} fehlgeschlagen:\n{proc.stderr.strip()[-1500:]}")
    return proc.stdout


# ---------------------------------------------------------------- Analyse


def probe_duration(ffprobe: str, path: str) -> float:
    out = run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path]
    )
    try:
        return float(out.strip())
    except ValueError as exc:
        raise AssemblyError(f"Keine Dauer fuer {path} ermittelbar.") from exc


def has_audio(ffprobe: str, path: str) -> bool:
    out = run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "json", path]
    )
    return bool(json.loads(out or "{}").get("streams"))


# ---------------------------------------------------------------- Kommandos


def normalize_args(ffmpeg: str, src: str, dst: str, width: int, height: int, fps: int, silent: bool) -> list[str]:
    """Skaliert formatfuellend auf 9:16 und erzwingt einheitliche Streams."""
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},setsar=1"
    )
    args = [ffmpeg, "-y", "-i", src]
    if silent:
        # Ohne Tonspur wuerde der Concat-Demuxer spaeter aus dem Tritt geraten.
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest"]
    args += [
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", dst,
    ]
    return args


def concat_args(ffmpeg: str, list_path: str, dst: str) -> list[str]:
    return [
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", "-movflags", "+faststart", dst,
    ]


def write_concat_list(paths: list[str], list_path: str) -> str:
    with open(list_path, "w", encoding="utf-8") as fh:
        for path in paths:
            fh.write(f"file '{os.path.abspath(path)}'\n")
    return list_path


def mix_args(
    ffmpeg: str,
    video: str,
    narration: list[tuple[str, float]],
    music: str,
    dst: str,
    subtitles: str = "",
) -> list[str]:
    """Legt Voiceover-Segmente an ihre Startzeiten und mischt alles zusammen.

    `narration` ist eine Liste aus (Audiodatei, Startsekunde) — je ein Eintrag
    pro Clip, damit der Text synchron zum Bildwechsel einsetzt.
    """
    args = [ffmpeg, "-y", "-i", video]
    labels = []
    filters = []

    for i, (path, offset) in enumerate(narration, start=1):
        args += ["-i", path]
        delay_ms = int(round(offset * 1000))
        filters.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},apad[v{i}]")
        labels.append(f"[v{i}]")

    ambient_index = 0
    filters.insert(0, f"[{ambient_index}:a]volume={AMBIENT_VOLUME}[amb]")
    mix_inputs = ["[amb]"] + labels

    if music:
        music_index = len(narration) + 1
        args += ["-i", music]
        filters.append(f"[{music_index}:a]volume={MUSIC_VOLUME},apad[mus]")
        mix_inputs.append("[mus]")

    # normalize=0: sonst senkt amix jede Spur, je mehr Spuren dazukommen.
    filters.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:normalize=0[aout]"
    )

    video_map = "0:v"
    if subtitles:
        filters.append(f"[0:v]subtitles='{subtitles}'[vout]")
        video_map = "[vout]"

    args += [
        "-filter_complex", ";".join(filters),
        "-map", video_map, "-map", "[aout]",
        "-c:v", "libx264" if subtitles else "copy",
    ]
    if subtitles:
        args += ["-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", dst]
    return args


# ---------------------------------------------------------------- Untertitel


def _timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(beats: list[dict], durations: list[float]) -> str:
    """Ein Untertitelblock pro Clip — reicht fuer TikTok-Lesbarkeit."""
    lines = []
    start = 0.0
    for i, (beat, duration) in enumerate(zip(beats, durations), start=1):
        text = str(beat.get("voiceover", "")).strip()
        if text:
            lines.append(f"{i}\n{_timestamp(start)} --> {_timestamp(start + duration)}\n{text}\n")
        start += duration
    return "\n".join(lines)


# ---------------------------------------------------------------- Orchestrierung


def assemble(
    config: Config,
    job_dir: str,
    clip_paths: list[str],
    narration_paths: list[str],
    beats: list[dict],
    music: str = "",
    final_name: str = "final.mp4",
) -> str:
    """Baut aus Clips + Voiceover das fertige, postbare Video."""
    work = os.path.join(job_dir, "work")
    os.makedirs(work, exist_ok=True)

    normalized = []
    durations = []
    for i, clip in enumerate(clip_paths, start=1):
        dst = os.path.join(work, f"norm_{i:02d}.mp4")
        if not os.path.exists(dst):
            run(normalize_args(
                config.ffmpeg, clip, dst, config.width, config.height,
                config.target_fps, silent=not has_audio(config.ffprobe, clip),
            ))
        normalized.append(dst)
        durations.append(probe_duration(config.ffprobe, dst))

    silent_video = os.path.join(work, "joined.mp4")
    run(concat_args(config.ffmpeg, write_concat_list(normalized, os.path.join(work, "concat.txt")), silent_video))

    narration = []
    offset = 0.0
    for path, duration in zip(narration_paths, durations):
        if path and os.path.exists(path):
            narration.append((path, offset))
        offset += duration

    subtitles = ""
    if config.burn_subtitles:
        srt_path = os.path.join(work, "subs.srt")
        with open(srt_path, "w", encoding="utf-8") as fh:
            fh.write(build_srt(beats, durations))
        subtitles = srt_path

    final_path = os.path.join(job_dir, final_name)
    if not narration and not music and not subtitles:
        os.replace(silent_video, final_path)
        return final_path

    run(mix_args(config.ffmpeg, silent_video, narration, music, final_path, subtitles))
    return final_path
