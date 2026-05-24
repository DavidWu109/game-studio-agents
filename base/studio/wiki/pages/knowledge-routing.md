---
title: Knowledge Routing — Wiki vs Skill vs Raw
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [planning, knowledge, routing, decision]
sources: [tense emotion review 2026-05-24]
confidence: high
---

# Knowledge Routing Rules

## Where Does This Belong?

| Question | Answer | Store |
|---|---|---|
| Is it an immutable source document? | Image, log, recording | `raw/` |
| Is it a fact about the world/domain? | "Flux ignores negative prompt at CFG=1" | `wiki/pages/` |
| Is it a project decision or status? | "R2S0 picked as tense final" | `wiki/pages/` (project) |
| Is it a procedure for doing a task? | "How to generate a button" | `skills/SKILL.md` |
| Is it a pitfall to avoid during a procedure? | "Don't use 'pill' in prompt" | `skills/SKILL.md` pitfalls |
| Is it detailed session data from one run? | Round-by-round scores | `skills/references/` |

## Common Mistakes

**Decision records in skills**: "We picked this image" is a project fact,
not a procedure. It goes in wiki, not SKILL.md.

**Procedures in wiki**: "Step 1: render mask, Step 2: run Flux" is a
procedure. It goes in a skill, not a wiki page.

**Universal knowledge in project wiki**: "Flux can't do nervous expressions"
is true for any game. It goes in `base/`, not `projects/`.

## The Two Tests

**Skill or wiki?**
> "If I delete this, would someone not know HOW to do the task?"
> YES → skill. NO → wiki.

**Base or project?**
> "Would this still be true for a completely different game?"
> YES → base. NO → project.

See also: [[roadmap]], [[evaluator-calibration]]
