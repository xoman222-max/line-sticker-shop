# 上架 LINE Creators Market（贴图 Stickers；不含表情贴 Emoji / 动态表情贴）

官方规范（2026-11-07 核对，平台会更新，以官网为准）：

- 静态贴图：https://creator.line.me/en/guideline/sticker/ （[繁中](https://creator.line.me/zh-hant/guideline/sticker/)）
- 动态贴图：https://creator.line.me/en/guideline/animationsticker/ （[繁中](https://creator.line.me/zh-hant/guideline/animationsticker/)）
- ZIP 命名：LINE Creators Market Sales Manual — 「Only stickers with the proper file names will be processed correctly」https://static.line.naver.jp/line_creators_market/img/CMS/pdf/SalesManual_EN_1.5.0.pdf

## 步骤

1. 在 [creator.line.me](https://creator.line.me/) 用 LINE 账号注册创作者（用户本人操作）。
2. 建立贴图组，选静态或动态与张数（送审前可改）。
3. 「ZIP 上传」`line_submit.zip` / `line_animated_submit.zip`；文案照 `LINE上架文案.md` / `manifest.json` 填。
4. 用 AI 生成须在后台声明；不仿知名角色、不用他人照片。
5. 送审。本工具的检查不等于审核通过。

## 静态规格（`check` 中为 FAIL 的硬规则）

| 素材 | 数量 | 规格 | 大小 |
|---|---|---|---|
| 贴图 01.png… | 8/16/24/32/40 | PNG，透明背景，最大 370×320，宽高**偶数** | ≤1MB/张 |
| main.png | 1 | PNG 240×240 | ≤1MB |
| tab.png | 1 | PNG 96×74 | ≤1MB |
| ZIP | 1 | 扁平：01.png…、main.png、tab.png | ≤60MB |

WARN：内容距边约 10px（官方「around 10 pixels」）、RGB 色彩模式、72dpi。

## 动态规格（APNG，扩展名 `.png`）

| 素材 | 数量 | 规格 |
|---|---|---|
| 贴图 01.png… | 8/16/24 | APNG，透明背景，≤320×270 且宽或高 ≥270；5–20 帧；≤1MB |
| main.png | 1 | APNG 240×240 |
| tab.png | 1 | **静态** PNG 96×74（播放符号由 LINE 自动加，别自己画） |
| ZIP | 1 | 扁平，≤60MB |

**时长**：官方写「Loops: 1–4 loops per sticker whose combined length does not exceed 4 seconds」与「Playback time: Up to 4 seconds per sticker」。
即「一次循环时长 × 循环次数 ≤ 4 秒」（例：1.92 秒 × 2 次 = 3.84 秒 OK；× 3 次 = 5.76 秒 FAIL）。官方没有写最短时长，本工具不强制。
循环 0（无限）FAIL。全帧相同 FAIL（官方：会上传错误）。APNG 第一帧会作为商店静态图——第一帧空白 WARN。
动态贴图官方未要求偶数尺寸，奇数仅 WARN（工具产出一律偶数）。

`check` 直接解析 APNG 的 acTL（帧数、循环次数）与 fcTL（每帧延迟、帧区域），不只依赖 Pillow。

## 文案字数（亚洲文字与部分符号算 2 字，`check` 按此计算）

| 字段 | 上限 |
|---|---|
| 贴图名称 | 40 |
| 作者 | 50 |
| 介绍 | 160 |
| 版权 | 50 |

## 本工具用法

```bash
python3 scripts/sticker.py build 项目目录 --platform line [--animated]
python3 scripts/sticker.py check 项目目录 --platform line [--animated]
```

`--platform` 与 `--target` 等价。未指定时仍是上游微信流程（GIF），两者输出目录与 ZIP 名称完全分开。
