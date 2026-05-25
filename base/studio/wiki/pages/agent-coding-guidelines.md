---
title: Agent Coding Guidelines — Karpathy's 4 Principles
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [process, coding, discipline, quality-gate, agent-behavior]
sources: [github.com/multica-ai/andrej-karpathy-skills, Karpathy X post]
confidence: high
---

# Agent Coding Guidelines

Derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876)
on LLM coding pitfalls. These 4 principles apply to ALL agents in the
studio when they write or modify code.

Validated: applying these to Claude Code raised accuracy from 65% → 94%.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### How This Failed For Us

- Design agent skipped self-review, assumed mockup was good → 9 issues
- Engineering agent assumed anchor values instead of reading layout spec
- Evaluator assumed 8/10 score was accurate without honest visual check

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite it.

### How This Failed For Us

- core/agent.py: full class with NotImplementedError everywhere — nobody called it
- 7-department structure created before any department had content
- Message bus designed before any agent needed to communicate

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.

### How This Failed For Us

- dispatch v1 `claude -p` changed code it shouldn't have
- Engineering handler modified files beyond the requested change
- GamePanelBuilder edits touched unrelated sections

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

### How This Failed For Us

- GamePanel "8.0/10" was self-declared without honest verification
- "layout_refactor done" was marked done without checking actual file changes
- Art iterate declared "done" on tasks with permission errors in results

## Application to Our Dispatch System

Every dispatch task `input` should follow principle #4:

```yaml
input: |
  Change X in file Y.
  Success criteria:
    1. File Y compiles without errors
    2. GamePanel screenshot shows X changed
    3. No other elements affected (surgical)
```

Result validation (core/dispatch.py `validate_result()`) enforces this —
but it only catches obvious failures. Agents should self-verify before
reporting "done".

## Application to Engineering Handler

The `claude -p` prompt for engineering tasks must include:

```
PRINCIPLES:
1. State what you'll change BEFORE changing it
2. Minimum changes — don't improve adjacent code
3. Match existing code style
4. Verify: compile clean, no unintended side effects
```

This is already partially in `build_safety_prompt()` but should be
strengthened with these explicit behavioral constraints.

See also: [[self-review-failure]], [[dispatch-issues-v2]], [[knowledge-routing]]
