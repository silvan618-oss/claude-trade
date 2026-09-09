#!/usr/bin/env python3
"""Put photos downloaded from Google Flow (or anywhere) into raw/<id>.png for snapify.py.

  python import_raw.py 03-delilah ~/Downloads/Flow_2026-09-09.png     # one file -> one snap
  python import_raw.py ~/Downloads/Flow_*.png                          # 5 files, oldest first,
                                                                       # assigned to the 5 snaps in order
  python import_raw.py --list                                          # show which snaps still lack a photo

Files are converted to PNG, EXIF-rotated, and 2K/4K downloads are kept at full size (snapify crops
to 9:16 and scales to the output size). An existing raw/<id>.png is moved to raw/<id>-old<N>.png.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
EXTS = {".png", ".jpg", ".jpeg", ".webp", ".heic"}


def snap_ids() -> list[str]:
    return [s["id"] for s in json.loads((HERE / "snaps.json").read_text(encoding="utf-8"))["snaps"]]


def place(src: Path, snap_id: str) -> Path:
    RAW.mkdir(exist_ok=True)
    dst = RAW / f"{snap_id}.png"
    if dst.exists():
        n = 1
        while (RAW / f"{snap_id}-old{n}.png").exists():
            n += 1
        dst.rename(RAW / f"{snap_id}-old{n}.png")
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    im.save(dst, "PNG")
    print(f"{src.name}  ->  raw/{dst.name}  ({im.width}x{im.height})")
    return dst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("args", nargs="*", help="[<snap id>] <file> ... ")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    ids = snap_ids()
    if a.list or not a.args:
        for i in ids:
            print(f"{'ok ' if (RAW / f'{i}.png').exists() else '-- '}{i}")
        return 0
    if a.args[0] in ids:
        if len(a.args) != 2:
            sys.exit("usage: import_raw.py <snap id> <file>")
        place(Path(a.args[1]).expanduser(), a.args[0])
        return 0
    files = [Path(f).expanduser() for f in a.args]
    bad = [f for f in files if f.suffix.lower() not in EXTS or not f.exists()]
    if bad:
        sys.exit("not an image file: " + ", ".join(map(str, bad)))
    files.sort(key=lambda f: f.stat().st_mtime)  # Flow downloads in prompt order -> snap order
    if len(files) != len(ids):
        sys.exit(f"got {len(files)} files for {len(ids)} snaps; assign single files with: import_raw.py <id> <file>")
    for f, i in zip(files, ids):
        place(f, i)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
