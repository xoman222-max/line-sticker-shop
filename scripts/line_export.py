#!/usr/bin/env python3
"""LINE Creators Market export helpers used by sticker.py.

Static stickers: PNG ≤370×320 (even), transparent, ≤1MB; counts 8/16/24/32/40;
main.png 240×240; tab.png 96×74; zip ≤60MB.

Animated stickers (--animated): APNG (.png) ≤320×270 with at least one side ≥270;
5–20 frames; total duration 1–4s; loops 1–4; ≤1MB each; counts 8/16/24;
main APNG 240×240; tab static PNG 96×74.
"""
from __future__ import annotations

import json
import sys
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
ANIM_DURATION_MS = (1000, 4000)
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
        if not sheet.exists() and not raw_one.exists():
            raise SystemExit(f"Missing sheets/{i:02d}.png (or stickers_raw/{i:02d}.png) for sticker {i} ({s.get('word','')})")

        dest = stickers_dir / f"{i:02d}.png"
        if animated:
            if sheet.exists():
                frames = _sheet_frames(sheet)
            else:
                # Single image: treat as 1 frame → duplicate to min frames
                frames = [Image.open(raw_one).convert("RGBA")]
            frames = _select_anim_frames(frames, *ANIM_FRAMES)
            shared = _union_bbox(frames)
            frames = [_fit_on_canvas(f, ANIM_MAX, MARGIN, bbox=shared) for f in frames]
            total_ms = frame_ms * len(frames)
            if total_ms < ANIM_DURATION_MS[0]:
                frame_ms_use = max(1, ANIM_DURATION_MS[0] // len(frames))
                total_ms = frame_ms_use * len(frames)
            else:
                frame_ms_use = frame_ms
            if total_ms > ANIM_DURATION_MS[1]:
                frame_ms_use = max(1, ANIM_DURATION_MS[1] // len(frames))
                total_ms = frame_ms_use * len(frames)
            size = _save_apng(frames, dest, frame_ms_use, loops)
            print(f"{i:02d} {s.get('word','')}: APNG {size // 1024}KB {len(frames)}f {total_ms}ms loop={loops}")
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
        main_ms = max(1, min(800, ANIM_DURATION_MS[1] // len(main_frames)))
        _save_apng(main_frames, main_path, main_ms, loops)
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
            "stickers": [f"stickers/{i:02d}.png" for i in range(1, n + 1)],
            "main": "main.png",
            "tab": "tab.png",
        },
        "notes": [
            "Upload via https://creator.line.me/ — declare AI use if applicable.",
            "Static: PNG ≤370×320 even, transparent, ≤1MB; counts 8/16/24/32/40.",
            "Animated: APNG (.png) ≤320×270, one side ≥270, 5–20 frames, 1–4s, loops 1–4, ≤1MB; counts 8/16/24.",
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
            "- stickers/01.png … — sticker images",
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
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out).as_posix())
    zsize = zip_path.stat().st_size
    if zsize > MAX_ZIP:
        raise SystemExit(f"ZIP is {zsize} bytes, over LINE's 60MB limit")
    print(f"LINE output: {out}")
    print(f"ZIP: {zip_path} ({zsize // 1024}KB)")
    print(f"Listing: {p / 'LINE上架文案.md'}")
    return zip_path


def _is_apng(path: Path) -> bool:
    data = path.read_bytes()
    # APNG has acTL chunk
    return b"acTL" in data


def _apng_frame_count(path: Path) -> int:
    im = Image.open(path)
    return getattr(im, "n_frames", 1)


def _apng_total_duration_ms(path: Path) -> tuple[int, int]:
    """Return (total_ms, loop_count). loop_count from info; Pillow may report 0 for infinite."""
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    durations = []
    for i in range(n):
        im.seek(i)
        durations.append(int(im.info.get("duration", 100)))
    total = sum(durations)
    loop = int(im.info.get("loop", 0))
    return total, loop


def check_line(p: Path, pack: dict, animated: bool = False) -> int:
    fails: list[str] = []
    warns: list[str] = []
    F, W = fails.append, warns.append

    title = pack.get("name", "")
    desc = pack.get("intro", "")
    creator = pack.get("creator") or pack.get("copyright", "")
    copyright_ = pack.get("copyright", "")
    # LINE counts Asian chars as 2 for some fields — we warn by len only
    if not title or len(title) > 40:
        F(f"title must be 1–40 chars, got {len(title)}: {title!r}")
    if len(desc) > 160:
        F(f"description must be ≤160 chars, got {len(desc)}")
    if len(creator) > 50:
        F(f"creator must be ≤50 chars, got {len(creator)}")
    if len(copyright_) > 50:
        F(f"copyright must be ≤50 chars, got {len(copyright_)}")

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

    for i, s in enumerate(stickers, 1):
        f = out / "stickers" / f"{i:02d}.png"
        tag = f"{i:02d} {s.get('word', '')}"
        if not f.exists():
            F(f"{tag}: missing {f.name}")
            continue
        size = f.stat().st_size
        if size > MAX_FILE:
            F(f"{tag}: {size} bytes > 1MB")
        im = Image.open(f)
        w, h = im.size
        if w % 2 or h % 2:
            F(f"{tag}: dimensions must be even, got {w}x{h}")
        if animated:
            if w > ANIM_MAX[0] or h > ANIM_MAX[1]:
                F(f"{tag}: size {w}x{h} exceeds {ANIM_MAX[0]}x{ANIM_MAX[1]}")
            if max(w, h) < ANIM_MIN_SIDE:
                F(f"{tag}: at least one side must be ≥{ANIM_MIN_SIDE}, got {w}x{h}")
            if not _is_apng(f):
                F(f"{tag}: expected APNG (acTL chunk missing)")
            else:
                nf = _apng_frame_count(f)
                if not (ANIM_FRAMES[0] <= nf <= ANIM_FRAMES[1]):
                    F(f"{tag}: frame count {nf} not in {ANIM_FRAMES[0]}–{ANIM_FRAMES[1]}")
                total, loop = _apng_total_duration_ms(f)
                if total < ANIM_DURATION_MS[0] or total > ANIM_DURATION_MS[1]:
                    F(f"{tag}: total duration {total}ms not in {ANIM_DURATION_MS[0]}–{ANIM_DURATION_MS[1]}ms")
                # Pillow may store loop differently; accept 1–4, warn on 0 (infinite)
                if loop == 0:
                    W(f"{tag}: loop=0 (infinite); LINE wants 1–4 loops")
                elif not (ANIM_LOOPS[0] <= loop <= ANIM_LOOPS[1]):
                    F(f"{tag}: loop {loop} not in {ANIM_LOOPS[0]}–{ANIM_LOOPS[1]}")
        else:
            if w > STATIC_MAX[0] or h > STATIC_MAX[1]:
                F(f"{tag}: size {w}x{h} exceeds {STATIC_MAX[0]}x{STATIC_MAX[1]}")
            rgba = im.convert("RGBA")
            if rgba.getchannel("A").getextrema()[0] > 8:
                F(f"{tag}: background must be transparent")

    main = out / "main.png"
    tab = out / "tab.png"
    if not main.exists():
        F("missing main.png")
    else:
        im = Image.open(main)
        if im.size != MAIN_SIZE:
            F(f"main.png size {im.size}, want {MAIN_SIZE}")
        if main.stat().st_size > MAX_FILE:
            F("main.png over 1MB")
        if animated and not _is_apng(main):
            F("main.png must be APNG for animated packs")
        if not animated and _is_apng(main):
            W("main.png is APNG but pack is static (usually fine if first frame shows)")

    if not tab.exists():
        F("missing tab.png")
    else:
        im = Image.open(tab)
        if im.size != TAB_SIZE:
            F(f"tab.png size {im.size}, want {TAB_SIZE}")
        if tab.stat().st_size > MAX_FILE:
            F("tab.png over 1MB")
        if _is_apng(tab):
            F("tab.png must be a static PNG (not APNG)")

    zip_name = "line_animated_submit.zip" if animated else "line_submit.zip"
    zp = p / zip_name
    if not zp.exists():
        F(f"missing {zip_name}")
    elif zp.stat().st_size > MAX_ZIP:
        F(f"{zip_name} is {zp.stat().st_size} bytes > 60MB")

    if not (out / "README.md").exists():
        W("missing README.md in submit folder")
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
    print("機器看不了的：角色有沒有跑圖、文字有沒有侵權、是否勾選 AI 生成、權利是否清楚。")
