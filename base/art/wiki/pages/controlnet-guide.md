---
title: ControlNet for UI Asset Generation
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [sprite-pipeline, generation, shape-control, controlnet, mask]
sources: [comfyui_workflow/DEBUG_LESSONS.md]
confidence: high
---

# ControlNet for UI Assets

## Core Insight

ControlNet mask is not just "shape constraint" — it is a **visual content
template**. The mask's appearance directly determines the output's appearance.

| Mask Type | Flux Interpretation | Result |
|---|---|---|
| 3px thin canny edge | Geometric boundary hint | No thick outline in output |
| 12-22px thick black ring | Content to reproduce | **Thick cartoon outline** in output |

## Union Pro 2.0

- **Requires VAE input** — first-time setup will fail without it
- Add `vae` input to `ControlNetApplyAdvanced` node
- Type selection: `canny/lineart/anime_lineart/mlsd` for line constraint

## Sweet Spot Parameters

| Parameter | Value | Notes |
|---|---|---|
| CN strength | 0.75-0.85 | Lower = more creative freedom, higher = stricter |
| end_percent | 0.90-0.95 | Stop CN influence before final denoising steps |

## Mask Design Rules

- Draw the mask to look like the desired output
- Include outline thickness you want in the final image
- White interior = "fill this area" signal to Flux
- Black ring width determines output outline width

See also: [[flux-priors]], [[lora-behavior]]
