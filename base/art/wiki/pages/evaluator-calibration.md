---
title: Evaluator Calibration — Checklist vs Holistic Scoring
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [scoring, review, automation, quality-gate, evaluator-design]
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

## Multi-Dimension Scoring (Composite Assets)

Discovered during card_back_v2 review (2026-05-24):

- R1S1 scored 4/10 overall, but had the **best border, composition, and card feel**
- R3S1 scored 8/10 overall, but had the **best mascot character** while other
  elements were flat/plain
- Human verdict: ideal result = R1S1's border + R3S1's poop mascot

### The Problem

Single-score evaluation forces a false choice. A complex asset (card, panel,
scene) has **independent visual dimensions** that should be scored separately:

| Dimension | R1S1 | R3S1 |
|---|---|---|
| Border/frame quality | 9 | 5 |
| Central character | 4 | 9 |
| Color/palette | 8 | 7 |
| Suit symbols | 7 | 6 |
| Overall card feel | 8 | 6 |
| **Single score (evaluator)** | **4** | **8** |

R3S1 "won" because the evaluator's single score was dragged up by the character.
R1S1 "lost" because the evaluator's single score was dragged down by the character.
Neither score reflects the dimensional strengths.

### Fix: Dimensional Scoring for Composite Assets

For assets with multiple independent visual regions (cards, panels, frames),
score each dimension separately:

```json
{
  "dimensions": {
    "border_frame": {"score": 8, "notes": "ornate gold, good weight"},
    "central_element": {"score": 4, "notes": "too simple, needs CotL style"},
    "color_palette": {"score": 9, "notes": "deep purple on target"},
    "decorative_details": {"score": 7, "notes": "suit symbols present"},
    "overall_feel": {"score": 8, "notes": "reads as premium card back"}
  },
  "composite_score": 7.2,
  "best_dimensions": ["border_frame", "color_palette"],
  "worst_dimensions": ["central_element"]
}
```

### Enabling Composite Workflows

Dimensional scoring enables a new production strategy:

```
Round N produces images with per-dimension scores
  → Identify "best border" image and "best character" image
  → Inpaint: use best border as base, replace central region
     with best character's style
  → Evaluate the composite
```

This is more efficient than hoping one prompt produces all dimensions
perfectly in a single generation. Especially for Flux, which tends to
excel at one aspect per seed while trading off others.

### When to Use Dimensional vs Single Score

| Asset Type | Scoring | Why |
|---|---|---|
| Character sprite | Single + holistic | One visual subject, expression matters as whole |
| Button | Single | Simple shape, uniform quality |
| Card back/front | Dimensional | Multiple independent regions (border, center, corners) |
| Panel/frame | Dimensional | Frame + content area + decorations |
| Background/scene | Dimensional | Composition + mood + detail elements |

See also: [[flux-priors]] (expression nuance ceiling), [[page-review-checklist]]
