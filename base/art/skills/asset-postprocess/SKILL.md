---
name: asset-postprocess
description: "Standardize generated images for game engine deployment."
version: 1.0.0
created_by: human
tags: [post-process, color-key, trim, pad, alpha]
---

# Asset Post-Processing Skill

Standardize raw Flux/SD output into engine-ready sprites with deterministic
size, transparent background, and correct alpha channel.

## When to Use

After any image generation, before deploying to Unity/game engine.

## Procedure

```
[1] smart_color_key()     — remove background (HSV-based, not rembg)
[2] feather_alpha_edge()  — smooth alpha edges
[3] trim_to_alpha()       — crop to content bounding box
[4] pad_to_canvas(w, h)   — center on target canvas size
[5] save as RGBA PNG       — ready for engine import
```

## Color Key Algorithm

```python
bg_mask = (min_rgb > threshold) AND (max_rgb - min_rgb <= 25)
```

The spread check (max-min ≤ 25) distinguishes saturated fills from
neutral backgrounds:
- Amber RGB(255,179,0) → spread=255 → content (keep)
- White RGB(252,251,253) → spread=2 → background (remove)

## Standard Canvas Sizes

| Asset Type | Gen Size | Final Canvas | Ratio |
|---|---|---|---|
| Button | 640×384 | 256×128 | 2:1 |
| Icon | 512×512 | 128×128 | 1:1 |
| Character | 512×512 | 256×256 | 1:1 |
| Card | 384×512 | 256×384 | 2:3 |
| Background | 1920×1088 | 1920×1088 | ~16:9 |

Generate at larger size for stability, then shrink to standard canvas.
All final sizes are power-of-two for optimal sprite atlas packing.

## Pitfalls

- rembg fails on light-colored UI elements — always use HSV color-key
- Aspect ratio must match from generation — 9-slice compensates but
  doesn't fix major ratio mismatches
- Always generate larger than target, never upscale
