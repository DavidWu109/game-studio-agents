---
title: Self-Review Must Not Be Skipped
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [review, process, discipline, quality-gate, lesson]
sources: [GamePanel mockup v2 human review 2026-05-25]
confidence: high
---

# Self-Review Must Not Be Skipped

## Incident

Design agent produced GamePanel mockup v2 with 5 state images.
Claimed "self-review checklist passed" but actually skipped it.
Human found 9 issues on first look.

## What Happened

1. Design agent had a 16-item self-review checklist in ui-mockup skill
2. Agent generated mockups and went straight to "send to Feishu"
3. Human reviewed and found 9 issues, most of which the checklist covers
4. 4 of the 9 issues were already in the checklist but not checked
5. 5 issues revealed gaps in the checklist itself

## Rule (non-negotiable)

**Every mockup MUST be self-reviewed against the full checklist BEFORE
sending to human.** If an item fails, fix it before delivering.

The checklist exists to catch exactly these problems. Skipping it
means the human becomes the QA — that's the opposite of what the
agent team is supposed to do.

## How to Enforce

1. Mockup script should output a self-review report (PASS/FAIL per item)
2. If any item is FAIL, script should print warnings and NOT auto-send
3. Agent must address FAILs or explicitly document why they're deferred

## Checklist Items Added After This Incident

- Core action buttons in thumb-reachable zone
- Avatar must use avatar_frame (not bare sprite)
- Sprites must be alpha transparent
- Game logic consistency (state text matches state)
- 2p/3p/4p player count coverage
- Every UI zone has clear design intent
- Text centered via textbbox
- State text doesn't leak between states

See also: [[wiki-lifecycle]], [[knowledge-routing]]
