#!/usr/bin/env python3
"""Bridge: composed GIFs / PNGs / decoded frame dirs → LINE project → build → check.

Feeds the vendored pixel-gif exporters (vendor/pixel_gif) or the user's own art
into the tested LINE exporter (line_export.py). Offline; no API calls.

  python3 scripts/gif_to_line.py OUT_PROJECT INPUT... --name 標題 --creator 作者 [--animated]

INPUT may be: a .gif, a .png, a directory of per-frame PNGs, or a directory
containing such items (scanned recursively for *.gif, sorted by file name).
Default GIFs loop forever at ~2s; LINE animated stickers need 1–4 loops whose
combined playback is ≤4s, so the bridge sets finite loops and the exporter clamps.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from line_export import build_line, check_line  # noqa: E402


def _word(path: Path) -> str:
    stem = path.stem if path.is_file() else path.name
    return re.sub(r"^\d+[-_ ]*", "", stem) or stem


def _collect(inputs: list[Path]) -> list[Path]:
    items: list[Path] = []
    for x in inputs:
        if x.is_file() and x.suffix.lower() in (".gif", ".png"):
            items.append(x)
        elif x.is_dir():
            gifs = sorted(x.rglob("*.gif"), key=lambda q: q.name)
            if gifs:
                items += gifs
            elif any(x.glob("*.png")) and not any(d.is_dir() for d in x.iterdir()):
                items.append(x)  # a single frame directory
            else:
                items += sorted([d for d in x.iterdir() if d.is_dir()] + list(x.glob("*.png")), key=lambda q: q.name)
        else:
            raise SystemExit(f"unsupported input: {x}")
    return items


def _frames(item: Path) -> tuple[list[Image.Image], int]:
    """RGBA frames (disposal-composited by Pillow) and one-loop duration in ms."""
    if item.is_dir():
        fr = [Image.open(f).convert("RGBA") for f in sorted(item.glob("*.png"))]
        return fr, 0
    im = Image.open(item)
    fr, total = [], 0
    for f in ImageSequence.Iterator(im):
        fr.append(f.convert("RGBA").copy())
        total += int(f.info.get("duration", 100) or 100)
    return fr, total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path, help="LINE project dir to create (must be empty or absent)")
    ap.add_argument("inputs", type=Path, nargs="+")
    ap.add_argument("--name", required=True, help="貼圖名稱 (≤40, Asian chars count 2)")
    ap.add_argument("--creator", required=True)
    ap.add_argument("--copyright", default=None)
    ap.add_argument("--intro", default="")
    ap.add_argument("--animated", action="store_true", help="APNG output (8/16/24); default static PNG (8–40)")
    ap.add_argument("--loops", type=int, default=2, help="LINE loops 1–4 (combined ≤4s enforced)")
    ap.add_argument("--still-frame", choices=("first", "middle", "last"), default="first",
                    help="which decoded frame becomes the static sticker")
    ap.add_argument("--cover", type=Path, help="PNG for main.png (default: first sticker)")
    ap.add_argument("--icon", type=Path, help="PNG for tab.png (default: cover)")
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args(argv)

    items = _collect(a.inputs)
    p = a.project
    if p.exists() and any(p.iterdir()):
        raise SystemExit(f"{p} is not empty")
    p.mkdir(parents=True, exist_ok=True)
    stickers, one_loop = [], []
    for i, item in enumerate(items, 1):
        frames, total = _frames(item)
        if not frames:
            raise SystemExit(f"no frames in {item}")
        stickers.append({"word": _word(item), "source": str(item.name)})
        if a.animated:
            d = p / "frames_raw" / f"{i:02d}"
            d.mkdir(parents=True)
            for k, f in enumerate(frames):
                f.save(d / f"{k:03d}.png")
            if total:
                one_loop.append(total)
        else:
            idx = {"first": 0, "middle": len(frames) // 2, "last": -1}[a.still_frame]
            (p / "stickers_raw").mkdir(exist_ok=True)
            frames[idx].save(p / "stickers_raw" / f"{i:02d}.png")
    raw = p / "assets_raw"
    raw.mkdir()
    if a.cover:
        shutil.copy(a.cover, raw / "cover.png")
    if a.icon:
        shutil.copy(a.icon, raw / "icon.png")
    if not a.cover:
        src = p / ("frames_raw/01/000.png" if a.animated else "stickers_raw/01.png")
        shutil.copy(src, raw / "cover.png")
    pack = {
        "name": a.name, "intro": a.intro, "creator": a.creator,
        "copyright": a.copyright or a.creator, "line_loops": a.loops, "stickers": stickers,
    }
    if one_loop:
        # keep the source GIF speed: one LINE loop ≈ source loop, spread over ≤20 sampled frames
        n = min(20, max(5, len(list((p / "frames_raw" / "01").glob("*.png")))))
        pack["frame_ms"] = max(20, round(max(one_loop) / n))
    (p / "pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"imported {len(items)} item(s) → {p}")
    build_line(p, pack, animated=a.animated)
    return 0 if a.no_check else check_line(p, pack, animated=a.animated)


if __name__ == "__main__":
    sys.exit(main())
