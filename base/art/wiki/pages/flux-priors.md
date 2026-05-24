---
title: Flux Model Priors and Workarounds
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [flux, prompt, cfg, controlnet]
sources: [comfyui_workflow/DEBUG_LESSONS.md]
confidence: high
---

# Flux Model Priors

## Negative Prompt Is Ineffective

Flux uses `BasicGuider` at CFG=1. Negative prompts are **completely ignored**.
Only `CFGGuider` (CFG>1) uses negative conditions, but Flux produces artifacts
at high CFG.

**Workaround**: write all exclusions as positive statements.
- BAD: "no chairs, no capsule"
- GOOD: "the room is completely empty of furniture"
- Use positive antonyms: "one continuous unbroken body, seamless silhouette"

## Vocabulary Priors (T5 Encoder)

The T5 text encoder has strong concept bindings:

| Word | What Flux Generates | Avoid |
|---|---|---|
| pill, capsule, stadium, lozenge, tablet | Medical capsule (two-half split) | Use "rounded horizontal banner button" |
| tavern | Always adds chairs and tables | Use "ancient stone chamber" or reframe scene |

These bindings cannot be overridden by prompt — they are baked into the encoder.

## Brand Anchoring

Brand names activate entire concept clusters in T5:

- "Hearthstone" → gold borders, gem inlays, premium ornaments
- "Cult of the Lamb" → purple tones, multi-layer decoration, oil paint texture

**Rule**: brand anchoring for exploration only. For final assets, use pure
visual descriptions. You cannot cherry-pick one trait from a brand cluster.

## Small Icon Rendering Limitation

Flux struggles to render clear, recognizable icons inside small circular
areas (128×128 category buttons). Common failures:

- Icon doesn't appear at all (empty circle)
- Wrong icon type (play arrow instead of up-down arrow)
- Icon is blurry/ambiguous at small sizes
- Fill color deviates from target hex significantly

**Workaround options:**
1. ControlNet with pre-drawn icon mask (draw the icon in the mask itself)
2. PIL programmatic generation (circle + icon) → Flux style transfer
3. Generate larger (256×256+) then downscale
4. Simpler icon shapes (silhouettes > detailed drawings)

## Color Accuracy

Flux frequently shifts colors lighter/more pastel than requested:
- Requested deep purple #5E2A82 → outputs lavender
- Requested amber #FFB300 → outputs pale peach/cream
- Requested dark green #0F6E56 → outputs bright lime

**Workaround:** specify BOTH hex code AND descriptive words ("deep dark
warm amber-gold, NOT pale, NOT pastel, NOT cream"). Post-process HSV
correction may be needed for critical color matching.

See also: [[lora-behavior]], [[controlnet-guide]]
