#!/usr/bin/env python3
"""Turn a generated photo into a Snapchat-style snap that matches the reference look.

Two stages, in this order (the same order the real app produces the image):
  1. "look"    – 2015-iPhone degradation of the photo (softness, noise, JPEG, black lift)
  2. "caption" – the crisp Snapchat caption bar (black, ~62 % opaque, white Helvetica text,
                 centred, word-wrapped) composited on top at the snap's caption_y

All geometry is relative to the frame width so it is identical at every resolution.
The relative numbers were measured on the reference snaps (1200x2133):
  bar height 106 px, line pitch 59 px, font ~50 px, first baseline 71 px below bar top.

Usage:
  python snapify.py                 # all snaps in snaps.json  (raw/<id>.*  ->  out/<id>.jpg)
  python snapify.py 02-hard-at-work # one snap
  python snapify.py --calibrate     # render the caption bars on neutral backgrounds and
                                    # compare their pixel geometry with the references
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent


def load_config(path: Path | None = None) -> dict:
    return json.loads((path or HERE / "snaps.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- photo look

def cover_crop(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale + centre-crop to exactly `size` (like the phone screen showing a 9:16 photo)."""
    W, H = size
    s = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def apply_look(im: Image.Image, look: dict, seed: int = 0) -> Image.Image:
    """2015 smartphone camera look: soft, noisy, compressed, slightly lifted blacks."""
    W, H = im.size
    rng = np.random.default_rng(seed)

    # 1. resolution loss: downscale and back up (old sensor + heavy in-camera NR)
    soft = float(look.get("softness", 1.0))
    if soft < 1.0:
        im = im.resize((max(1, round(W * soft)), max(1, round(H * soft))), Image.BILINEAR)
        im = im.resize((W, H), Image.BICUBIC)
    # 2. lens softness
    if look.get("blur", 0) > 0:
        im = im.filter(ImageFilter.GaussianBlur(float(look["blur"])))
    # 3. colour: slightly desaturated, blacks lifted (cheap sensor, no true black)
    if look.get("saturation", 1.0) != 1.0:
        im = ImageEnhance.Color(im).enhance(float(look["saturation"]))
    arr = np.asarray(im).astype(np.float32)
    lift = float(look.get("black_lift", 0))
    if lift:
        arr = lift + arr * (255.0 - lift) / 255.0
    # 4. sensor noise: luma noise on all channels + weaker independent chroma noise
    nl = float(look.get("noise_luma", 0))
    nc = float(look.get("noise_chroma", 0))
    if nl or nc:
        luma = rng.normal(0, nl, (H, W, 1)).astype(np.float32)
        chroma = rng.normal(0, nc, (H, W, 3)).astype(np.float32)
        arr = arr + luma + chroma
    # 5. mild vignette (small phone lens)
    v = float(look.get("vignette", 0))
    if v:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        arr = arr * (1.0 - v * np.clip(r - 0.5, 0, None) ** 2 / 0.6)[..., None]
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # 6. JPEG compression artefacts (baked in, then the caption goes on top uncompressed)
    q = int(look.get("jpeg_quality", 0))
    if q:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, subsampling=2)
        im = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return im


# --------------------------------------------------------------------------- caption bar

def _font(cfg: dict, W: int) -> ImageFont.FreeTypeFont:
    path = HERE / cfg["font"]
    return ImageFont.truetype(str(path), round(cfg["font_size"] * W))


def wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Greedy word wrap, the way UILabel wraps: as many words per line as fit."""
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and font.getlength(trial) > max_width:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def draw_tracked(d: ImageDraw.ImageDraw, line: str, cx: float, baseline: float,
                 font: ImageFont.FreeTypeFont, color: tuple, tracking: float) -> None:
    """Draw `line` centred on cx with its baseline at `baseline` and extra letter spacing.

    Helvetica Neue (what the phone drew) runs ~2 % wider than the Helvetica clone we ship,
    so a tiny positive tracking reproduces the reference text width exactly. Glyphs are
    placed via getlength() of the prefix, which keeps the font's own kerning intact.
    """
    total = font.getlength(line) + tracking * (len(line) - 1)
    x0 = cx - total / 2
    if not tracking:
        d.text((x0, baseline), line, font=font, fill=color, anchor="ls")
        return
    for i, ch in enumerate(line):
        d.text((x0 + font.getlength(line[:i]) + i * tracking, baseline), ch, font=font, fill=color, anchor="ls")


def caption_geometry(cfg: dict, W: int, H: int, caption_y: float, n_lines: int) -> tuple[int, int]:
    """Return (bar_top, bar_bottom) in pixels for a bar whose centre sits at caption_y * H."""
    bar_h = round(cfg["bar_height"] * W + (n_lines - 1) * cfg["line_pitch"] * W)
    top = round(caption_y * H - bar_h / 2)
    return top, top + bar_h


def draw_caption(im: Image.Image, text: str, caption_y: float, cfg: dict) -> Image.Image:
    """Composite the Snapchat caption bar (RGBA overlay) onto the photo."""
    W, H = im.size
    font = _font(cfg, W)
    lines = wrap_lines(text, font, W - 2 * cfg["side_padding"] * W)
    top, bottom = caption_geometry(cfg, W, H, caption_y, len(lines))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    # PIL rectangles include both end pixels, hence bottom - 1 for an exact bar height
    d.rectangle((0, top, W, bottom - 1), fill=(0, 0, 0, round(255 * cfg["bar_alpha"])))
    baseline = top + cfg["baseline"] * W
    pitch = cfg["line_pitch"] * W
    color = tuple(cfg.get("text_color", (255, 255, 255))) + (255,)
    tracking = cfg.get("tracking", 0) * W
    for i, line in enumerate(lines):
        draw_tracked(d, line, W / 2, baseline + i * pitch, font, color, tracking)
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


# --------------------------------------------------------------------------- pipeline

def find_raw(snap_id: str) -> Path | None:
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = HERE / "raw" / f"{snap_id}.{ext}"
        if p.exists():
            return p
    return None


def build_snap(snap: dict, cfg: dict, seed: int, out_dir: Path, src: Path | None = None) -> Path:
    src = src or find_raw(snap["id"])
    if src is None:
        raise FileNotFoundError(f"no raw photo for {snap['id']} in {HERE / 'raw'} (run generate.py first)")
    size = tuple(cfg["size"])
    im = Image.open(src).convert("RGB")
    im = cover_crop(im, size)
    im = apply_look(im, cfg["look"], seed=seed)
    im = draw_caption(im, snap["caption"], snap["caption_y"], cfg["caption"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{snap['id']}.jpg"
    im.save(out, "JPEG", quality=92, subsampling=0)  # screenshot-quality final save
    return out


# --------------------------------------------------------------------------- calibration

def measure_bar(im: Image.Image, approx_center: float) -> dict:
    """Measure bar top/bottom, text line rows and text column extent around approx_center."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    lum = a.mean(axis=2)
    H, W = lum.shape
    edge = np.concatenate([lum[:, : W // 40], lum[:, -W // 40 :]], axis=1).mean(axis=1)
    c = int(approx_center * H)
    best = None
    for t in range(max(c - int(0.12 * H), 40), c):
        for h in range(int(0.08 * W), int(0.16 * W)):
            b = t + h
            if b > H - 40:
                continue
            inside = edge[t + 2 : b - 2].mean()
            out = (edge[t - 40 : t - 2].mean() + edge[b + 2 : b + 40].mean()) / 2
            step = (edge[t - 3 : t].mean() - edge[t : t + 3].mean()) + (edge[b : b + 3].mean() - edge[b - 3 : b].mean())
            score = (out - inside) + step
            if best is None or score > best[0]:
                best = (score, t, b)
    _, t, b = best
    bar = a[t:b]
    white = bar.min(axis=2) > 190
    rows = np.where(white.sum(axis=1) > 2)[0]
    cols = np.where(white.sum(axis=0) > 0)[0]
    lines, start, prev = [], rows[0], rows[0]
    for r in rows[1:]:
        if r - prev > 6:
            lines.append((int(start), int(prev)))
            start = r
        prev = r
    lines.append((int(start), int(prev)))
    return {"top": t, "bottom": b, "height": b - t, "lines": lines,
            "text_x": (int(cols.min()), int(cols.max())), "width": W, "height_px": H}


def calibrate(cfg: dict) -> None:
    """Render every caption on a flat grey 1200x2133 frame and compare with the reference."""
    rows = []
    for snap in cfg["snaps"]:
        ref = Image.open(HERE / snap["reference"]).convert("RGB")
        W, H = ref.size
        test = Image.new("RGB", (W, H), (120, 120, 120))
        test = draw_caption(test, snap["caption"], snap["caption_y"], cfg["caption"])
        m_ref = measure_bar(ref, snap["caption_y"])
        m_new = measure_bar(test, snap["caption_y"])
        rows.append((snap["id"], m_ref, m_new))
        (HERE / "out").mkdir(exist_ok=True)
        # side-by-side strip: reference bar above, our bar below, for eyeballing
        strip = Image.new("RGB", (W, 2 * (m_ref["height"] + 80)), (120, 120, 120))
        strip.paste(ref.crop((0, m_ref["top"] - 40, W, m_ref["bottom"] + 40)), (0, 0))
        strip.paste(test.crop((0, m_new["top"] - 40, W, m_new["bottom"] + 40)), (0, m_ref["height"] + 80))
        strip.save(HERE / "out" / f"calib-{snap['id']}.png")
    print(f"{'snap':16} {'bar h ref/new':>14} {'line1 rows ref':>16} {'line1 rows new':>16} {'text x ref':>12} {'text x new':>12}")
    for sid, r, n in rows:
        rel = lambda m, key: tuple(v - m["top"] for v in m["lines"][0])
        print(f"{sid:16} {r['height']:>6}/{n['height']:<7} {str(rel(r, 0)):>16} {str(rel(n, 0)):>16} {str(r['text_x']):>12} {str(n['text_x']):>12}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="snap ids to build (default: all)")
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--src", type=Path, default=None, help="use this photo instead of raw/<id>.*")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--calibrate", action="store_true", help="compare caption geometry with references")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.calibrate:
        calibrate(cfg)
        return 0
    snaps = [s for s in cfg["snaps"] if not args.ids or s["id"] in args.ids]
    if not snaps:
        print("no matching snaps", file=sys.stderr)
        return 1
    for i, snap in enumerate(snaps):
        out = build_snap(snap, cfg, seed=i + 1, out_dir=args.out, src=args.src)
        print("wrote", out.relative_to(HERE.parent) if out.is_relative_to(HERE.parent) else out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
