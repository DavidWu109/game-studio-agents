---
title: Evaluator Calibration — Checklist vs Holistic Scoring
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [evaluator, scoring, calibration, checklist]
sources: [tense_v2 run 2026-05-24]
confidence: high
---

# Evaluator Calibration

## The Problem: Rigid Checklists Miss Holistic Quality

Discovered during GoPoo tense emotion iteration (2026-05-24):

- Evaluator checklist had 7 binary items (pupils sideways? wavy mouth? worried brows?)
- 9 images scored 2-4/10 because 3 items failed consistently
- Human review found 2 of those images **actually conveyed the target emotion**
- R2S0 scored 3/10 by checklist but was picked as the final by the human
  ("紧张到委屈的感觉" — nervous to the point of feeling wronged)

## Root Cause

Binary per-item scoring treats all checklist items as equal hard gates.
But in character expression, **overall emotional read matters more than
individual feature accuracy**. An image with "wrong" brow angle can still
read as nervous if the overall composition (sweat drops + mouth + posture)
sells it.

## Fix: Two-Pass Scoring

Evaluator should score in two passes:

### Pass 1: Feature Checklist (diagnostic, not score-determining)
Per-item ✅/❌ as before. Used to generate revision hints for the generator.
Does NOT directly determine the final score.

### Pass 2: Holistic Assessment (determines score)
- "Does this image, as a whole, convey the target emotion?" (0-10)
- "Would a player understand this is [emotion] in the game context?" (0-10)
- "Is the art quality (outline, style, consistency) acceptable?" (0-10)
- Final score = weighted average, not item count

### Score Reconciliation
If Pass 2 holistic score ≥ 7 but Pass 1 has failed items:
→ Flag for human review, do NOT auto-reject
→ The failed items become "nice to have" improvements, not blockers

## When Rigid Checklists DO Work

- **Structural requirements**: transparent background, correct dimensions, no text
- **Style requirements**: thick black outline present, flat colors
- **These are binary and non-negotiable**

## When Rigid Checklists Fail

- **Expression/emotion**: holistic perception > individual features
- **Composition/mood**: "does this feel right" > "is each element exactly as described"
- **Artistic judgment**: the human's "this feels nervous" overrides 0/3 on expression items

See also: [[flux-priors]] (expression nuance ceiling)
