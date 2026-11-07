#!/usr/bin/env python3
"""定制表情包流水线：参考图 → 16 帧精灵图 → 微信 GIF 或 LINE PNG/APNG 投稿包。

用法见 SKILL.md。依赖 Python 3.9+ 和 Pillow。
默认 --target wechat；加 --target line 导出 LINE Creators Market 素材，
再加 --animated 则产出 APNG 动态贴图。
"""
import argparse
import base64
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat

from line_export import build_line, check_line

GRID = 4
SHEET = "960x960"
GIF_SIZE = 240
MAX_GIF = 500 * 1024
MAX_ICON = 100 * 1024
# 官方 token 单价（美元），用来记账；走中转站时以中转站账单为准
PRICE = {"text": 5e-6, "image": 8e-6, "out": 30e-6}
BANNED = ["微信", "wechat", "腾讯", "官方", "认证", "正版"]


# ---------- 生成 ----------

def _prompt_sheet(pack, s):
    style = pack.get("style", "").strip()
    caption = (s.get("caption") or "").strip()
    cap = (
        f'Add one big bold hand-lettered caption at the bottom of every cell, identical in every frame, reading exactly: "{caption}". '
        "Give the caption and the character a clean thick white sticker outline. No other text."
        if caption
        else "No text anywhere. Give the character a clean thick white sticker outline."
    )
    return (
        "Use the character in the input image exactly: same face, body shape, colors, clothing and line style. "
        + (f"Style notes: {style}. " if style else "")
        + "Draw a 4x4 animation sprite sheet of one short looping chat-sticker animation: 16 equal square cells, "
        "read left to right, top to bottom, each cell is the next frame. "
        "No grid lines, no borders, no cell numbers, fully transparent background. "
        "Same character size and same ground position in every cell, keep everything fully inside its cell with margin. "
        "Exaggerated, readable facial expression at small size. All shapes solid and crisp: no motion blur, no dust clouds, no semi-transparent effects. The last frame must flow smoothly back to the first. "
        f"Action: {s['action']}. {cap}"
    )


ASSET_PROMPTS = {
    "cover": (
        "1024x1024", "transparent",
        "Use the character in the input image exactly. Clean front-facing half-body portrait, centered, filling the frame, "
        "friendly expression, fully transparent background, no text, no white outline, no border.",
    ),
    "icon": (
        "1024x1024", "transparent",
        "Use the character in the input image exactly. Only the head, front-facing, centered, filling the frame, "
        "simple and bold so it reads at very small size, fully transparent background, no text, no white outline, no border.",
    ),
    "banner": (
        "1504x800", "opaque",
        "Use the character in the input image exactly. A rich, lively wide scene that tells a tiny story about this character, "
        "bright saturated colorful background (never white or near-white), absolutely no text, letters, logos or watermarks.",
    ),
    "reward_guide": (
        "1504x1120", "opaque",
        "Use the character in the input image exactly. The character cutely asks for a little tip, holding out both hands, "
        "bright saturated colorful background (never white or near-white), absolutely no text, letters, logos, QR codes or watermarks.",
    ),
    "reward_thanks": (
        "1024x1024", "opaque",
        "Use the character in the input image exactly. The character bows and blows hearts to say thank you, "
        "bright saturated colorful background (never white or near-white), absolutely no text, letters, logos, QR codes or watermarks.",
    ),
}


def _edit(image_path, prompt, size, background, model, quality, log_path):
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("缺 OPENAI_API_KEY。没有 key 时用 prompts 命令拿提示词，到 ChatGPT 或 Codex 里出图，再跑 build。")
    boundary = uuid.uuid4().hex
    fields = {"model": model, "prompt": prompt, "size": size, "quality": quality, "complexity": "medium", "background": background}
    body = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()
    )
    body += (
        f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="ref.png"\r\nContent-Type: image/png\r\n\r\n'.encode()
        + Path(image_path).read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        f"{base}/images/edits",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise RuntimeError(str(e)) from None
            time.sleep(5 * (attempt + 1))
    u = data.get("usage") or {}
    d = u.get("input_tokens_details") or {}
    cost = u.get("output_tokens", 0) * PRICE["out"] + d.get("image_tokens", 0) * PRICE["image"] + d.get("text_tokens", 0) * PRICE["text"]
    with open(log_path, "a") as f:
        f.write(json.dumps({"size": size, "usage": u, "usd": round(cost, 4)}) + "\n")
    return base64.b64decode(data["data"][0]["b64_json"])


def load_pack(pack_dir):
    p = Path(pack_dir)
    pack = json.loads((p / "pack.json").read_text())
    return p, pack


def cmd_character(a):
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prompt = (
        "Turn the subject of this photo into an original, heavily stylized cute cartoon sticker character: "
        f"{a.style}. Keep the identifying features (hairstyle, glasses, markings, signature clothing or fur pattern). "
        "It must clearly read as a drawing, never photorealistic. Front-facing full body, centered, "
        "fully transparent background, no text, no border."
    )
    log = out.parent / "costs.jsonl"
    out.write_bytes(_edit(a.photo, prompt, "1024x1024", "transparent", a.model, a.quality, log))
    print("角色图：", out)


def _gen_one(job):
    target, ref, prompt, size, bg, model, quality, log = job
    if target.exists():
        return f"跳过（已有）{target.name}"
    target.write_bytes(_edit(ref, prompt, size, bg, model, quality, log))
    return f"完成 {target.name}"


def _jobs(p, pack, model, quality, with_assets, redo=None):
    ref = p / pack["character"]
    if not ref.exists():
        sys.exit(f"找不到角色图 {ref}")
    log = p / "costs.jsonl"
    (p / "sheets").mkdir(exist_ok=True)
    (p / "assets_raw").mkdir(exist_ok=True)
    jobs = []
    for i, s in enumerate(pack["stickers"], 1):
        t = p / "sheets" / f"{i:02d}.png"
        if redo and i in redo and t.exists():
            t.unlink()
        jobs.append((t, ref, _prompt_sheet(pack, s), SHEET, "transparent", model, quality, log))
    if with_assets:
        for name, (size, bg, prompt) in ASSET_PROMPTS.items():
            jobs.append((p / "assets_raw" / f"{name}.png", ref, prompt, size, bg, model, quality, log))
    return jobs


def cmd_gen(a):
    p, pack = load_pack(a.pack)
    redo = {int(x) for x in a.redo.split(",")} if a.redo else None
    jobs = _jobs(p, pack, a.model, a.quality, not a.no_assets, redo)
    todo = [j for j in jobs if not j[0].exists()]
    print(f"要生成 {len(todo)} 张，按官方单价约 ${len(todo) * 0.052:.2f}（重抽另算）")
    if a.dry_run:
        return
    errors = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for j, f in zip(todo, [ex.submit(_gen_one, j) for j in todo]):
            try:
                print(f.result(), flush=True)
            except Exception as e:  # 单张失败不拖垮整套，重跑只补缺的
                errors.append(j[0].name)
                print(f"失败 {j[0].name}: {e}", flush=True)
    if errors:
        print("失败的可以直接重跑 gen，只补缺的：", ", ".join(errors))
    print(f"本目录累计花费约 ${total_cost(p):.2f}")


def total_cost(p):
    log = p / "costs.jsonl"
    if not log.exists():
        return 0.0
    return sum(json.loads(x)["usd"] for x in log.read_text().splitlines() if x.strip())


def cmd_prompts(a):
    """没有 API key 时：打印提示词，用户在 ChatGPT/Codex 出图后放进 sheets/。"""
    p, pack = load_pack(a.pack)
    for i, s in enumerate(pack["stickers"], 1):
        print(f"--- sheets/{i:02d}.png（上传角色图，要 1:1 透明底）---\n{_prompt_sheet(pack, s)}\n")
    for name, (size, _, prompt) in ASSET_PROMPTS.items():
        print(f"--- assets_raw/{name}.png（{size}）---\n{prompt}\n")


# ---------- 合成 ----------

def _slice(sheet_path):
    s = Image.open(sheet_path).convert("RGBA")
    # ChatGPT 里出的图可能不是正方形或不是 960，统一按格切
    w, h = s.width // GRID, s.height // GRID
    frames = [s.crop((x * w, y * h, x * w + w, y * h + h)).resize((GIF_SIZE, GIF_SIZE), Image.LANCZOS) for y in range(GRID) for x in range(GRID)]
    # 内容压到格子边上说明这一格可能被切断
    border = 0
    for y in range(GRID):
        for x in range(GRID):
            c = s.crop((x * w, y * h, x * w + w, y * h + h)).getchannel("A")
            px = c.load()
            edge = sum(px[i, 0] > 128 or px[i, c.height - 1] > 128 for i in range(c.width)) + sum(
                px[0, j] > 128 or px[c.width - 1, j] > 128 for j in range(c.height)
            )
            border = max(border, edge)
    return frames, border


def _encode(frames, path, ms, colors, bg):
    """全局调色板编码。全局调色板让相邻帧的像素能复用，GIF 体积明显更小。"""
    flat = []
    for f in frames:
        base = Image.new("RGBA", f.size, "white")
        base.alpha_composite(f)
        flat.append(base.convert("RGB"))
    strip = Image.new("RGB", (GIF_SIZE * len(flat), GIF_SIZE))
    for i, f in enumerate(flat):
        strip.paste(f, (i * GIF_SIZE, 0))
    pal = strip.quantize(colors=colors - 1 if bg == "transparent" else colors, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    out = []
    for f, rgb in zip(frames, flat):
        q = rgb.quantize(palette=pal, dither=Image.Dither.NONE)
        if bg == "transparent":
            mask = f.getchannel("A").point(lambda a: 255 if a < 128 else 0)
            q.paste(colors - 1, (0, 0), mask)
        out.append(q)
    kw = {"save_all": True, "append_images": out[1:], "duration": ms, "loop": 0, "optimize": False}
    if bg == "transparent":
        kw.update(transparency=colors - 1, disposal=2)
    out[0].save(path, **kw)


def build_gif(sheet, path, ms, bg, keep=None):
    frames, border = _slice(sheet)
    if keep:  # 循环接不上时只留一段帧，写进 pack.json 才不会被下次 build 覆盖
        frames = frames[keep[0] - 1 : keep[1]]
    for frs, dur in ((frames, ms), (frames[::2], ms * 2)):  # 压不下去再抽一半帧
        for colors in (128, 96, 64, 48):
            _encode(frs, path, dur, colors, bg)
            if path.stat().st_size <= MAX_GIF:
                return path.stat().st_size, colors, len(frs), border
    return path.stat().st_size, colors, len(frs), border


def _fit_png(src, size, dst, limit, keep_alpha):
    im = Image.open(src).convert("RGBA")
    if keep_alpha:
        bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if bbox:
            im = im.crop(bbox)
        side = max(im.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        im = square.resize(size, Image.LANCZOS)
        im.save(dst, optimize=True)
    else:
        im = ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS)
        im.save(dst, optimize=True)
        if dst.stat().st_size > limit:
            im.quantize(colors=200).save(dst, optimize=True)


def cmd_build(a):
    p, pack = load_pack(a.pack)
    target = getattr(a, "target", "wechat")
    animated = getattr(a, "animated", False)
    if target == "line":
        build_line(p, pack, animated=animated)
        return
    if animated:
        sys.exit("--animated 只适用于 --target line")
    sub = p / "submit"
    gifs = sub / "表情图"
    gifs.mkdir(parents=True, exist_ok=True)
    ms = pack.get("frame_ms", 120)
    bg = pack.get("background", "transparent")
    rows = []
    for i, s in enumerate(pack["stickers"], 1):
        sheet = p / "sheets" / f"{i:02d}.png"
        if not sheet.exists():
            print(f"缺 {sheet.name}，先跑 gen 或把图放进 sheets/")
            continue
        size, colors, n, border = build_gif(sheet, gifs / f"{i:02d}.gif", ms, bg, s.get("keep_frames"))
        flag = "  ⚠ 内容压到格子边，重点看这张" if border > 8 else ""
        print(f"{i:02d} {s['word']}: {size // 1024}KB {n}帧 {colors}色{flag}")
        rows.append(gifs / f"{i:02d}.gif")
    raw = p / "assets_raw"
    specs = [
        ("cover", (240, 240), "封面图.png", 500, True),
        ("icon", (50, 50), "聊天面板图标.png", 100, True),
        ("banner", (750, 400), "详情页横幅.png", 500, False),
        ("reward_guide", (750, 560), "赞赏引导图.png", 500, False),
        ("reward_thanks", (750, 750), "赞赏致谢图.png", 500, False),
    ]
    for name, size, fn, kb, alpha in specs:
        if (raw / f"{name}.png").exists():
            _fit_png(raw / f"{name}.png", size, sub / fn, kb * 1024, alpha)
    _contact_sheet(rows, pack, p / "预览.png")
    _preview_html(pack, p)
    _listing(pack, p)
    with zipfile.ZipFile(p / "交付给客户.zip", "w", zipfile.ZIP_STORED) as z:
        for g in rows:
            z.write(g, f"{pack['stickers'][int(g.stem) - 1]['word']}.gif")
    print("输出：", sub, "；预览.png / 预览.html / 上架文案.md / 交付给客户.zip")


def _contact_sheet(gifs, pack, dst):
    if not gifs:
        return
    cols = min(4, len(gifs))
    rows = (len(gifs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * GIF_SIZE, rows * GIF_SIZE), "#e9ecef")
    for i, g in enumerate(gifs):
        im = Image.open(g)
        im.seek(im.n_frames // 2)
        fr = im.convert("RGBA")
        sheet.paste(fr, ((i % cols) * GIF_SIZE, (i // cols) * GIF_SIZE), fr)
    sheet.save(dst)


def _preview_html(pack, p):
    cells = "".join(
        f'<figure><img src="submit/表情图/{i:02d}.gif"><figcaption>{s["word"]}</figcaption></figure>'
        for i, s in enumerate(pack["stickers"], 1)
    )
    (p / "预览.html").write_text(
        f"""<!doctype html><meta charset="utf-8"><title>{pack.get('name','表情包')}</title>
<style>body{{font:14px -apple-system,sans-serif;margin:24px;background:#ededed}}main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:16px}}
figure{{margin:0;text-align:center}}img{{width:120px;height:120px;background:#fff;border-radius:8px}}
.dark img{{background:#191919}}button{{margin-bottom:16px}}</style>
<h2>{pack.get('name','')}</h2><button onclick="document.body.classList.toggle('dark')">切换深色聊天背景</button>
<main>{cells}</main>""",
        encoding="utf-8",
    )


def _listing(pack, p):
    lines = [
        f"# {pack.get('name','')} 上架文案\n",
        f"- 表情名称：{pack.get('name','')}",
        f"- 表情介绍：{pack.get('intro','')}",
        f"- 版权信息：{pack.get('copyright','')}",
        f"- 赞赏引导语：{pack.get('reward_line','')}\n",
        "| 序号 | 含义词 |",
        "|---|---|",
    ]
    lines += [f"| {i:02d} | {s['word']} |" for i, s in enumerate(pack["stickers"], 1)]
    (p / "上架文案.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- 检查 ----------

def _dhash(im):
    g = im.convert("L").resize((9, 8), Image.LANCZOS)
    px = g.load()
    return sum(1 << (x + y * 8) for y in range(8) for x in range(8) if px[x, y] > px[x + 1, y])


def _flat_frame(im, n):
    im.seek(n)
    fr = im.convert("RGBA")
    base = Image.new("RGBA", fr.size, "white")
    base.alpha_composite(fr)
    return base.convert("RGB")


def _chars(s):
    return len(s)


def cmd_check(a):
    p, pack = load_pack(a.pack)
    target = getattr(a, "target", "wechat")
    animated = getattr(a, "animated", False)
    if target == "line":
        code = check_line(p, pack, animated=animated)
        sys.exit(code)
    if animated:
        sys.exit("--animated 只适用于 --target line")
    sub = p / "submit"
    fails, warns = [], []
    F = fails.append
    W = warns.append

    name, intro, cr, line = pack.get("name", ""), pack.get("intro", ""), pack.get("copyright", ""), pack.get("reward_line", "")
    if not 1 <= _chars(name) <= 8 or re.search(r"[\s，。！？、,.!?]", name):
        F(f"表情名称要 1–8 字、无标点无空格：{name!r}")
    if _chars(intro) > 80:
        F(f"表情介绍超过 80 字：{_chars(intro)}")
    if _chars(cr) > 10:
        F(f"版权信息超过 10 字：{cr!r}")
    if line and not 5 <= _chars(line) <= 15:
        F(f"赞赏引导语要 5–15 字：{line!r}")
    for field, text in (("名称", name), ("介绍", intro), ("引导语", line)):
        for b in BANNED:
            if b.lower() in text.lower():
                F(f"{field}里有「{b}」，容易被驳回")

    stickers = pack["stickers"]
    if not 8 <= len(stickers) <= 24:
        F(f"一套要 8–24 张，现在 {len(stickers)} 张")
    words = [s["word"] for s in stickers]
    for w in words:
        if _chars(w) > 4 or re.search(r"[^\w]", w):
            F(f"含义词要 ≤4 字、不带符号：{w!r}")
    for w in {x for x in words if words.count(x) > 1}:
        F(f"含义词重复：{w}")
    for s in stickers:
        for b in BANNED:
            if b.lower() in (s.get("caption") or "").lower():
                F(f"配字里有「{b}」：{s['caption']}")

    hashes = []
    for i, s in enumerate(stickers, 1):
        g = sub / "表情图" / f"{i:02d}.gif"
        tag = f"{i:02d} {s['word']}"
        if not g.exists():
            F(f"{tag} 缺 GIF")
            continue
        im = Image.open(g)
        if im.size != (240, 240):
            F(f"{tag} 尺寸 {im.size}")
        kb = g.stat().st_size / 1024
        if kb > 500:
            F(f"{tag} 体积 {kb:.0f}KB 超 500KB")
        if getattr(im, "n_frames", 1) < 2:
            F(f"{tag} 不是动图")
            continue
        if im.info.get("loop") != 0:
            F(f"{tag} 没设无限循环")
        n = im.n_frames
        first, mid = _flat_frame(im, 0), _flat_frame(im, n // 2)
        diff = ImageStat.Stat(ImageChops.difference(first, mid).convert("L")).mean[0]
        if diff < 1.0:
            W(f"{tag} 动作太小（帧差 {diff:.1f}），可能看着不动")
        last = _flat_frame(im, n - 1)
        if ImageStat.Stat(ImageChops.difference(first, last).convert("L")).mean[0] > 18:
            W(f"{tag} 首尾帧差别大，循环可能跳一下")
        hashes.append((tag, _dhash(mid)))
    for x in range(len(hashes)):
        for y in range(x + 1, len(hashes)):
            d = bin(hashes[x][1] ^ hashes[y][1]).count("1")
            if d < 6:
                W(f"{hashes[x][0]} 和 {hashes[y][0]} 太像（距离 {d}），官方要求差异足够")

    for fn, size, kb, alpha in (
        ("封面图.png", (240, 240), 500, True),
        ("聊天面板图标.png", (50, 50), 100, True),
        ("详情页横幅.png", (750, 400), 500, False),
    ):
        f = sub / fn
        if not f.exists():
            F(f"缺 {fn}")
            continue
        _check_img(f, fn, size, kb, alpha, F, W)
    for fn, size in (("赞赏引导图.png", (750, 560)), ("赞赏致谢图.png", (750, 750))):
        f = sub / fn
        if f.exists():
            _check_img(f, fn, size, 500, False, F, W)
        elif line:
            F(f"写了赞赏引导语但缺 {fn}")

    for x in warns:
        print("WARN", x)
    for x in fails:
        print("FAIL", x)
    print(f"结果：{len(fails)} 个必须改，{len(warns)} 个要人看。")
    print("机器看不了的，交给人：配字有没有错别字、角色有没有变形、横幅有没有文字、权利是否清楚。")
    sys.exit(min(len(fails), 100))


def _check_img(f, fn, size, kb, alpha, F, W):
    im = Image.open(f)
    if im.size != size:
        F(f"{fn} 尺寸 {im.size}，要 {size}")
    if f.stat().st_size > kb * 1024:
        F(f"{fn} 超过 {kb}KB")
    rgba = im.convert("RGBA")
    lo = rgba.getchannel("A").getextrema()[0]
    if alpha and lo > 8:
        F(f"{fn} 要透明背景")
    if not alpha:
        if lo < 250:
            F(f"{fn} 不能用透明背景")
        if min(ImageStat.Stat(rgba.convert("RGB")).mean) > 235:
            W(f"{fn} 背景太接近白色")


# ---------- 入口 ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    c = sp.add_parser("character", help="照片变卡通角色图")
    c.add_argument("--photo", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--style", default="cute chibi, two-head-tall, thick clean dark outlines, flat soft colors")
    c.add_argument("--model", default="gpt-image-2.6-sunburst")
    c.add_argument("--quality", default="medium")
    c.set_defaults(fn=cmd_character)

    g = sp.add_parser("gen", help="生成精灵图和配套素材，已有的自动跳过")
    g.add_argument("pack")
    g.add_argument("--model", default="gpt-image-2.6-flare")
    g.add_argument("--quality", default="medium")
    g.add_argument("--jobs", type=int, default=4)
    g.add_argument("--redo", help="重抽这几张，如 3,7")
    g.add_argument("--no-assets", action="store_true")
    g.add_argument("--dry-run", action="store_true", help="只报数量和预估花费")
    g.set_defaults(fn=cmd_gen)

    pr = sp.add_parser("prompts", help="打印提示词，给没有 API key 的人")
    pr.add_argument("pack")
    pr.set_defaults(fn=cmd_prompts)

    for name, fn, h in (
        ("build", cmd_build, "切帧、合图、出投稿包（微信 GIF 或 LINE PNG/APNG）"),
        ("check", cmd_check, "按微信或 LINE 规范检查"),
    ):
        s = sp.add_parser(name, help=h)
        s.add_argument("pack")
        s.add_argument("--target", "--platform", dest="target", choices=("wechat", "line"), default="wechat",
                       help="投稿平台：line（LINE Creators Market）或 wechat（默认，沿用上游）")
        s.add_argument("--animated", action="store_true", help="LINE 动态贴图（APNG）；仅 --target line")
        s.set_defaults(fn=fn)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
