#!/usr/bin/env python3
"""Atlas safety check before slicing: empty cells, sprites touching cell edges
(top padding = clipped heads), and ink in the gutters between cells.

  python3 scripts/atlas_check.py atlas.png --grid 4 4 [--min-pad 12] [--gutter 8]

Exit 1 on FAIL. Measurable only; still inspect the atlas visually.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


def check(path: Path, cols: int, rows: int, min_pad: int = 12, gutter: int = 8, thr: int = 16):
    im = Image.open(path).convert("RGBA")
    a = im.getchannel("A").point(lambda v: 255 if v > thr else 0)
    if a.getextrema()[0] == 255:
        return ["FAIL atlas has no transparent pixels (opaque background)"], []
    cw, ch = im.width // cols, im.height // rows
    fails, warns = [], []
    for r in range(rows):
        for c in range(cols):
            box = (c * cw, r * ch, c * cw + cw, r * ch + ch)
            b = a.crop(box).getbbox()
            tag = f"cell[{c},{r}]"
            if not b:
                warns.append(f"WARN {tag} empty")
                continue
            pads = {"top": b[1], "left": b[0], "right": cw - b[2], "bottom": ch - b[3]}
            for side, v in pads.items():
                if v < min_pad:
                    (fails if v <= 1 else warns).append(
                        f"{'FAIL' if v <= 1 else 'WARN'} {tag} {side} padding {v}px (<{min_pad})"
                        + (" — likely clipped" if v <= 1 else ""))
    for c in range(1, cols):
        x = c * cw
        if a.crop((x - gutter // 2, 0, x + gutter // 2, im.height)).getbbox():
            warns.append(f"WARN ink in vertical gutter at x={x}")
    for r in range(1, rows):
        y = r * ch
        if a.crop((0, y - gutter // 2, im.width, y + gutter // 2)).getbbox():
            warns.append(f"WARN ink in horizontal gutter at y={y}")
    return fails, warns


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("atlas", type=Path)
    ap.add_argument("--grid", type=int, nargs=2, default=(4, 4), metavar=("COLS", "ROWS"))
    ap.add_argument("--min-pad", type=int, default=12)
    ap.add_argument("--gutter", type=int, default=8)
    a = ap.parse_args(argv)
    fails, warns = check(a.atlas, *a.grid, a.min_pad, a.gutter)
    for x in warns + fails:
        print(x)
    print(f"atlas: {len(fails)} FAIL, {len(warns)} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
