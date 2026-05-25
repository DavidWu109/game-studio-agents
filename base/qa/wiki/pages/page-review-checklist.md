---
title: Game UI Page Review Checklist
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [review, checklist, layout, ui, quality]
sources: [GamePanel 9-round iteration 2026-05-25]
confidence: high
---

# Game UI Page Review Checklist

Universal checklist for reviewing any game UI page/panel. Derived from
real iteration sessions where these issues caused rework.

## 1. Element Rendering Completeness

Every visible element must actually render, not just occupy space.

- [ ] All images/sprites load correctly (not white rectangles)
- [ ] Text is rendered with correct font (not fallback squares)
- [ ] Icons are visible and distinguishable at target resolution
- [ ] Frame/border assets display (transparent centers show content beneath)
- [ ] Dummy/preview data fills all areas (no empty containers)

**Common failure**: editor preview doesn't trigger runtime initialization —
sprites loaded via `Sprite.Create()` at build time lose references when
saved to prefab. Use persistent asset paths. See [[sprite-path-gotcha]].

## 2. Text Readability

All text must be readable on the target device (not just on a desktop monitor).

- [ ] Key text has outline/stroke (outlineWidth ≥ 0.15 for mid, ≥ 0.30 for heavy)
- [ ] Text contrast against background is sufficient
- [ ] Font size minimum meets mobile standard (≥12pt effective on device)
- [ ] Three-tier text hierarchy visible: heavy (titles/buttons), medium (counts/status), light (hints)
- [ ] No text-on-similar-color-background (e.g. purple text on purple panel)

## 3. Touch Target Size

Interactive elements must be large enough to tap on mobile.

- [ ] All buttons ≥ 48pt on target device (calculate: canvas_units × scale_factor)
- [ ] Primary action button is the most visually prominent
- [ ] Button spacing ≥ 20% of button height (no accidental taps)
- [ ] Card/tile tap targets don't overlap when adjacent

## 4. Layout Boundaries

No element should be clipped or hidden by screen edges.

- [ ] Safe area margins applied (notch/rounded corners on modern phones)
- [ ] Bottom elements lifted ≥ 2% from screen edge
- [ ] Left/right elements don't overlap with adjacent panels
- [ ] Elements don't overflow their parent containers

## 5. Information Hierarchy

Most important information is most prominent.

- [ ] Primary game state (turn, score, card count) is largest/brightest
- [ ] Player identity (avatar, name) is clearly visible
- [ ] Secondary info (opponent details) is present but not dominant
- [ ] Decorative elements don't compete with interactive elements
- [ ] Background decoration is dimmed enough to not distract

## 6. Player Layout (multiplayer)

Player positions must match the game's perspective.

- [ ] Player count modes all have correct layout (2p, 3p, 4p)
- [ ] Self is always at bottom
- [ ] Opponents arranged naturally (top for 2p; top+left for 3p; top+left+right for 4p)
- [ ] Each player slot shows: avatar + name + card count at minimum
- [ ] Avatar images actually render (not empty circles)

## 7. Variable Content Boundaries

UI must handle different amounts of content gracefully.

- [ ] Hand cards: tested with minimum (5) and maximum (15+) count
- [ ] Player names: tested with short ("Jo") and long ("Christopher") names
- [ ] Score numbers: tested with 1-digit and 3-digit values
- [ ] Lists: tested with 0 items and max items
- [ ] Auto-sizing text doesn't shrink below readable minimum

## 8. Visual Consistency

All elements should feel like they belong to the same game.

- [ ] Outline thickness consistent across elements
- [ ] Color palette matches style anchor
- [ ] No mix of 2D flat and 3D/glossy styles
- [ ] Background and foreground elements are from same art generation batch
- [ ] No placeholder/programmer-art visible in review build

## Mockup Comparison (when available)

When Design agent has provided a mockup for the panel being reviewed,
the primary scoring method is **visual diff against mockup**:

1. Place mockup (design target) alongside Unity screenshot
2. Score each section by how closely the implementation matches the design
3. Specific deviations become actionable issues for Engineering

Mockup source: `projects/<game>/design/mockups/<panel>.png`
Provider: Design agent (PIL composite of real assets + game font)

When no mockup exists, fall back to checklist-only scoring below.

## Scoring

Use the dual-layer scoring system from [[evaluator-calibration]]:
- Component scores per section above (any < 6 blocks shipping)
- Weighted overall ≥ 7.5 to approve

## Common Failures (from real iterations)

| Failure | Root Cause | Time Wasted |
|---|---|---|
| White rectangle cards | Sprite path wrong (Assets/ vs Resources/) | 3 rounds |
| Text invisible | No outline on text over busy background | 2 rounds |
| Elements clipped at bottom | No safe area margin | 1 round |
| Avatar empty circles | Sprite not loading in editor preview | 2 rounds |
| Decoration dominates UI | Background not dimmed, same visual weight as buttons | 1 round |

These failures are all detectable with this checklist BEFORE starting
iterative fixes. Run the checklist first, fix all items, then iterate
on subjective quality.
