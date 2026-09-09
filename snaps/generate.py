#!/usr/bin/env python3
"""Generate the raw photos for every snap in snaps.json with an image model.

The prompt for a snap is:  style_prefix + scene + style_suffix + suffix_extra
(exactly the wording that produced the reference photos).

Two ways to get the photos:

A) Google Flow (labs.google/flow) with Nano Banana 2 — manual, in the browser:
     python generate.py --export flow          # writes flow/<id>.txt + flow/PROMPTS.md to copy-paste
   In Flow: Bilder > Modell "Nano Banana 2", Seitenverhältnis 9:16, ein Bild pro Prompt.
   Then pull the downloads in with import_raw.py (see there).

B) an API (picked with --backend, default "auto" = first one with a key present):
  nanobanana GEMINI_API_KEY/GOOGLE_API_KEY gemini-3.1-flash-image-preview (Nano Banana 2), 9:16, 2K
  gemini     GEMINI_API_KEY/GOOGLE_API_KEY imagen-4.0-generate-001, aspect 9:16
  openai     OPENAI_API_KEY               gpt-image-1, 1024x1536 portrait (cropped to 9:16 by snapify)
  bedrock    AWS credentials (boto3)      amazon.nova-canvas-v1:0, 720x1280

Usage:
  python generate.py                         # all snaps -> raw/<id>.png
  python generate.py 03-delilah --n 3        # 3 variants of one snap -> raw/03-delilah.png, -2.png, -3.png
  python generate.py --dry                   # only print the prompts
Existing files are skipped unless --force is given.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"


def full_prompt(cfg: dict, snap: dict) -> str:
    parts = [cfg["style_prefix"], snap["scene"], cfg["style_suffix"], snap.get("suffix_extra", "")]
    return " ".join(p.strip() for p in parts if p.strip())


# --------------------------------------------------------------------------- backends

def gen_openai(prompt: str, seed: int | None) -> bytes:
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"), "prompt": prompt,
              "size": "1024x1536", "quality": os.environ.get("OPENAI_IMAGE_QUALITY", "high"), "n": 1},
        timeout=300,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


def gen_nanobanana(prompt: str, seed: int | None) -> bytes:
    """Nano Banana 2 through the Gemini API (generateContent with an image response)."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    model = os.environ.get("NANOBANANA_MODEL", "gemini-3.1-flash-image-preview")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": "9:16", "imageSize": "2K"}}}
    if seed is not None:
        body["generationConfig"]["seed"] = seed
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, json=body, timeout=300)
    r.raise_for_status()
    for part in r.json()["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError("no image in response: " + json.dumps(r.json())[:300])


def gen_gemini(prompt: str, seed: int | None) -> bytes:
    key = os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    model = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-4.0-generate-001")
    params = {"sampleCount": 1, "aspectRatio": "9:16", "personGeneration": "allow_adult"}
    if seed is not None:
        params["seed"] = seed
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict",
        headers={"x-goog-api-key": key},
        json={"instances": [{"prompt": prompt}], "parameters": params},
        timeout=300,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["predictions"][0]["bytesBase64Encoded"])


def gen_bedrock(prompt: str, seed: int | None) -> bytes:
    import boto3  # optional dependency

    client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    body = {"taskType": "TEXT_IMAGE", "textToImageParams": {"text": prompt[:1024]},
            "imageGenerationConfig": {"numberOfImages": 1, "width": 720, "height": 1280,
                                      "cfgScale": 6.5, "seed": seed if seed is not None else 0}}
    resp = client.invoke_model(modelId=os.environ.get("BEDROCK_IMAGE_MODEL", "amazon.nova-canvas-v1:0"),
                               body=json.dumps(body), accept="application/json", contentType="application/json")
    return base64.b64decode(json.loads(resp["body"].read())["images"][0])


BACKENDS = {
    "nanobanana": (gen_nanobanana, lambda: bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))),
    "openai": (gen_openai, lambda: bool(os.environ.get("OPENAI_API_KEY"))),
    "gemini": (gen_gemini, lambda: bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))),
    "bedrock": (gen_bedrock, lambda: bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"))),
}


def pick_backend(name: str) -> str:
    if name != "auto":
        return name
    for n, (_, available) in BACKENDS.items():
        if available():
            return n
    sys.exit("no image backend configured: set OPENAI_API_KEY, GEMINI_API_KEY or AWS credentials")


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="snap ids to generate (default: all)")
    ap.add_argument("--backend", default="auto", choices=["auto", *BACKENDS])
    ap.add_argument("--n", type=int, default=1, help="variants per snap")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="overwrite existing raw files")
    ap.add_argument("--dry", action="store_true", help="print prompts only")
    ap.add_argument("--export", type=Path, default=None, metavar="DIR",
                    help="write one prompt file per snap plus PROMPTS.md into DIR (for Google Flow)")
    ap.add_argument("--config", type=Path, default=HERE / "snaps.json")
    args = ap.parse_args(argv)

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    snaps = [s for s in cfg["snaps"] if not args.ids or s["id"] in args.ids]
    if not snaps:
        sys.exit("no matching snaps")
    if args.export:
        args.export.mkdir(parents=True, exist_ok=True)
        md = ["# Prompts für Google Flow (Nano Banana 2, 9:16, 1 Bild pro Prompt)\n",
              "Heruntergeladene Datei danach zuordnen: `python import_raw.py <id> <datei>`\n"]
        for s in snaps:
            (args.export / f"{s['id']}.txt").write_text(full_prompt(cfg, s) + "\n", encoding="utf-8")
            md.append(f"## {s['id']}  —  Caption: „{s['caption']}“\n\n```\n{full_prompt(cfg, s)}\n```\n")
        (args.export / "PROMPTS.md").write_text("\n".join(md), encoding="utf-8")
        print(f"wrote {len(snaps)} prompts to {args.export}/")
        return 0
    if args.dry:
        for s in snaps:
            print(f"### {s['id']}\n{full_prompt(cfg, s)}\n")
        return 0

    backend = pick_backend(args.backend)
    gen = BACKENDS[backend][0]
    RAW.mkdir(exist_ok=True)
    for s in snaps:
        prompt = full_prompt(cfg, s)
        for k in range(1, args.n + 1):
            out = RAW / (f"{s['id']}.png" if k == 1 else f"{s['id']}-{k}.png")
            if out.exists() and not args.force:
                print("skip (exists)", out.name)
                continue
            seed = None if args.seed is None else args.seed + k - 1
            for attempt in range(3):
                try:
                    data = gen(prompt, seed)
                    break
                except Exception as e:  # network / rate-limit: retry with backoff
                    if attempt == 2:
                        raise
                    print(f"  {backend} failed ({e}); retrying", file=sys.stderr)
                    time.sleep(2 ** (attempt + 1))
            out.write_bytes(data)
            print(f"[{backend}] wrote {out.relative_to(HERE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
