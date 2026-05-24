---
title: Dispatch Lessons — First Real Multi-Agent Execution
created: 2026-05-25
updated: 2026-05-25
type: summary
tags: [dispatch, automation, coordination, lesson]
sources: [gamepanel-fixes dispatch 2026-05-25]
confidence: high
---

# Dispatch Lessons (2026-05-25)

First real execution of task-dispatch skill on gamepanel-fixes.yaml.
3 of 6 tasks completed, 2 agents (Art + Engineering) ran in parallel.

## What Worked

**Task decomposition was correct.** The dependency graph accurately
reflected real constraints — Art toilet generation and Engineering
layout refactor were truly independent and ran in parallel.

**Feishu notifications created a timeline.** Each agent posting
`【Agent名】message` made the execution traceable. Human could
follow progress from phone without being at the computer.

**Parallel execution saved time.** Engineering finished layout refactor
(7 min) while Art was still on round 1 of toilet generation.
Engineering validated with old assets, didn't wait for Art.

**Art iterate loop continues to work.** toilet_draw_v2 passed 8.0/10
in only 2 rounds — the wiki lessons from previous sessions
(flux-priors, evaluator-calibration) were read by generator.

## What Didn't Work

### 1. Manual orchestration
The human (Claude Code CLI session) acted as the dispatcher —
reading the YAML, deciding what to run next, calling each agent.
No automation whatsoever.

**Impact**: human bottleneck. If human is asleep, dispatch stalls.

### 2. No dependency-triggered execution
When Art toilet completed, nothing automatically started
integrate_assets. The human had to notice and trigger it.

**Impact**: idle time between tasks.

### 3. Task status not persisted
The YAML file still shows `status: planned` for completed tasks.
No record of completion time, result, or score in the dispatch file.

**Impact**: can't resume a partially-completed dispatch, can't
audit what happened after the fact.

### 4. Resource contention not managed
bg_art couldn't run because ComfyUI was busy with toilet_art.
The dispatch has no concept of "ComfyUI is a shared resource
that only serves one task at a time."

**Impact**: parallel Art tasks actually serialize on ComfyUI.

### 5. No QA gate enforcement
Even though qa_review is in the dispatch, nothing prevents
the human from skipping it and deploying directly.

**Impact**: quality gate is advisory, not enforced.

## Automation Gap Analysis

| Manual Step | Automation Needed |
|---|---|
| Read YAML, decide next task | Dispatch runner script |
| Start agent (run CLI command) | Agent launcher per task type |
| Detect task completion | File watch (final.png / compile success) |
| Trigger dependent tasks | Dependency resolver |
| Update task status | YAML writer |
| Feishu notifications | Already automated ✅ |
| Wiki writes (synthesis) | Already automated ✅ |

See also: [[roadmap]], [[knowledge-routing]]
