# 上游 ray-sticker-shop 流程（微信 GIF + GPT Image 生成，舊版保留）

> 本檔為上游 SKILL.md 原文移入，供微信投稿與 `sticker.py gen` 使用。LINE 製作請回到根目錄 SKILL.md；文中「5b. LINE」一節以根目錄 SKILL.md 與 line.md 為準。

一张图进，一套能上架、能交付的动态表情包出。默认 8 张加 5 张配套素材，按官方单价约 $0.65（约 ¥5，重抽另算），几分钟出完。

## 流程

### 1. 先问清权利，这一步不能跳

确认素材是下面哪一种，不是就停下来说明原因：

- 用户自己的原创角色、自家宠物；
- 用户本人，或已取得本人同意的成年人，而且要做成明显的卡通形象；
- 客户下单提供的素材，客户要能确认有权使用。

不做：明星、影视动漫游戏角色、网络二创形象（如「大肥鱼/鲸鱼娘」，创作者声明过非商用）、别人的画作。微信审核标准明确不收未获授权的二次创作和同人。未成年人肖像也是审核标准禁止的范围，孩子的照片不做投稿，只可以私下给家长自用。

### 2. 定角色

已有干净的角色图，直接用。只有照片时：

```bash
python3 scripts/sticker.py character --photo 照片.jpg --out 项目目录/character.png
```

生成后给用户看一眼，确认像了再往下走。这张图是整套一致性的锚，不满意就重抽。

### 3. 写 pack.json

在项目目录写 `pack.json`，格式见 [pack.example.json](pack.example.json)。写之前读 [选题和文案](writing.md)。

要点：每张一句聊天高频话，每张绑不同的动作和姿势。只换字不换动作，审核会判差异不足。含义词 ≤4 字，名称 ≤8 字。

把 8 句话给用户过一遍，定了再生成。

### 4. 生成

先报价：

```bash
python3 scripts/sticker.py gen 项目目录 --dry-run
```

把预估花费告诉用户，同意后去掉 `--dry-run`。失败的重跑只补缺的。想重抽某几张加 `--redo 3,7`。

需要环境变量 `OPENAI_API_KEY`；走中转站时再设 `OPENAI_BASE_URL`。

**没有 API key：** 跑 `prompts` 拿提示词，到 ChatGPT 或 Codex 里上传角色图出图，文件存进 `sheets/01.png`、`assets_raw/cover.png`……然后接着走第 5 步。

### 5. 合成和检查

```bash
python3 scripts/sticker.py build 项目目录
python3 scripts/sticker.py check 项目目录
```

`check` 的 FAIL 必须清零。然后**亲眼看**：打开 `预览.html`，逐张看配字有没有错字、角色有没有变形、循环有没有跳帧，再切深色背景看有没有白边。不满意就 `gen --redo` 重抽。循环跳一下、又不想重抽时，在 pack.json 那一张加 `"keep_frames": [1, 13]`（只留第 1–13 帧）再 `build`；修图都走这个字段或重抽，不要直接改 GIF，否则下次 `build` 会被覆盖。


### 5b. 若目标是 LINE（本 fork，推荐）

张数必须符合平台：静态 8/16/24/32/40；动态 8/16/24。可参考 [pack.line.example.json](pack.line.example.json)。

素材来源三选一（`build`/`check` 完全离线，不需要任何 API key）：

- `sheets/NN.png`：4×4 精灵图（`gen` 产出，或用 Grok / 其他工具自己出图后放入）；
- `frames_raw/NN/*.png`：已有的逐帧 PNG（按文件名排序，动态用）；
- `stickers_raw/NN.png`：单张透明 PNG（静态用）。

```bash
python3 scripts/sticker.py build 项目目录 --platform line
python3 scripts/sticker.py check 项目目录 --platform line
# 动态 APNG：
python3 scripts/sticker.py build 项目目录 --platform line --animated
python3 scripts/sticker.py check 项目目录 --platform line --animated
```

动态时长：一次循环时长 × 循环次数 ≤ 4 秒；`build` 会先减少循环次数、再缩短帧间隔，自动压进限制。`check` 的 FAIL 是可量测的硬规格，WARN（边距、偶数尺寸、灰阶）要人看；本地通过不代表 LINE 审核通过。

产物：`submit_line/` 或 `submit_line_animated/`、`line_submit.zip` / `line_animated_submit.zip`、`LINE上架文案.md`、`manifest.json`。规格见 [上架 LINE](line.md)。注册和提交仍须用户本人操作；AI 生成须在后台声明。

微信默认流程不变（`--target wechat` 可省略）。

### 6. 交付

产物都在项目目录：

| 文件 | 用途 |
|---|---|
| `submit/` | 投稿素材，按微信字段命名 |
| `上架文案.md` | 名称、介绍、含义词，直接照填 |
| `预览.html`、`预览.png` | 给自己或客户确认 |
| `交付给客户.zip` | 定制单直接发给客户 |
| `costs.jsonl` | 每次调用的实际花费 |

上架步骤和接单做法分别见 [上架微信](wechat.md) 和 [定制接单](custom-order.md)。注册和提交要用户本人实名操作，不要代做。

## 边界

- 不承诺收入和过审。过审由微信或 LINE 决定；微信通常 5 个工作日内反馈，LINE 时限以官网为准。
- 定制单交付前提醒客户：表情归客户自用；要投稿到微信，权利和实名都是投稿人自己的责任。
