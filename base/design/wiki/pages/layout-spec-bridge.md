---
title: Layout Spec Bridge — Mockup to Engine
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [layout, mockup, bridge, automation, engine-integration]
sources: [GamePanel layout sync dispatch 2026-05-25]
confidence: high
---

# Layout Spec Bridge

## Problem

Mockup uses pixel coordinates (PIL). Engine uses anchor percentages (Unity).
When LLM translates between them, accuracy is low — positions drift,
sizes don't match, and the result doesn't look like the mockup.

## Solution

Mockup script automatically outputs a **layout spec JSON** alongside
the PNG. Every element has its exact Unity anchor values pre-calculated.

```python
# In mockup script
def px_to_anchor(x, y, w, h):
    return {
        "anchorMin": [x / W, 1 - (y + h) / H],
        "anchorMax": [(x + w) / W, 1 - y / H],
    }
```

Engineering reads the JSON directly. No LLM interpretation needed.

## Flow

```
Design: mockup.py → gamepanel_mockup.png + gamepanel_layout_spec.json
                              ↓                        ↓
                    Human reviews visual    Engineering reads JSON
                              ↓                        ↓
                    "looks good"            Builder.cs sets anchors
                              ↓                        ↓
                              QA compares PNG vs Unity screenshot
```

## JSON Format

```json
{
  "_meta": {"screen": [1920, 1080], "safe_margin": [96, 54]},
  "element_name": {
    "anchorMin": [0.35, 0.26],
    "anchorMax": [0.65, 0.74],
    "size_px": [280, 364]
  }
}
```

## When to Use

Every time Design produces a mockup that Engineering needs to implement.
The spec JSON is mandatory output — mockup without spec is incomplete.

See also: [[self-review-failure]], [[industry-player-hand-display]]
