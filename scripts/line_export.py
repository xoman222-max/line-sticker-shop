#!/usr/bin/env python3
"""LINE Creators Market export helpers used by sticker.py.

Static stickers: PNG ≤370×320 (even), transparent, ≤1MB; counts 8/16/24/32/40;
main.png 240×240; tab.png 96×74; zip ≤60MB.

Animated stickers (--animated): APNG (.png) ≤320×270 with at least one side ≥270;
5–20 frames; 1–4 loops whose COMBINED playback (one loop × loops) is ≤4s;
≤1MB each; counts 8/16/24; main APNG 240×240; tab static PNG 96×74.

Upload ZIP is flat: 01.png … NN.png, main.png, tab.png only (LINE only processes
correctly named files). Rules verified 2026-11-07 against:
  https://creator.line.me/en/guideline/sticker/
  https://creator.line.me/en/guideline/animationsticker/
Local checks cannot guarantee LINE review acceptance.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

STATIC_COUNTS = frozenset({8, 16, 24, 32, 40})
ANIM_COUNTS = frozenset({8, 16, 24})
STATIC_MAX = (370, 320)
ANIM_MAX = (320, 270)
ANIM_MIN_SIDE = 270
MAIN_SIZE = (240, 240)
TAB_SIZE = (96, 74)
MAX_FILE = 1 * 1024 * 1024
MAX_ZIP = 60 * 1024 * 1024
MARGIN = 10
ANIM_FRAMES = (5, 20)
ANIM_MAX_PLAY_MS = 4000  # combined length of all loops
ANIM_LOOPS = (1, 4)


def _even(n: int) -> int:
    n = max(2, int(n))
    return n if n % 2 == 0 else n - 1


def _alpha_bbox(im: Image.Image, threshold: int = 8):
    a = im.getchannel("A")
    return a.point(lambda v: 255 if v > threshold else 0).getbbox()


def _fit_on_canvas(im: Image.Image, canvas: tuple[int, int], margin: int = MARGIN, bbox=None) -> Image.Image:
    """Crop to content (or shared bbox), scale into canvas leaving ~margin, center on transparent canvas."""
    im = im.convert("RGBA")
    box = bbox if bbox is not None else _alpha_bbox(im)
    if box:
        im = im.crop(box)
    max_w = max(2, canvas[0] - 2 * margin)
    max_h = max(2, canvas[1] - 2 * margin)
    im.thumbnail((max_w, max_h), Image.LANCZOS)
    w, h = _even(im.width), _even(im.height)
    if (w, h) != im.size:
        im = im.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    out.paste(im, ((canvas[0] - im.width) // 2, (canvas[1] - im.height) // 2), im)
    return out


def _union_bbox(frames: list[Image.Image]):
    """Shared crop box so per-frame motion survives fitting."""
    union = None
    for fr in frames:
        b = _alpha_bbox(fr.convert("RGBA"))
        if not b:
            continue
        if union is None:
            union = list(b)
        else:
            union[0] = min(union[0], b[0])
            union[1] = min(union[1], b[1])
            union[2] = max(union[2], b[2])
            union[3] = max(union[3], b[3])
    return tuple(union) if union else None


def _fit_static_sticker(im: Image.Image) -> Image.Image:
    """Fit into ≤370×320 with even sides; prefer full 370×320 canvas for chat size."""
    return _fit_on_canvas(im, STATIC_MAX, MARGIN)


def _fit_anim_frame(im: Image.Image) -> Image.Image:
    """Always 320×270 so width≥270 and height≥270 rule is satisfied."""
    return _fit_on_canvas(im, ANIM_MAX, MARGIN)


def _save_png(im: Image.Image, path: Path, limit: int = MAX_FILE) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = im.convert("RGBA")
    im.save(path, format="PNG", optimize=True)
    size = path.stat().st_size
    if size > limit:
        # Retry with palette (keeps transparency via RGBA→P with alpha)
        q = im.quantize(colors=256, method=Image.MEDIANCUT)
        q.save(path, format="PNG", optimize=True)
        size = path.stat().st_size
    if size > limit:
        raise RuntimeError(f"{path.name} is {size} bytes, over {limit} byte limit")
    return size


def _save_apng(frames: list[Image.Image], path: Path, duration_ms: int, loops: int, limit: int = MAX_FILE) -> int:
    if not frames:
        raise RuntimeError("no frames for APNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Pillow: duration can be int (all frames) or list; loop=N means play N times
    # Do not pass optimize=True — Pillow may collapse APNG frames.
    frames[0].save(
        path,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=loops,
        disposal=2,
        blend=0,
        default_image=False,
    )
    size = path.stat().st_size
    if size > limit:
        # Drop to every other frame if still too big (keep ≥5)
        if len(frames) >= 10:
            slim = frames[::2]
            if len(slim) < ANIM_FRAMES[0]:
                slim = frames[: ANIM_FRAMES[0]]
            per = max(1, int(round(duration_ms * len(frames) / len(slim))))
            return _save_apng(slim, path, per, loops, limit)
        raise RuntimeError(f"{path.name} is {size} bytes, over {limit} byte limit after compression")
    return size


def _sheet_frames(sheet_path: Path, cell_size: tuple[int, int] | None = None) -> list[Image.Image]:
    """Slice a 4×4 sprite sheet into 16 frames (same convention as WeChat path)."""
    grid = 4
    s = Image.open(sheet_path).convert("RGBA")
    w, h = s.width // grid, s.height // grid
    frames = [
        s.crop((x * w, y * h, x * w + w, y * h + h))
        for y in range(grid)
        for x in range(grid)
    ]
    if cell_size:
        frames = [f.resize(cell_size, Image.LANCZOS) for f in frames]
    return frames


def _pick_static_frame(sheet_path: Path) -> Image.Image:
    frames = _sheet_frames(sheet_path)
    return frames[len(frames) // 2]


def _select_anim_frames(frames: list[Image.Image], want_min: int = 5, want_max: int = 20) -> list[Image.Image]:
    n = len(frames)
    if n < want_min:
        # Duplicate last frames to reach minimum (synthetic/short inputs)
        out = list(frames)
        while len(out) < want_min:
            out.append(frames[-1].copy())
        return out
    if n <= want_max:
        return frames
    # Evenly sample want_max frames
    idxs = [round(i * (n - 1) / (want_max - 1)) for i in range(want_max)]
    return [frames[i] for i in idxs]


def _all_same(frames: list[Image.Image]) -> bool:
    first = frames[0].convert("RGBA").tobytes()
    return all(f.convert("RGBA").tobytes() == first for f in frames[1:])


def _fit_timing(n_frames: int, frame_ms: int, loops: int) -> tuple[int, int]:
    """Keep per-loop × loops ≤ 4000ms: reduce loops first, then shorten frames."""
    frame_ms = max(20, int(frame_ms))
    per_loop = frame_ms * n_frames
    while loops > 1 and per_loop * loops > ANIM_MAX_PLAY_MS:
        loops -= 1
    if per_loop * loops > ANIM_MAX_PLAY_MS:
        frame_ms = ANIM_MAX_PLAY_MS // (n_frames * loops)
    return frame_ms, loops


def text_width(s: str) -> int:
    """LINE counts Asian characters and some symbols as 2."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F", "A") else 1 for c in s)


def _resolve_asset(p: Path, pack: dict, names: list[str]) -> Path | None:
    raw = p / "assets_raw"
    for name in names:
        cand = raw / f"{name}.png"
        if cand.exists():
            return cand
    char = p / pack.get("character", "character.png")
    return char if char.exists() else None


def _line_counts_ok(n: int, animated: bool) -> bool:
    return n in (ANIM_COUNTS if animated else STATIC_COUNTS)


def build_line(p: Path, pack: dict, animated: bool = False) -> Path:
    stickers = pack["stickers"]
    n = len(stickers)
    if not _line_counts_ok(n, animated):
        allowed = sorted(ANIM_COUNTS if animated else STATIC_COUNTS)
        kind = "animated" if animated else "static"
        raise SystemExit(
            f"LINE {kind} sticker sets must have one of {allowed} stickers; pack.json has {n}."
        )

    out = p / ("submit_line_animated" if animated else "submit_line")
    stickers_dir = out / "stickers"
    stickers_dir.mkdir(parents=True, exist_ok=True)

    frame_ms = int(pack.get("frame_ms", 120))
    loops = int(pack.get("line_loops", 3))
    if animated and not (ANIM_LOOPS[0] <= loops <= ANIM_LOOPS[1]):
        raise SystemExit(f"line_loops must be {ANIM_LOOPS[0]}–{ANIM_LOOPS[1]}, got {loops}")

    built = []
    for i, s in enumerate(stickers, 1):
        sheet = p / "sheets" / f"{i:02d}.png"
        # Also accept a pre-made single PNG in stickers_raw/
        raw_one = p / "stickers_raw" / f"{i:02d}.png"
        frame_dir = p / "frames_raw" / f"{i:02d}"
        frame_files = sorted(frame_dir.glob("*.png")) if frame_dir.is_dir() else []
        if not sheet.exists() and not raw_one.exists() and not frame_files:
            raise SystemExit(
                f"Missing sheets/{i:02d}.png, stickers_raw/{i:02d}.png or frames_raw/{i:02d}/*.png "
                f"for sticker {i} ({s.get('word','')})"
            )

        dest = stickers_dir / f"{i:02d}.png"
        if animated:
            if frame_files:
                frames = [Image.open(x).convert("RGBA") for x in frame_files]
            elif sheet.exists():
                frames = _sheet_frames(sheet)
            else:
                # Single image: treat as 1 frame → duplicate to min frames
                frames = [Image.open(raw_one).convert("RGBA")]
            frames = _select_anim_frames(frames, *ANIM_FRAMES)
            shared = _union_bbox(frames)
            frames = [_fit_on_canvas(f, ANIM_MAX, MARGIN, bbox=shared) for f in frames]
            if _all_same(frames):
                raise SystemExit(f"sticker {i:02d}: all frames identical — LINE rejects non-animating APNGs")
            frame_ms_use, loops_use = _fit_timing(len(frames), frame_ms, loops)
            if loops_use != loops:
                print(f"  note {i:02d}: loops {loops}→{loops_use} to keep combined playback ≤{ANIM_MAX_PLAY_MS}ms")
            size = _save_apng(frames, dest, frame_ms_use, loops_use)
            nf, per_loop, lp = _apng_timing(dest)
            print(f"{i:02d} {s.get('word','')}: APNG {size // 1024}KB {nf}f {per_loop}ms×{lp}={per_loop*lp}ms")
        else:
            if sheet.exists():
                im = _pick_static_frame(sheet)
            else:
                im = Image.open(raw_one).convert("RGBA")
            im = _fit_static_sticker(im)
            size = _save_png(im, dest)
            print(f"{i:02d} {s.get('word','')}: PNG {im.size[0]}x{im.size[1]} {size // 1024}KB")
        built.append(dest)

    # main + tab
    cover = _resolve_asset(p, pack, ["cover", "icon"])
    icon = _resolve_asset(p, pack, ["icon", "cover"])
    if cover is None:
        # Fall back to first sticker frame
        cover_im = Image.open(built[0]).convert("RGBA")
        if animated:
            # first frame of APNG
            cover_im.seek(0)
    else:
        cover_im = Image.open(cover).convert("RGBA")

    main_path = out / "main.png"
    if animated:
        # Build a short APNG main from cover (or pulse single frame to 5 frames)
        if cover is not None and cover.suffix.lower() == ".png":
            base = _fit_on_canvas(cover_im, MAIN_SIZE, 8)
        else:
            base = _fit_on_canvas(Image.open(built[0]).convert("RGBA"), MAIN_SIZE, 8)
            try:
                Image.open(built[0]).seek(0)
            except Exception:
                pass
        main_frames = [base.copy() for _ in range(5)]
        # tiny opacity pulse so frames aren't identical (LINE rejects all-identical frames)
        for idx, fr in enumerate(main_frames):
            if idx % 2:
                # nudge 1px to change pixels without looking broken
                shifted = Image.new("RGBA", MAIN_SIZE, (0, 0, 0, 0))
                shifted.paste(fr, (1, 0), fr)
                main_frames[idx] = shifted
        main_ms, main_loops = _fit_timing(len(main_frames), 200, 1)
        _save_apng(main_frames, main_path, main_ms, main_loops)
    else:
        _save_png(_fit_on_canvas(cover_im, MAIN_SIZE, 8), main_path)

    if icon is None:
        tab_im = cover_im
    else:
        tab_im = Image.open(icon).convert("RGBA")
    tab_path = out / "tab.png"
    # Tab is always static PNG
    tab_fitted = ImageOps.fit(tab_im, TAB_SIZE, Image.LANCZOS, centering=(0.5, 0.4))
    # Preserve alpha: fit on RGBA canvas
    tab_canvas = Image.new("RGBA", TAB_SIZE, (0, 0, 0, 0))
    src = tab_im.copy()
    src.thumbnail((TAB_SIZE[0] - 4, TAB_SIZE[1] - 4), Image.LANCZOS)
    tab_canvas.paste(src, ((TAB_SIZE[0] - src.width) // 2, (TAB_SIZE[1] - src.height) // 2), src)
    _save_png(tab_canvas, tab_path)

    # manifest / readme for Creators Market form fields
    title = pack.get("name", "")
    desc = pack.get("intro", "")
    creator = pack.get("creator") or pack.get("copyright", "")
    copyright_ = pack.get("copyright", "")
    manifest = {
        "platform": "LINE Creators Market",
        "type": "animated" if animated else "static",
        "title": title,
        "description": desc,
        "creator": creator,
        "copyright": copyright_,
        "sticker_count": n,
        "files": {
            "stickers": [f"{i:02d}.png" for i in range(1, n + 1)],
            "main": "main.png",
            "tab": "tab.png",
        },
        "notes": [
            "Upload via https://creator.line.me/ — declare AI use if applicable.",
            "Static: PNG ≤370×320 even, transparent, ≤1MB; counts 8/16/24/32/40.",
            "Animated: APNG (.png) ≤320×270, one side ≥270, 5–20 frames, 1–4 loops with combined playback ≤4s, ≤1MB; counts 8/16/24.",
            "ZIP must be ≤60MB.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = "\n".join(
        [
            f"# LINE upload pack — {title}",
            "",
            f"- Type: {'animated (APNG)' if animated else 'static PNG'}",
            f"- Title (≤40 chars): {title}",
            f"- Description (≤160 chars): {desc}",
            f"- Creator (≤50 chars): {creator}",
            f"- Copyright (≤50 chars): {copyright_}",
            f"- Stickers: {n}",
            "",
            "## Files",
            "- stickers/01.png … — sticker images (stored flat as 01.png … in the upload ZIP)",
            "- main.png — store main image (240×240)",
            "- tab.png — chat tab icon (96×74, static PNG)",
            "- manifest.json — machine-readable copy of the fields above",
            "",
            "Upload the zip, or the files individually, at LINE Creators Market.",
            "Specs: https://creator.line.me/zh-hant/guideline/sticker/",
            "",
        ]
    )
    (out / "README.md").write_text(readme, encoding="utf-8")
    # Also Traditional Chinese listing mirror
    (p / "LINE上架文案.md").write_text(
        "\n".join(
            [
                f"# {title} LINE 上架文案",
                "",
                f"- 貼圖名稱：{title}",
                f"- 介紹：{desc}",
                f"- 作者：{creator}",
                f"- 版權：{copyright_}",
                f"- 類型：{'動態 APNG' if animated else '靜態 PNG'}",
                f"- 張數：{n}",
                "",
                "| 序號 | 含義詞 |",
                "|---|---|",
                *[f"| {i:02d} | {s.get('word', '')} |" for i, s in enumerate(stickers, 1)],
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    zip_name = "line_animated_submit.zip" if animated else "line_submit.zip"
    zip_path = p / zip_name
    # Flat upload ZIP: LINE only processes correctly named files (01.png…, main.png, tab.png).
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in built:
            z.write(f, f.name)
        z.write(main_path, "main.png")
        z.write(tab_path, "tab.png")
    zsize = zip_path.stat().st_size
    if zsize > MAX_ZIP:
        raise SystemExit(f"ZIP is {zsize} bytes, over LINE's 60MB limit")
    print(f"LINE output: {out}")
    print(f"ZIP: {zip_path} ({zsize // 1024}KB)")
    print(f"Listing: {p / 'LINE上架文案.md'}")
    return zip_path


PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _chunks(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        typ = data[pos + 4:pos + 8]
        yield typ, data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IEND":
            break


def _png_info(path: Path) -> dict:
    """Parse PNG/APNG chunks directly (independent of Pillow's APNG handling)."""
    data = path.read_bytes()
    info = {"png": data[:8] == PNG_SIG, "apng": False, "frames": 1, "plays": None, "delays_ms": [], "frame_rects": []}
    if not info["png"]:
        return info
    for typ, body in _chunks(data):
        if typ == b"IHDR":
            info["size"] = (int.from_bytes(body[0:4], "big"), int.from_bytes(body[4:8], "big"))
            info["color_type"] = body[9]
        elif typ == b"acTL":
            info["apng"] = True
            info["frames"] = int.from_bytes(body[0:4], "big")
            info["plays"] = int.from_bytes(body[4:8], "big")
        elif typ == b"fcTL":
            w, h = int.from_bytes(body[4:8], "big"), int.from_bytes(body[8:12], "big")
            x, y = int.from_bytes(body[12:16], "big"), int.from_bytes(body[16:20], "big")
            num, den = int.from_bytes(body[20:22], "big"), int.from_bytes(body[22:24], "big") or 100
            info["frame_rects"].append((x, y, w, h))
            info["delays_ms"].append(round(num * 1000 / den))
    return info


def _apng_timing(path: Path) -> tuple[int, int, int]:
    """(frame_count, one_loop_ms, plays) from acTL/fcTL."""
    i = _png_info(path)
    return i["frames"], sum(i["delays_ms"]), i["plays"] or 0


def _decoded_frames(path: Path) -> list[Image.Image]:
    im = Image.open(path)
    out = []
    for k in range(getattr(im, "n_frames", 1)):
        im.seek(k)
        out.append(im.convert("RGBA").copy())
    return out


def _margin(im: Image.Image) -> int | None:
    b = _alpha_bbox(im.convert("RGBA"))
    if not b:
        return None
    return min(b[0], b[1], im.width - b[2], im.height - b[3])


def check_line(p: Path, pack: dict, animated: bool = False) -> int:
    fails: list[str] = []
    warns: list[str] = []
    F, W = fails.append, warns.append

    title = pack.get("name", "")
    desc = pack.get("intro", "")
    creator = pack.get("creator") or pack.get("copyright", "")
    copyright_ = pack.get("copyright", "")
    for label, val, lim in (("title", title, 40), ("creator", creator, 50), ("description", desc, 160), ("copyright", copyright_, 50)):
        w = text_width(val)
        if label in ("title", "creator", "copyright") and not val:
            F(f"{label} is empty")
        if w > lim:
            F(f"{label} width {w} > {lim} (Asian chars count as 2): {val!r}")

    stickers = pack["stickers"]
    n = len(stickers)
    if not _line_counts_ok(n, animated):
        allowed = sorted(ANIM_COUNTS if animated else STATIC_COUNTS)
        F(f"sticker count {n} not in {allowed} for {'animated' if animated else 'static'} LINE packs")

    out = p / ("submit_line_animated" if animated else "submit_line")
    if not out.exists():
        F(f"missing {out.name}/ — run: python3 scripts/sticker.py build <pack> --target line" + (" --animated" if animated else ""))
        _print_results(fails, warns)
        return min(len(fails), 100)

    def common(f: Path, tag: str):
        info = _png_info(f)
        if not info["png"]:
            F(f"{tag}: not a PNG file")
            return None
        if f.stat().st_size > MAX_FILE:
            F(f"{tag}: {f.stat().st_size} bytes > 1MB")
        if info.get("color_type") in (0, 4):
            W(f"{tag}: grayscale PNG; LINE asks for RGB colour mode")
        return info

    for i, s in enumerate(stickers, 1):
        f = out / "stickers" / f"{i:02d}.png"
        tag = f"{i:02d} {s.get('word', '')}"
        if not f.exists():
            F(f"{tag}: missing {f.name}")
            continue
        info = common(f, tag)
        if info is None:
            continue
        w, h = info["size"]
        if animated:
            if w > ANIM_MAX[0] or h > ANIM_MAX[1]:
                F(f"{tag}: size {w}x{h} exceeds {ANIM_MAX[0]}x{ANIM_MAX[1]}")
            if max(w, h) < ANIM_MIN_SIDE:
                F(f"{tag}: width or height must be ≥{ANIM_MIN_SIDE}, got {w}x{h}")
            if w % 2 or h % 2:
                W(f"{tag}: odd dimensions {w}x{h} (even required only for static; LINE may resize)")
            if not info["apng"]:
                F(f"{tag}: expected APNG (acTL chunk missing)")
                continue
            nf, plays = info["frames"], info["plays"]
            if not (ANIM_FRAMES[0] <= nf <= ANIM_FRAMES[1]):
                F(f"{tag}: frame count {nf} not in {ANIM_FRAMES[0]}–{ANIM_FRAMES[1]}")
            if plays == 0:
                F(f"{tag}: num_plays=0 (infinite loop); LINE requires 1–4 loops")
            elif not (ANIM_LOOPS[0] <= plays <= ANIM_LOOPS[1]):
                F(f"{tag}: loops {plays} not in {ANIM_LOOPS[0]}–{ANIM_LOOPS[1]}")
            per_loop = sum(info["delays_ms"])
            combined = per_loop * max(plays or 1, 1)
            if combined > ANIM_MAX_PLAY_MS:
                F(f"{tag}: combined playback {per_loop}ms×{plays}={combined}ms > {ANIM_MAX_PLAY_MS}ms")
            for (x, y, fw, fh) in info["frame_rects"]:
                if x + fw > w or y + fh > h:
                    F(f"{tag}: a frame exceeds the canvas {w}x{h}")
                    break
            frames = _decoded_frames(f)
            if len(frames) > 1 and _all_same(frames):
                F(f"{tag}: all frames identical (LINE upload error)")
            first = frames[0]
            if first.getchannel("A").getextrema()[0] > 8:
                F(f"{tag}: background must be transparent (first frame has no transparent pixel)")
            if _alpha_bbox(first) is None:
                W(f"{tag}: first frame is empty — LINE STORE shows the first frame as the static preview")
            m = min((x for x in (_margin(fr) for fr in frames) if x is not None), default=None)
        else:
            if info["apng"]:
                W(f"{tag}: APNG in a static pack; only the first frame will be used")
            if w > STATIC_MAX[0] or h > STATIC_MAX[1]:
                F(f"{tag}: size {w}x{h} exceeds {STATIC_MAX[0]}x{STATIC_MAX[1]}")
            if w % 2 or h % 2:
                F(f"{tag}: dimensions must be even, got {w}x{h}")
            rgba = Image.open(f).convert("RGBA")
            if rgba.getchannel("A").getextrema()[0] > 8:
                F(f"{tag}: background must be transparent")
            m = _margin(rgba)
            if m is None:
                F(f"{tag}: image is fully transparent")
        if m is not None and m < 8:
            W(f"{tag}: content only {m}px from edge (LINE suggests ~{MARGIN}px margin)")

    extra = sorted(x.name for x in (out / "stickers").glob("*.png") if not re.fullmatch(r"\d{2}\.png", x.name) or int(x.stem) > n)
    if extra:
        F(f"unexpected files in stickers/: {extra}")

    main, tab = out / "main.png", out / "tab.png"
    if not main.exists():
        F("missing main.png")
    else:
        info = common(main, "main.png")
        if info:
            if info["size"] != MAIN_SIZE:
                F(f"main.png size {info['size']}, want {MAIN_SIZE}")
            if animated and not info["apng"]:
                F("main.png must be APNG for animated packs")
            if not animated and info["apng"]:
                W("main.png is APNG in a static pack")
            if Image.open(main).convert("RGBA").getchannel("A").getextrema()[0] > 8:
                W("main.png has no transparent pixels (LINE asks for transparent backgrounds)")
    if not tab.exists():
        F("missing tab.png")
    else:
        info = common(tab, "tab.png")
        if info:
            if info["size"] != TAB_SIZE:
                F(f"tab.png size {info['size']}, want {TAB_SIZE}")
            if info["apng"]:
                F("tab.png must be a static PNG (not APNG)")

    zip_name = "line_animated_submit.zip" if animated else "line_submit.zip"
    zp = p / zip_name
    if not zp.exists():
        F(f"missing {zip_name}")
    else:
        if zp.stat().st_size > MAX_ZIP:
            F(f"{zip_name} is {zp.stat().st_size} bytes > 60MB")
        with zipfile.ZipFile(zp) as z:
            names = set(z.namelist())
        want = {f"{i:02d}.png" for i in range(1, n + 1)} | {"main.png", "tab.png"}
        if names - want:
            F(f"{zip_name}: unexpected entries {sorted(names - want)} (ZIP must be flat 01.png…, main.png, tab.png)")
        if want - names:
            F(f"{zip_name}: missing entries {sorted(want - names)}")

    if not (out / "manifest.json").exists():
        W("missing manifest.json in submit folder")

    _print_results(fails, warns)
    return min(len(fails), 100)


def _print_results(fails, warns):
    for x in warns:
        print("WARN", x)
    for x in fails:
        print("FAIL", x)
    print(f"結果：{len(fails)} 個必須改，{len(warns)} 個要人看。")
    print("本地檢查通過不代表 LINE 審核通過。機器看不了的：角色一致性、文字侵權、AI 使用聲明、權利歸屬。")
