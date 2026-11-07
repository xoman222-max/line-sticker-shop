---
name: LINE Sticker Studio
description: 角色貼圖一站式工作室：從角色參考圖或使用者既有圖，規劃不重複的姿勢與文案，選畫風（像素/插畫/照片）與動作方式（輕動效/連續動作），用安全間距的圖集合成固定字幕 GIF 預覽，再轉成 LINE Creators Market 靜態 PNG 或動態 APNG 上傳 ZIP 並依官方規格檢查；也含微信舊流程與吉祥物品牌短片附錄。用於「做貼圖」「LINE 貼圖/動態貼圖」「表情包」「GIF 貼圖」「上架 LINE」。不代替使用者註冊、送審或付款；不做未授權 IP；不支援 LINE 表情貼（emoji）。
---

# LINE Sticker Studio

一份角色參考 → 一套形象一致、每張姿勢不同的貼圖 → GIF 預覽 + LINE 上傳 ZIP。
本檔所在目錄稱為 `$SKILL`（`SKILL=<含本 SKILL.md 的目錄>`）；以下路徑都相對於它。需要 Python 3.9+、Pillow；MP4 預覽另需 FFmpeg。合成、轉檔、檢查全離線，不呼叫任何付費 API。

| 位置 | 內容 |
|---|---|
| `scripts/gif_to_line.py` | 橋接：GIF / PNG / 逐幀資料夾 → LINE 專案 → build → check |
| `scripts/atlas_check.py` | 圖集安全檢查：空格、貼邊（頭頂被裁）、間隔溝有墨 |
| `scripts/sticker.py`、`scripts/line_export.py` | LINE 匯出與檢查（`--platform line [--animated]`）；微信舊流程 |
| `vendor/pixel_gif/scripts/` | 合成器：`export_pack.py`（輕動效）、`export_pixel_actions.py`、`export_keyframes.py`、`review_gif.py` |
| `vendor/pixel_gif/references/` | 畫風、輕動效、關鍵影格、像素動作、穩定度、清晰度、manifest、品牌短片 |
| `references/` | `line.md`（官方規格與出處）、`ideation.md`、`writing.md`、`legacy-ray-workflow.md`（微信）、`wechat.md`、`custom-order.md` |

## 1. 權利與來源（不可跳過）

只用使用者原創角色、自家寵物、本人或已同意的成年人（做成明顯卡通）、或客戶能證明有權的素材。不做名人、影視動漫遊戲角色、他人畫作或二創；未成年人照片不做上架。
在專案 `notes.md` 記：參考圖來源、授權說明、身分錨點（輪廓、臉部特徵、配色、招牌配件）、是否用 AI 生成（LINE 後台須聲明）。

## 2. 規劃

- 確認：平台（LINE 靜態 8/16/24/32/40、LINE 動態 8/16/24、或只要 GIF）、張數、語言、文案。能從上下文確定就不再問。
- 需要新企劃或「用資料想點子」時讀 `references/ideation.md`；一般選句讀 `references/writing.md`。
- 每張 = 短句 + **互不相同的姿勢/道具** + 一個動作節拍。只換字不換姿勢算重複。
- 畫風與動作分開選（題材不決定動作方式）：
  - 畫風：像素 / 清透插畫 / 照片 → `vendor/pixel_gif/references/appearance.md`
  - **輕動效**：每張一個姿勢，加點頭、彈跳、搖擺、擠壓、小符號 → `light-motion.md`，合成器 `export_pack.py`
  - **連續動作**：依序畫出臉、頭、肩、軀幹、四肢協調的多個姿勢 → 像素 `pixel-actions.md` + `export_pixel_actions.py`；插畫/照片 `keyframes.md` + `export_keyframes.py`；每次新動作先讀 `stability.md`。只轉一隻手不算。動作失敗時不可默默改成輕動效。
- 已認可的樣本 + 「擴充」= 沿用畫風、動作強度與設定。

## 3. 出圖

用宿主自己的生圖能力（例如 Grok Bot 的 GenerateImage），或使用者提供的現成圖。不要求 OpenAI 金鑰；`sticker.py gen` 僅屬微信舊流程，且需使用者明確同意付費。

- 一次一張透明圖集（常用 4×4），**寬間隔溝**、每格**頭頂留白**、圖上不放字（字幕由合成器加，才能檢查錯字）。寫清閱讀順序與身分錨點。
- 每張圖集先跑：`python3 "$SKILL/scripts/atlas_check.py" atlas.png --grid 4 4`。FAIL（貼邊 ≤1px，多半被裁）必須重做或加 `crop`；WARN 要人看。再以原尺寸目視：格數、格→姿勢對應、換位、手髮被切、溝內殘影。

## 4. 合成 GIF（預覽與通用交付）

```bash
FONT=<含所有字幕字形的字型檔>   # 例：NotoSansCJK-Bold.ttc；TTC 用 --font-index 選字面
python3 "$SKILL/vendor/pixel_gif/scripts/export_pack.py" manifest.json out --font "$FONT" --preview
```

manifest 格式見 `vendor/pixel_gif/references/manifest.md`（`atlas` 路徑相對 manifest、`cell` 從 0 起算、`out` 必須是空資料夾）。預設 HD 512×512；`"render_style": "pixel"` 才走 320×320 像素路徑。字幕固定不隨動作擠壓。
GIF 預設約 2 秒、**無限循環**——這是聊天 GIF 用，不是 LINE 規格。

視覺檢查（逐幀、原尺寸、循環接縫）：

```bash
python3 "$SKILL/vendor/pixel_gif/scripts/review_gif.py" extract out/<組>/001-xxx.gif review/001
```

幀數、雜湊、ZIP 有效只是技術檢查，不等於視覺驗收；助理自評與使用者認可分開記錄。

## 5. 轉 LINE 並檢查

```bash
# 動態 APNG（8/16/24 張）
python3 "$SKILL/scripts/gif_to_line.py" line_proj out --name "貼圖名稱" --creator "作者" --animated --loops 2
# 靜態 PNG（8/16/24/32/40 張；預設取每張 GIF 第一幀，--still-frame middle|last 可改）
python3 "$SKILL/scripts/gif_to_line.py" line_proj_static out --name "貼圖名稱" --creator "作者"
```

輸入可為 GIF、PNG、逐幀 PNG 資料夾或含它們的目錄（依檔名排序，`001-收到.gif` 的「收到」成為含義詞）。可加 `--cover`、`--icon` 指定主圖與標籤圖。也可直接手放 `sheets/NN.png`、`frames_raw/NN/*.png`、`stickers_raw/NN.png` 後執行 `python3 "$SKILL/scripts/sticker.py" build|check 專案 --platform line [--animated]`。

LINE 動態規格（2026-11-07 依官方頁核對，詳見 `references/line.md`）：每張 5–20 幀、1–4 次循環，**一次循環時長 × 次數 ≤ 4 秒**；官方未規定最短時長，也沒有「必須剛好 1/2/3/4 秒」。≤320×270 且寬或高 ≥270；每檔 ≤1MB；main 240×240 APNG；tab 96×74 靜態 PNG；APNG 第一幀是商店靜態圖。靜態：≤370×320 偶數尺寸、透明背景、≤1MB、main 240×240、tab 96×74。ZIP ≤60MB，扁平 `01.png…`、`main.png`、`tab.png`。
轉換會把 20 幀以上取樣、把 GIF 的無限循環改為有限次數並壓進 4 秒。`check` 的 FAIL 必須清零；WARN（約 10px 邊距、RGB、奇數尺寸）要人看。**本地通過不代表 LINE 審核通過。**

LINE 表情貼（emoji）、動態表情貼、大貼圖、訊息貼圖等規格不同，本技能不支援；需要時先查官方規範再另做。

## 6. 交付與回報

列出實際檔案路徑、畫風＋動作方式、張數、已執行的檢查與結果、已知視覺限制、待使用者認可項目。附代表性 GIF 或預覽 MP4。原始圖集不放進分享 ZIP，除非被要求。註冊、送審、定價、販售由使用者本人在 creator.line.me 操作。

## 附錄

- **微信表情開放平台**（上游原流程）：`references/legacy-ray-workflow.md`、`references/wechat.md`；`sticker.py build|check 專案`（不加 `--platform` 時預設即微信）。
- **吉祥物品牌短片**（僅在被要求時）：`vendor/pixel_gif/references/brand-film.md`；不套貼圖畫布與循環時長。
- **定制接單**：`references/custom-order.md`。

授權：根目錄 `LICENSE`（MIT, Ray Wang，ray-sticker-shop 上游）；`vendor/pixel_gif/LICENSE`（MIT, WoYun520）。本 fork 新增部分同為 MIT。
