# 上架 LINE Creators Market

规范以[静态贴图](https://creator.line.me/zh-hant/guideline/sticker/)与[动态贴图](https://creator.line.me/zh-hant/guideline/animationsticker/)为准，平台会更新。下面是 2026-11-06 核对的版本。

## 步骤

1. 打开 [creator.line.me](https://creator.line.me/zh-hant/) 用 LINE 账号注册创作者。
2. 建立贴图组，选择静态或动态、张数（送审后张数不能改）。
3. 上传 `line_submit.zip`（或 `line_animated_submit.zip`）里的文件，文案照 `LINE上架文案.md` / `manifest.json` 填。
4. 若用 AI 生成，后台须勾选 AI 使用声明；不要仿知名角色或用他人照片。
5. 送审。通过后点开始贩售。无预先上架费。

## 静态规格

| 素材 | 数量 | 格式 | 尺寸 | 大小 |
|---|---|---|---|---|
| 贴图 | 8 / 16 / 24 / 32 / 40 | PNG 透明底 | ≤370×320，宽高偶数 | ≤1MB / 张 |
| 主图 main | 1 | PNG | 240×240 | ≤1MB |
| 聊天标签 tab | 1 | PNG | 96×74 | ≤1MB |
| 整包 ZIP | 1 | ZIP | — | ≤60MB |

内容与裁切边缘约留 10px 边距。

## 动态规格（APNG）

| 素材 | 数量 | 格式 | 尺寸 | 大小 |
|---|---|---|---|---|
| 贴图 | 8 / 16 / 24 | APNG（扩展名 `.png`） | ≤320×270，且宽或高 ≥270 | ≤1MB / 张 |
| 主图 main | 1 | APNG `.png` | 240×240 | ≤1MB |
| 聊天标签 tab | 1 | **静态** PNG | 96×74 | ≤1MB |
| 整包 ZIP | 1 | ZIP | — | ≤60MB |

每张：5–20 帧；总时长 1–4 秒；循环 1–4 次；全帧相同会被拒。

## 文案字数

| 字段 | 上限 |
|---|---|
| 贴图名称 | 40 |
| 作者 | 50 |
| 介绍 | 160 |
| 版权 | 50 |

部分语系亚洲字符按 2 字计，过长时自行缩短。

## 收入（摘要，以官网为准）

标价先扣平台约 30%，再与 LINE 对半，创作者大约拿标价 35%，另扣日本预扣税与收款手续费。最低标价与汇款门槛以 Creators Market 后台为准。

## 本工具用法

```bash
# 静态
python3 scripts/sticker.py build 项目目录 --target line
python3 scripts/sticker.py check 项目目录 --target line

# 动态 APNG
python3 scripts/sticker.py build 项目目录 --target line --animated
python3 scripts/sticker.py check 项目目录 --target line --animated
```

产物：`submit_line/` 或 `submit_line_animated/`、`line_submit.zip` / `line_animated_submit.zip`、`LINE上架文案.md`。
微信流程不变，默认 `--target wechat`。
