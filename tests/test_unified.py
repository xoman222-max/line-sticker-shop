#!/usr/bin/env python3
"""End-to-end: synthetic atlas → atlas_check → vendored export_pack GIFs → review_gif
→ gif_to_line (static + animated) → LINE check. Offline, synthetic only."""
from __future__ import annotations

import glob
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"
V = ROOT / "vendor" / "pixel_gif" / "scripts"
FONTS = sorted(glob.glob("/usr/share/fonts/**/NotoSansCJK-Bold.ttc", recursive=True)
               + glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True))


def run(*args, ok=True):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    if ok:
        assert r.returncode == 0, f"{args}\n{r.stdout}\n{r.stderr}"
    return r


def atlas(path: Path, cols=4, rows=2, cell=256, top_pad=40):
    im = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    colors = [(230, 80, 80, 255), (80, 170, 90, 255), (70, 110, 220, 255), (240, 200, 40, 255)]
    for r in range(rows):
        for c in range(cols):
            x, y = c * cell, r * cell
            k = r * cols + c
            col = colors[k % 4]
            d.ellipse((x + 50 + r * 20, y + top_pad, x + 206 - r * 10, y + 210), fill=col)
            d.rectangle((x + 70 + k * 12, y + 90 + r * 30, x + 95 + k * 12, y + 115 + r * 30), fill=(0, 0, 0, 255))
            d.polygon([(x + 60, y + 200 - k * 8), (x + 120, y + 150), (x + 190, y + 200)], fill=(255, 255, 255, 255))
    im.save(path)


def test_atlas_check(td: Path):
    good, bad = td / "good.png", td / "bad.png"
    atlas(good)
    atlas(bad, top_pad=0)  # heads touch the cell top → clipped
    assert run(S / "atlas_check.py", good, "--grid", 4, 2).returncode == 0
    r = run(S / "atlas_check.py", bad, "--grid", 4, 2, ok=False)
    assert r.returncode == 1 and "top padding 0px" in r.stdout, r.stdout
    print("PASS atlas_check accepts padded atlas, rejects clipped tops")
    return good


def test_end_to_end(td: Path, good_atlas: Path):
    if not FONTS:
        print("SKIP end-to-end (no CJK/DejaVu font found)")
        return
    words = ["收到", "晚安", "加油", "哭哭", "可以", "笑死", "救命", "謝謝"]
    motions = ["nod", "breathe", "jump", "tremble", "pulse", "pop", "startle", "lean"]
    entries = [{"text": w, "cell": [i % 4, i // 4], "motion": m, "icon": "none"} for i, (w, m) in enumerate(zip(words, motions))]
    man = {"title": "測試", "count": 8, "groups": [{"name": "日常", "atlas": good_atlas.name, "grid": [4, 2],
            "ink": "#333333", "tint": "#DDDDDD", "background": "#FFFFFF", "entries": entries}]}
    mp = td / "manifest.json"
    mp.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    out = td / "gif_out"
    run(V / "export_pack.py", mp, out, "--font", FONTS[0], "--jobs", 2)
    gifs = sorted(out.rglob("*.gif"))
    assert len(gifs) == 8, gifs
    g = Image.open(gifs[0])
    assert g.n_frames > 1 and g.info.get("loop") == 0, "source GIF should loop forever"
    print(f"PASS vendored export_pack → 8 GIFs ({g.size[0]}px, {g.n_frames} frames, infinite loop)")

    rv = td / "review01"
    run(V / "review_gif.py", "extract", gifs[0], rv)
    assert any(rv.iterdir())
    print("PASS review_gif extract on a composed GIF")

    for animated in (False, True):
        proj = td / ("line_anim" if animated else "line_static")
        args = [S / "gif_to_line.py", proj, out, "--name", "測試貼圖", "--creator", "Test Lab"] + (["--animated"] if animated else [])
        r = run(*args)
        assert "0 個必須改" in r.stdout, r.stdout
        zp = proj / ("line_animated_submit.zip" if animated else "line_submit.zip")
        with zipfile.ZipFile(zp) as z:
            assert sorted(z.namelist()) == sorted([f"{i:02d}.png" for i in range(1, 9)] + ["main.png", "tab.png"])
        pack = json.loads((proj / "pack.json").read_text(encoding="utf-8"))
        assert [s["word"] for s in pack["stickers"]] == words, pack["stickers"]
        if animated:
            sys.path.insert(0, str(S))
            from line_export import _apng_timing
            nf, per, plays = _apng_timing(proj / "submit_line_animated" / "stickers" / "01.png")
            assert 5 <= nf <= 20 and 1 <= plays <= 4 and per * plays <= 4000, (nf, per, plays)
            print(f"PASS GIF→LINE animated: {nf}f {per}ms×{plays}={per*plays}ms, flat ZIP, words kept")
        else:
            im = Image.open(proj / "submit_line" / "stickers" / "01.png")
            assert im.size == (370, 320) and im.convert("RGBA").getchannel("A").getextrema()[0] == 0
            print("PASS GIF→LINE static: 370x320 transparent PNG, flat ZIP, words kept")

    # wrong count rejected by the bridge (7 GIFs)
    gifs[-1].unlink()
    r = run(S / "gif_to_line.py", td / "line_bad", out, "--name", "x", "--creator", "y", ok=False)
    assert r.returncode != 0 and "must have one of" in (r.stdout + r.stderr)
    print("PASS bridge rejects 7 stickers")


def test_vendor_review_suite():
    r = subprocess.run([sys.executable, "-m", "unittest", "-q", str(ROOT / "vendor/pixel_gif/tests/test_review_gif.py")],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stdout + r.stderr
    print("PASS vendored review_gif unit tests")


def test_portability():
    import re
    bad = []
    for f in [ROOT / "SKILL.md", *ROOT.glob("references/*.md"), *ROOT.glob("vendor/pixel_gif/references/*.md"), *ROOT.glob("scripts/*.py")]:
        t = f.read_text(encoding="utf-8")
        if re.search(r"/workspace/|/home/box|agent-data", t):
            bad.append(f.name)
        if re.search(r"exactly 1, 2, 3,? or 4 seconds|剛好 ?1、2、3", t):
            bad.append(f.name + " (wrong 1/2/3/4s rule)")
    assert not bad, bad
    print("PASS no box-specific paths or wrong LINE duration rule in skill/docs/scripts")


def main():
    test_vendor_review_suite()
    test_portability()
    with tempfile.TemporaryDirectory(prefix="unified-") as td:
        td = Path(td)
        good = test_atlas_check(td)
        test_end_to_end(td, good)
    print("ALL UNIFIED TESTS PASSED")


if __name__ == "__main__":
    main()
