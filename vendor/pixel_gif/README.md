# vendor/pixel_gif

Vendored from [WoYun520/pixel-gif-sticker-pack](https://github.com/WoYun520/pixel-gif-sticker-pack) (MIT, Copyright 2026 WoYun520; see `LICENSE` here) as adapted in the Grok Bot `pixel-gif-sticker-pack` skill.
Scripts are unmodified and import each other as siblings, so run them by path: `python3 vendor/pixel_gif/scripts/<name>.py`.

| Script | Purpose |
|---|---|
| `export_pack.py manifest.json OUT --font F` | light-motion GIFs from an atlas (fixed captions, HD 512 / pixel 320) |
| `export_pixel_actions.py manifest.json OUT --font F` | pixel consecutive actions |
| `export_keyframes.py manifest.json OUT --font F` | HD consecutive actions from key poses |
| `review_gif.py extract GIF OUT` / `check AUDIT REVIEW` | native-frame review sheet bound to the GIF hash |

References: `references/` (appearance, light-motion, keyframes, pixel-actions, stability, clarity, manifest, brand-film).
