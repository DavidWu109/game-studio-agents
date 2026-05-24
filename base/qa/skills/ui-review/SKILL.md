---
name: ui-review
description: "Dual-layer UI scoring with component and overall gates."
version: 1.0.0
created_by: human
tags: [visual-review, scoring, checklist, quality]
---

# UI Review Skill

Systematic visual review process for game UI panels. Ensures no substandard
work ships by enforcing component-level and overall scoring gates.

## When to Use

- After building or modifying a UI panel
- Before sending screenshots for stakeholder review
- As part of QA regression testing

## Procedure

```
[1] Build/rebuild the panel
[2] Force recompile + confirm (check DLL timestamp)
[3] Capture screenshot (Play Mode + ScreenCapture)
[4] Run component checklist (below)
[5] Score each component 0-10
[6] If any component < 6 → fix that component first
[7] Score overall (weighted dimensions)
[8] If overall < 7.5 → continue iterating
[9] If all pass → approved for delivery
```

## Component Checklist (Universal)

- [ ] Title text: visible, sized appropriately, sufficient contrast, outlined
- [ ] Buttons: correct position, ≥48pt touch target, text centered, primary/secondary clear
- [ ] Button spacing: gaps ≥ 20% of button height, no overlap
- [ ] Text hierarchy: heavy/medium/light three tiers distinct
- [ ] Panel bounds: no elements overflow or get clipped
- [ ] Information hierarchy: most important info is largest and brightest
- [ ] Color contrast: text readable on background
- [ ] No overlap: all elements non-overlapping

## Overall Scoring Dimensions

| Dimension | Weight |
|---|---|
| Information hierarchy | 30% |
| Spacing/alignment | 25% |
| Color contrast | 20% |
| Style consistency | 15% |
| Touch usability | 10% |

## Gates

- Any component < 6 → **blocked** (fix before continuing)
- Overall < 7.5 → **iterate** (keep improving)
- All components ≥ 6 AND overall ≥ 7.5 → **approved**

## Pitfalls

- Don't skip the recompile step — changes won't appear without Assets/Refresh
- Don't score from editor preview — use Play Mode screenshot for accuracy
- "Runtime fills data" is not an excuse for empty panels — add dummy data
