---
name: asset-review
description: "Review generated asset finals and route findings to wiki."
version: 1.0.0
created_by: agent
tags: [review, scoring, quality, workflow]
---

# Asset Review Skill

Systematic review of AutoResearch run finals. Scores each output,
classifies actionable findings, and routes knowledge to the correct
wiki/skill layer.

## When to Use

After any AutoResearch batch run completes, or when auditing existing
asset libraries before deployment.

## Procedure

```
[1] Collect:  find runs/ -name "final.png" | sort
[2] View:     read each final image
[3] Score:    0-10 against style checklist + target description
[4] Classify: ✅ (≥8) / ⚠️ (6-7) / ❌ (<6)
[5] Route findings (see below)
[6] Update wiki log
```

## Finding Classification and Routing

| Finding Type | Example | Destination |
|---|---|---|
| Model limitation (any game) | "Flux can't render icons in small circles" | `base/art/wiki/` |
| Pipeline technique (any game) | "PIL pre-draw mask for icon shapes" | `base/art/skills/` |
| Style drift (this game) | "purple too light, need #5E2A82" | `projects/<game>/art/skills/*/references/` |
| Expression mismatch (this game) | "tense reads as sad" | `projects/<game>/art/skills/*/references/` |
| Passed asset | deploy path + backup | `projects/<game>/engineering/wiki/` |

### The Key Question

For each finding, ask:
> "Would this still be true if we were making a different game?"

YES → `base/` (universal)
NO → `projects/<game>/` (project-specific)

## Output Template

```markdown
## Asset Review — [date]

### ✅ Ship (≥8)
- asset_name: score X — notes

### ⚠️ Iterate (6-7)
- asset_name: score X — specific issue → action

### ❌ Redo (<6)
- asset_name: score X — root cause → strategy change needed?

### Findings Routed
- base/art/wiki/flux-priors.md: added "small icon limitation"
- projects/gopoo/art/skills/gopoo-emotion/references/: updated tense notes
```

## Pitfalls

- Don't batch-approve ⚠️ assets to save time — they accumulate visual debt
- Score against the STYLE_SENTENCE, not personal taste
- Check if a ❌ asset needs strategy change (architectural) vs prompt tweaks (parametric)
