#!/usr/bin/env python3
"""Play the finished snaps back the way Snapchat does and write it as a video.

Snapchat playback has no transitions: a snap appears instantly (hard cut), stays for its
duration, then the next one replaces it. The frame is the plain 9:16 snap, no UI chrome —
exactly what the reference screenshots show. Optional extras (all off by default, toggled in
snaps.json -> "animation" or on the command line):

  story_ui   thin white progress segments at the top (one per snap) that fill up while the
             snap is showing, like a Snapchat story
  transition "cut" (default, real Snapchat) or "fade" with a very short cross-dissolve
  ken_burns  slow 3 % push-in per snap (TikTok-style edit), 0 = off

Usage:
  python animate.py                      # out/<id>.jpg ... -> out/story.mp4
  python animate.py --duration 2 --story-ui
  python animate.py --durations 3,2,2,2.5,4
Outputs are also written as a self-contained out/story.html (tap to advance / hold to pause).
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw

from snapify import cover_crop

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def load_frames(cfg: dict, out_dir: Path) -> list[tuple[dict, Image.Image]]:
    """Load out/<id>.jpg for every snap, normalised to the configured (even-sized) frame."""
    W, H = cfg["size"]
    size = (W - W % 2, H - H % 2)  # libx264 with yuv420p needs even dimensions
    frames = []
    for snap in cfg["snaps"]:
        p = out_dir / f"{snap['id']}.jpg"
        if not p.exists():
            print(f"missing {p} (run snapify.py first)", file=sys.stderr)
            continue
        im = cover_crop(Image.open(p).convert("RGB"), size)
        frames.append((snap, im))
    if not frames:
        sys.exit("no snaps to animate")
    return frames


def story_bar(im: Image.Image, idx: int, n: int, progress: float) -> Image.Image:
    """Snapchat story progress segments along the top edge."""
    W, H = im.size
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    margin, gap, y, h = round(0.02 * W), round(0.006 * W), round(0.012 * W), max(2, round(0.004 * W))
    seg = (W - 2 * margin - gap * (n - 1)) / n
    for i in range(n):
        x0 = margin + i * (seg + gap)
        d.rectangle((x0, y, x0 + seg, y + h), fill=(255, 255, 255, 90))
        fill = 1.0 if i < idx else progress if i == idx else 0.0
        if fill > 0:
            d.rectangle((x0, y, x0 + seg * fill, y + h), fill=(255, 255, 255, 235))
    return Image.alpha_composite(im.convert("RGBA"), over).convert("RGB")


def push_in(im: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return im
    W, H = im.size
    s = 1 + amount
    x = (W * s - W) / 2
    y = (H * s - H) / 2
    return im.resize((round(W * s), round(H * s)), Image.BILINEAR).crop((round(x), round(y), round(x) + W, round(y) + H))


def render(cfg: dict, frames: list, out_mp4: Path, durations: list[float], transition: str,
           story_ui: bool, ken_burns: float, fps: int) -> None:
    W, H = frames[0][1].size
    fade_frames = round(0.12 * fps) if transition == "fade" else 0
    writer = imageio.get_writer(str(out_mp4), fps=fps, codec="libx264", quality=8,
                                pixelformat="yuv420p", macro_block_size=1)
    prev_last = None
    for idx, (snap, im) in enumerate(frames):
        n_frames = max(1, round(durations[idx] * fps))
        last = None
        for f in range(n_frames):
            t = f / max(1, n_frames - 1)
            frame = push_in(im, ken_burns * t)
            if story_ui:
                frame = story_bar(frame, idx, len(frames), t)
            arr = np.asarray(frame)
            if prev_last is not None and f < fade_frames:  # short cross-dissolve from the previous snap
                a = (f + 1) / (fade_frames + 1)
                arr = (prev_last * (1 - a) + arr * a).astype(np.uint8)
            writer.append_data(arr)
            last = np.asarray(frame).astype(np.float32)
        prev_last = last
    writer.close()


HTML = """<!doctype html><meta charset=utf-8><title>snaps</title>
<style>html,body{margin:0;height:100%%;background:#000;display:flex;align-items:center;justify-content:center;font-family:Helvetica,Arial,sans-serif}
#s{position:relative;height:100vh;aspect-ratio:9/16;max-width:100vw;background:#000;overflow:hidden;user-select:none;-webkit-user-select:none}
#s img{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover;display:none}#s img.on{display:block}
#bar{position:absolute;top:1.2%%;left:2%%;right:2%%;display:%s;gap:0.6%%}#bar i{flex:1;height:3px;background:rgba(255,255,255,.35);border-radius:2px;overflow:hidden}
#bar i b{display:block;height:100%%;width:0;background:#fff}</style>
<div id=s>%s<div id=bar>%s</div></div>
<script>
const D=%s,imgs=[...document.querySelectorAll('#s img')],segs=[...document.querySelectorAll('#bar b')];let i=0,t0=0,el=0,paused=false,raf;
function show(k){i=(k+imgs.length)%%imgs.length;imgs.forEach((im,j)=>im.classList.toggle('on',j===i));segs.forEach((b,j)=>b.style.width=j<i?'100%%':'0');el=0;t0=performance.now();}
function loop(now){if(!paused){el+=now-t0;}t0=now;const p=Math.min(1,el/(D[i]*1000));if(segs[i])segs[i].style.width=(p*100)+'%%';if(p>=1)show(i+1);raf=requestAnimationFrame(loop);}
const s=document.getElementById('s');let down=0;
s.addEventListener('pointerdown',e=>{down=performance.now();paused=true;});
s.addEventListener('pointerup',e=>{paused=false;if(performance.now()-down<250){const r=s.getBoundingClientRect();show(e.clientX-r.left<r.width*0.3?i-1:i+1);}});
show(0);raf=requestAnimationFrame(loop);
</script>"""


def write_html(frames: list, durations: list[float], story_ui: bool, out_html: Path) -> None:
    imgs, segs = [], []
    for snap, im in frames:
        p = OUT / f"{snap['id']}.jpg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        imgs.append(f'<img src="data:image/jpeg;base64,{b64}" alt="{snap["id"]}">')
        segs.append("<i><b></b></i>")
    out_html.write_text(HTML % ("flex" if story_ui else "none", "".join(imgs), "".join(segs), json.dumps(durations)),
                        encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=HERE / "snaps.json")
    ap.add_argument("--out", type=Path, default=OUT / "story.mp4")
    ap.add_argument("--duration", type=float, default=None, help="seconds per snap (default from snaps.json)")
    ap.add_argument("--durations", default=None, help="comma-separated seconds per snap")
    ap.add_argument("--transition", choices=["cut", "fade"], default=None)
    ap.add_argument("--story-ui", action="store_true", help="Snapchat story progress segments at the top")
    ap.add_argument("--ken-burns", type=float, default=None, help="push-in amount per snap, e.g. 0.03 (default 0)")
    ap.add_argument("--fps", type=int, default=None)
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    anim = cfg.get("animation", {})
    frames = load_frames(cfg, OUT)
    n = len(frames)
    if args.durations:
        durations = [float(x) for x in args.durations.split(",")]
        durations = (durations + [durations[-1]] * n)[:n]
    else:
        d = args.duration if args.duration is not None else float(anim.get("duration", 2.5))
        durations = [float(s.get("duration", d)) for s, _ in frames]
    transition = args.transition or anim.get("transition", "cut")
    story_ui = args.story_ui or bool(anim.get("story_ui", False))
    ken_burns = args.ken_burns if args.ken_burns is not None else float(anim.get("ken_burns", 0))
    fps = args.fps or int(cfg.get("fps", 30))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(cfg, frames, args.out, durations, transition, story_ui, ken_burns, fps)
    html = args.out.with_suffix(".html")
    write_html(frames, durations, story_ui, html)
    print(f"wrote {args.out} ({sum(durations):.1f}s, {n} snaps, {transition}, fps {fps}) and {html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
