#!/usr/bin/env python3
"""Synthetic-image tests for LINE build/check. No paid APIs, no credentials."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sticker.py"


def _sprite_sheet(path: Path, color, label: str = ""):
    """4x4 sheet 960x960 with a moving blob so frames differ."""
    grid, cell = 4, 240
    sheet = Image.new("RGBA", (grid * cell, grid * cell), (0, 0, 0, 0))
    for y in range(grid):
        for x in range(grid):
            i = y * grid + x
            fr = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
            d = ImageDraw.Draw(fr)
            ox = 40 + (i % 5) * 8
            oy = 50 + (i % 7) * 6
            d.ellipse((ox, oy, ox + 120, oy + 120), fill=color)
            d.rectangle((ox + 30, oy + 40, ox + 50, oy + 60), fill=(0, 0, 0, 255))
            d.rectangle((ox + 70, oy + 40, ox + 90, oy + 60), fill=(0, 0, 0, 255))
            if label:
                d.text((ox + 20, oy + 90), label[:4], fill=(255, 255, 255, 255))
            sheet.paste(fr, (x * cell, y * cell), fr)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def _cover(path: Path, color):
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((80, 80, 430, 430), fill=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def _make_pack(tmpdir: Path, n: int = 8, animated_meta: bool = False) -> Path:
    colors = [
        (255, 99, 71, 255),
        (60, 179, 113, 255),
        (65, 105, 225, 255),
        (255, 215, 0, 255),
        (186, 85, 211, 255),
        (255, 140, 0, 255),
        (0, 206, 209, 255),
        (255, 105, 180, 255),
        (100, 149, 237, 255),
        (154, 205, 50, 255),
        (210, 105, 30, 255),
        (72, 61, 139, 255),
        (46, 139, 87, 255),
        (220, 20, 60, 255),
        (70, 130, 180, 255),
        (255, 160, 122, 255),
    ]
    stickers = []
    for i in range(n):
        word = f"W{i+1:02d}"
        stickers.append({"word": word, "caption": word, "action": f"pose {i+1}"})
        _sprite_sheet(tmpdir / "sheets" / f"{i+1:02d}.png", colors[i % len(colors)], word)
    _cover(tmpdir / "assets_raw" / "cover.png", (255, 99, 71, 255))
    _cover(tmpdir / "assets_raw" / "icon.png", (65, 105, 225, 255))
    # tiny character placeholder
    _cover(tmpdir / "character.png", (60, 179, 113, 255))
    pack = {
        "name": "Test Capys",
        "intro": "Synthetic pack for offline LINE export tests.",
        "copyright": "Test Lab",
        "creator": "Test Lab",
        "character": "character.png",
        "frame_ms": 120,
        "line_loops": 3,
        "stickers": stickers,
    }
    (tmpdir / "pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmpdir


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT / "scripts"),  # so line_export import resolves
        capture_output=True,
        text=True,
    )


def test_static_build_and_check():
    with tempfile.TemporaryDirectory(prefix="line-static-") as td:
        p = _make_pack(Path(td), n=8)
        r = _run(["build", str(p), "--target", "line"])
        assert r.returncode == 0, r.stdout + "\n" + r.stderr
        assert (p / "submit_line" / "main.png").exists()
        assert (p / "submit_line" / "tab.png").exists()
        assert (p / "line_submit.zip").exists()
        assert (p / "LINE上架文案.md").exists()
        with zipfile.ZipFile(p / "line_submit.zip") as z:
            names = z.namelist()
            assert "main.png" in names
            assert "tab.png" in names
            assert set(names) == {f"{i:02d}.png" for i in range(1, 9)} | {"main.png", "tab.png"}, names
        r2 = _run(["check", str(p), "--target", "line"])
        assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
        print("PASS static build+check")


def test_animated_build_and_check():
    with tempfile.TemporaryDirectory(prefix="line-anim-") as td:
        p = _make_pack(Path(td), n=8)
        r = _run(["build", str(p), "--target", "line", "--animated"])
        assert r.returncode == 0, r.stdout + "\n" + r.stderr
        main = p / "submit_line_animated" / "main.png"
        assert main.exists()
        assert b"acTL" in main.read_bytes()
        sticker = p / "submit_line_animated" / "stickers" / "01.png"
        assert b"acTL" in sticker.read_bytes()
        tab = p / "submit_line_animated" / "tab.png"
        assert b"acTL" not in tab.read_bytes()
        r2 = _run(["check", str(p), "--target", "line", "--animated"])
        assert r2.returncode == 0, r2.stdout + "\n" + r2.stderr
        print("PASS animated build+check")


def test_bad_count_fails():
    with tempfile.TemporaryDirectory(prefix="line-bad-") as td:
        p = _make_pack(Path(td), n=8)
        # Corrupt pack to illegal count for static LINE (7 not allowed)
        pack = json.loads((p / "pack.json").read_text())
        pack["stickers"] = pack["stickers"][:7]
        (p / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
        r = _run(["build", str(p), "--target", "line"])
        assert r.returncode != 0, "expected failure for count=7"
        assert "8" in (r.stdout + r.stderr) or "must have" in (r.stdout + r.stderr).lower() or "必须" in (r.stdout + r.stderr) or "stickers" in (r.stdout + r.stderr).lower()
        print("PASS bad count rejected")


def test_wechat_default_still_runs_without_line_flags():
    """Smoke: build --help lists targets; we do not fully build wechat GIF here."""
    r = _run(["build", "--help"])
    assert r.returncode == 0
    assert "--target" in r.stdout
    assert "line" in r.stdout
    assert "--animated" in r.stdout
    print("PASS CLI help")


import os
import re as _re
from PIL import PngImagePlugin

SPEC_FAIL = _re.compile(r"^FAIL ", _re.M)


def _check(p, animated=False):
    args = ["check", str(p), "--platform", "line"] + (["--animated"] if animated else [])
    return _run(args)


def _expect_fail(p, animated, needle, label):
    r = _check(p, animated)
    out = r.stdout + r.stderr
    assert r.returncode != 0 and needle in out, f"{label}: expected FAIL containing {needle!r}\n{out}"
    print(f"PASS rejects {label}")


def _restore(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _blob(size=(300, 260), color=(255, 0, 0, 255), shift=0):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    m = min(40, size[0] // 5, size[1] // 5)
    ImageDraw.Draw(im).ellipse((m + shift, m, size[0] - m - 12 + shift, size[1] - m), fill=color)
    return im


def _apng(path, n=8, ms=100, loop=2, size=(320, 270), same=False):
    fr = [_blob(size, shift=0 if same else (k % 4) * 3) for k in range(n)]
    fr[0].save(path, format="PNG", save_all=True, append_images=fr[1:], duration=ms, loop=loop, disposal=2, blend=0)


def test_static_invalid_cases():
    with tempfile.TemporaryDirectory(prefix="line-sbad-") as td:
        p = _make_pack(Path(td), n=8)
        assert _run(["build", str(p), "--platform", "line"]).returncode == 0
        good = Path(td) / "_good"
        shutil.copytree(p / "submit_line", good)
        sd = p / "submit_line"
        # decoded alpha present on the valid output
        im = Image.open(sd / "stickers" / "01.png").convert("RGBA")
        assert im.getchannel("A").getextrema()[0] == 0 and im.size[0] % 2 == 0 and im.size[1] % 2 == 0
        cases = [
            ("odd dimensions", lambda: _blob((301, 260)).save(sd / "stickers" / "01.png"), "must be even"),
            ("oversize 372x320", lambda: _blob((372, 320)).save(sd / "stickers" / "01.png"), "exceeds 370x320"),
            ("opaque background", lambda: Image.new("RGBA", (370, 320), (255, 255, 255, 255)).save(sd / "stickers" / "02.png"), "transparent"),
            ("file >1MB", lambda: _big(sd / "stickers" / "03.png"), "> 1MB"),
            ("wrong main size", lambda: _blob((240, 238)).save(sd / "main.png"), "main.png size"),
            ("APNG tab", lambda: _apng(sd / "tab.png", size=(96, 74)), "tab.png must be a static PNG"),
            ("JPEG renamed .png", lambda: _blob().convert("RGB").save(sd / "stickers" / "04.png", format="JPEG"), "not a PNG"),
        ]
        for label, mut, needle in cases:
            mut()
            _expect_fail(p, False, needle, f"static {label}")
            _restore(good, sd)
        # ZIP with legacy nested layout / extra files
        with zipfile.ZipFile(p / "line_submit.zip", "a") as z:
            z.writestr("stickers/01.png", b"x")
            z.writestr("manifest.json", b"{}")
        _expect_fail(p, False, "unexpected entries", "static nested/extra ZIP entries")
        assert _run(["build", str(p), "--platform", "line"]).returncode == 0
        # wrong count and over-width title (Asian chars count as 2)
        pack = json.loads((p / "pack.json").read_text())
        pack["name"] = "貼" * 21  # width 42 > 40
        (p / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
        _expect_fail(p, False, "title width 42", "static title width (CJK=2)")
        pack["name"] = "OK"
        pack["stickers"] = pack["stickers"] + pack["stickers"][:1]
        (p / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
        _expect_fail(p, False, "sticker count 9", "static count 9")


def _big(path):
    info = PngImagePlugin.PngInfo()
    info.add_text("pad", os.urandom(800_000).hex())  # ~1.6MB uncompressed text chunk
    _blob((370, 320)).save(path, pnginfo=info)


def test_animated_invalid_cases():
    with tempfile.TemporaryDirectory(prefix="line-abad-") as td:
        p = _make_pack(Path(td), n=8)
        assert _run(["build", str(p), "--platform", "line", "--animated"]).returncode == 0
        sd = p / "submit_line_animated"
        good = Path(td) / "_good"
        shutil.copytree(sd, good)
        st = sd / "stickers"
        cases = [
            ("4 frames", lambda: _apng(st / "01.png", n=4), "frame count 4"),
            ("21 frames", lambda: _apng(st / "01.png", n=21, ms=40, loop=1), "frame count 21"),
            ("infinite loop", lambda: _apng(st / "01.png", loop=0), "infinite"),
            ("5 loops", lambda: _apng(st / "01.png", n=5, ms=100, loop=5), "loops 5"),
            ("combined >4s (1600ms x3)", lambda: _apng(st / "01.png", n=8, ms=200, loop=3), "combined playback 1600ms×3=4800ms"),
            ("static PNG instead of APNG", lambda: _blob((320, 270)).save(st / "01.png"), "acTL chunk missing"),
            ("too small 260x260", lambda: _apng(st / "01.png", size=(260, 260)), "must be ≥270"),
            ("oversize 330x270", lambda: _apng(st / "01.png", size=(330, 270)), "exceeds 320x270"),
            ("identical frames", lambda: _apng(st / "01.png", same=True), "all frames identical"),
            ("static main", lambda: _blob((240, 240)).save(sd / "main.png"), "main.png must be APNG"),
        ]
        for label, mut, needle in cases:
            mut()
            _expect_fail(p, True, needle, f"animated {label}")
            _restore(good, sd)
        # Per-loop 4s with 1 loop is allowed (limit is combined playback, not per-loop minimum)
        _apng(st / "01.png", n=8, ms=500, loop=1)
        r = _check(p, True)
        assert r.returncode == 0, r.stdout
        print("PASS animated accepts 8×500ms×1 loop = 4000ms")


def test_frames_raw_import_and_timing_clamp():
    """User/Grok images as per-frame PNGs; frame_ms*frames*loops over 4s must be clamped."""
    with tempfile.TemporaryDirectory(prefix="line-frames-") as td:
        p = _make_pack(Path(td), n=8)
        shutil.rmtree(p / "sheets")
        for i in range(1, 9):
            d = p / "frames_raw" / f"{i:02d}"
            d.mkdir(parents=True)
            for k in range(6):
                _blob((500, 500), shift=k * 5).save(d / f"{k:03d}.png")
        pack = json.loads((p / "pack.json").read_text())
        pack["frame_ms"], pack["line_loops"] = 300, 4  # 1800ms × 4 = 7200ms → must clamp
        (p / "pack.json").write_text(json.dumps(pack), encoding="utf-8")
        r = _run(["build", str(p), "--platform", "line", "--animated"])
        assert r.returncode == 0, r.stdout + r.stderr
        sys.path.insert(0, str(ROOT / "scripts"))
        from line_export import _apng_timing
        f = p / "submit_line_animated" / "stickers" / "01.png"
        nf, per_loop, plays = _apng_timing(f)
        assert nf == 6 and 1 <= plays <= 4 and per_loop * plays <= 4000, (nf, per_loop, plays)
        # Pillow decode agrees with chunk parser
        im = Image.open(f)
        assert im.n_frames == 6 and im.info.get("loop") == plays
        assert im.size == (320, 270)
        assert im.convert("RGBA").getchannel("A").getextrema()[0] == 0
        mi = Image.open(p / "submit_line_animated" / "main.png")
        assert mi.size == (240, 240) and getattr(mi, "is_animated", False)
        assert _check(p, True).returncode == 0
        with zipfile.ZipFile(p / "line_animated_submit.zip") as z:
            assert sorted(z.namelist()) == sorted([f"{i:02d}.png" for i in range(1, 9)] + ["main.png", "tab.png"])
        print(f"PASS frames_raw import; timing clamped to {per_loop}ms×{plays}")

def main():
    assert SCRIPT.exists(), SCRIPT
    test_wechat_default_still_runs_without_line_flags()
    test_bad_count_fails()
    test_static_build_and_check()
    test_animated_build_and_check()
    test_static_invalid_cases()
    test_animated_invalid_cases()
    test_frames_raw_import_and_timing_clamp()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
