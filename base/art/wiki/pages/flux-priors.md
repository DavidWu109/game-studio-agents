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

See also: [[lora-behavior]], [[controlnet-guide]]
