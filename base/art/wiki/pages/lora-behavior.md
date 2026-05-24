---
title: LoRA Behavior Patterns
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [lora, flux, style]
sources: [comfyui_workflow/DEBUG_LESSONS.md]
confidence: high
---

# LoRA as Style Attractor

LoRA's "style attractor" priority is **higher than prompt text**. If LoRA
training data conflicts with your prompt, the LoRA wins.

## Known LoRA Behaviors

| LoRA | Training Data Feature | Actual Output |
|---|---|---|
| UI_UX_Design_Flux | Web 2.0 glass buttons | Glossy/gel texture regardless of "matte" prompt |
| 3D_Game_Icon_Flux | Smooth 3D icons | No thick outlines despite prompt requesting them |

## Rules

1. LoRA is not "enhancement" — it **replaces** part of the prompt's semantics
2. Check LoRA training data characteristics, not just the LoRA name
3. If LoRA conflicts with requirements, **remove the LoRA entirely**
4. Use ControlNet to compensate for lost LoRA features

## Decision Flow

```
Need a specific style feature?
  → Is there a LoRA for it?
    → Does the LoRA's OTHER features conflict with requirements?
      YES → Remove LoRA, use ControlNet mask instead
      NO  → Use LoRA
```

See also: [[flux-priors]], [[controlnet-guide]]
