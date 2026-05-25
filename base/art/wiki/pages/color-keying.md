---
title: Post-Processing - Color Keying vs rembg
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [sprite-pipeline, post-process, alpha-transparency, background-removal, color-key]
sources: [comfyui_workflow/DEBUG_LESSONS.md]
confidence: high
---

# Color Keying for UI Assets

## Why rembg Fails on UI Elements

rembg (ISNet/U2Net) is trained on natural images (people, animals, objects
vs backgrounds). It fails on "geometric UI element + similar-toned background":

- Light-colored button fill on white background → rembg removes the fill
- Amber button on warm cream background → rembg removes the button

## HSV Color Key (Recommended)

Custom algorithm that reliably separates UI content from generated backgrounds:

```
background_mask = (min_rgb > threshold) AND (max_rgb - min_rgb <= 25)
```

The spread check (max-min ≤ 25) is the key insight:
- Amber gold RGB(255,179,0) → spread=255 → NOT background (correct)
- White background RGB(252,251,253) → spread=2 → IS background (correct)

## Standard Pipeline

```
1. Generate at large size (640×384 for buttons)
2. smart_color_key() → transparent background
3. trim_to_alpha() → crop to content bounding box
4. pad_to_canvas(target_w, target_h) → centered on standard canvas
5. Output: deterministic size, RGBA, ready for Unity
```

All assets standardize to power-of-two canvas (e.g. 256×128) for optimal
Unity sprite atlas packing.

See also: [[controlnet-guide]], [[flux-priors]]
