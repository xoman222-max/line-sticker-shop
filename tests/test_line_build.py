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
            assert "stickers/01.png" in names
            assert "manifest.json" in names
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


def main():
    assert SCRIPT.exists(), SCRIPT
    test_wechat_default_still_runs_without_line_flags()
    test_bad_count_fails()
    test_static_build_and_check()
    test_animated_build_and_check()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
