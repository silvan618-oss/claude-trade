"""Orchestration: concept -> clips -> silent cut -> voice-over script."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .assemble import AssemblyError, assemble, ffmpeg_available
from .backend import BudgetExceeded, Clip, check_budget
from .config import Config
from .ideas import Concept, generate_concepts
from .shotlist import build_shotlist
from .state import Store


@dataclass
class EpisodeResult:
    slug: str
    directory: Path
    concept: Concept
    video_path: Path | None
    script_path: Path
    usd_spent: float
    dry_run: bool


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def produce_episode(
    cfg: Config, store: Store, concept: Concept, *, dry_run: bool = False,
    keep_intermediates: bool = False,
) -> EpisodeResult:
    """Produce one episode end to end."""
    from .voiceover import build_vo_lines, render_script, render_srt

    episode_id, slug = store.add_episode(
        concept.title, concept.logline, concept.to_dict()
    )
    directory = cfg.output_dir / f"{date.today().isoformat()}_{slug}"
    directory.mkdir(parents=True, exist_ok=True)

    shotlist = build_shotlist(concept, cfg)
    _write_json(directory / "concept.json", concept.to_dict())
    _write_json(
        directory / "shotlist.json",
        [{"index": s.index, "seconds": s.seconds, "prompt": s.prompt,
          "negative_prompt": s.negative_prompt} for s in shotlist],
    )

    # Voice-over deliverables do not depend on the video, so write them first:
    # a failed generation still leaves a usable script behind.
    vo_lines = build_vo_lines(concept, cfg.seconds_per_shot)
    script_path = directory / "voiceover.txt"
    script_path.write_text(render_script(concept, vo_lines), encoding="utf-8")
    (directory / "voiceover.srt").write_text(render_srt(vo_lines), encoding="utf-8")

    if dry_run:
        store.set_status(episode_id, "dry-run")
        return EpisodeResult(
            slug=slug, directory=directory, concept=concept, video_path=None,
            script_path=script_path, usd_spent=0.0, dry_run=True,
        )

    planned = cfg.usd_per_second * sum(s.seconds for s in shotlist)
    planned += cfg.chained_input_usd_per_shot * max(0, len(shotlist) - 1)
    check_budget(cfg, store, planned)

    shots_dir = directory / "shots"
    clips: list[Clip] = []
    try:
        if cfg.backend == "omni":
            from .omni import ChainState, generate_clip

            chain = ChainState()
            for shot in shotlist:
                linked = " (continuing previous shot)" if chain.interaction_id else ""
                print(f"  shot {shot.index}/{len(shotlist)} generating{linked} ...")
                clips.append(
                    generate_clip(
                        cfg, store, shot, shots_dir / f"shot_{shot.index:02d}.mp4",
                        episode_id, chain,
                    )
                )
        else:
            from .veo import generate_clip as generate_veo_clip

            for shot in shotlist:
                print(f"  shot {shot.index}/{len(shotlist)} generating ...")
                clips.append(
                    generate_veo_clip(
                        cfg, store, shot, shots_dir / f"shot_{shot.index:02d}.mp4",
                        episode_id,
                    )
                )
    except Exception:
        store.set_status(episode_id, "failed")
        spent = sum(c.usd for c in clips)
        print(f"  generation failed after {len(clips)} clip(s), ${spent:.2f} spent")
        raise

    spent = sum(c.usd for c in clips)
    video_path: Path | None = None
    work_dir = directory / "work"
    try:
        video_path = assemble(
            [c.path for c in clips], directory / "final_silent.mp4",
            aspect_ratio=cfg.aspect_ratio, resolution=cfg.resolution,
            keep_audio=cfg.keep_ambient_audio, gain_db=cfg.ambient_audio_gain_db,
            work_dir=work_dir,
        )
        store.set_status(episode_id, "done")
    except AssemblyError as exc:
        # The clips are paid for and on disk; assembly can be redone by hand.
        store.set_status(episode_id, "clips-only")
        print(f"  clips generated but assembly failed: {exc}")
    finally:
        if not keep_intermediates and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)

    return EpisodeResult(
        slug=slug, directory=directory, concept=concept, video_path=video_path,
        script_path=script_path, usd_spent=spent, dry_run=False,
    )


def run_batch(
    cfg: Config, store: Store, count: int, *, dry_run: bool = False,
    keep_intermediates: bool = False,
) -> list[EpisodeResult]:
    """Generate `count` concepts and produce each one."""
    if not dry_run and not ffmpeg_available():
        print("Warning: ffmpeg not found — clips will be generated but not stitched.\n")

    print(f"Generating {count} concept(s) for niche {cfg.niche!r} ...")
    concepts = generate_concepts(cfg, store, count, dry_run=dry_run)
    if len(concepts) < count:
        print(f"  only {len(concepts)} unique concept(s) after de-duplication")

    results: list[EpisodeResult] = []
    for i, concept in enumerate(concepts, start=1):
        print(f"\n[{i}/{len(concepts)}] {concept.title}")
        try:
            results.append(
                produce_episode(
                    cfg, store, concept, dry_run=dry_run,
                    keep_intermediates=keep_intermediates,
                )
            )
        except BudgetExceeded as exc:
            print(f"  stopped: {exc}")
            break
        except Exception as exc:  # noqa: BLE001 - one bad episode must not kill the batch
            print(f"  episode failed: {exc}")
            continue
    return results
