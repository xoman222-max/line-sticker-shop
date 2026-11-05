# line-sticker-shop（表情包工坊 · 微信 + LINE）

Fork of [imraywang/ray-sticker-shop](https://github.com/imraywang/ray-sticker-shop)（MIT，Copyright 2026 Ray Wang）。

一张照片或角色图，生成一整套形象一致的表情包，并打包成：

- **微信**表情开放平台投稿素材（原版流程，默认）
- **LINE Creators Market** 静态 PNG 或动态 APNG 投稿包（本 fork 新增）

## 安装

```bash
git clone https://github.com/xoman222-max/line-sticker-shop ~/.claude/skills/line-sticker-shop
# 或任意目录
pip install pillow   # Python 3.9+
```

对 Agent 说：「把这张猫的照片做成一套 LINE 贴图。」或「做成微信表情包。」

## 需要什么

- Python 3.9+ 和 Pillow：`pip install pillow`
- `OPENAI_API_KEY`（中转站再设 `OPENAI_BASE_URL`）——只在 `character` / `gen` 出图时需要
- 没有 key 也行：`prompts` 拿提示词，到 ChatGPT 出图放回 `sheets/`，再 `build`

## 用法摘要

```bash
# 1) 角色图（可选）
python3 scripts/sticker.py character --photo photo.jpg --out project/character.png

# 2) 写 pack.json（微信例：references/pack.example.json；LINE 例：references/pack.line.example.json）

# 3) 生成精灵图（要 API key；或用 prompts 手动出图）
python3 scripts/sticker.py gen project --dry-run
python3 scripts/sticker.py gen project

# 4a) 微信投稿包（默认）
python3 scripts/sticker.py build project
python3 scripts/sticker.py check project

# 4b) LINE 静态贴图（8/16/24/32/40 张）
python3 scripts/sticker.py build project --target line
python3 scripts/sticker.py check project --target line
# 产物：submit_line/、line_submit.zip、LINE上架文案.md

# 4c) LINE 动态贴图 APNG（8/16/24 张）
python3 scripts/sticker.py build project --target line --animated
python3 scripts/sticker.py check project --target line --animated
# 产物：submit_line_animated/、line_animated_submit.zip
```

LINE 规格与上架步骤见 [references/line.md](references/line.md)。微信见 [references/wechat.md](references/wechat.md)。

## 花费

出图费用与上游相同：8 张表情加配套素材，按 OpenAI 官方单价约 $0.7，重抽另算（未在本仓库实测定价）。`build` / `check` 本身不呼叫付费 API。

## 测试

不调用任何付费 API。用 Pillow 合成假精灵图跑 LINE 打包与校验：

```bash
python3 tests/test_line_build.py
```

## 注意

- 只做你有权使用的形象。LINE / 微信都不收未授权的二创和同人；AI 图须按平台要求声明。
- 过审与收入由平台决定，本工具不保证。
- 本仓库是 fork，上游微信流程尽量保持兼容；LINE 导出是新增 `--target line`，默认行为仍是微信。

## License

MIT（继承上游）。新增 LINE 导出代码同样按 MIT 授权。
