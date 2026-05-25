---
title: Dispatch Runner Issues — v0.7 Execution (Second Run)
created: 2026-05-25
updated: 2026-05-25
type: summary
tags: [dispatch, issue, automation, postmortem]
sources: [v07-deliverable.yaml execution 2026-05-25]
confidence: high
---

# Dispatch Runner Issues (v0.7 Run)

Tracked during live execution. To be resolved after dispatch completes.

## Issue 1: Single-Threaded Execution Prevents True Parallelism

**Symptom**: art_overnight_batch (ComfyUI) waited for all qa.review tasks
(Unity MCP) to finish, even though they use different resources.

**Root Cause**: `dispatch_loop` calls handlers synchronously. Even with
resource locks, only one task runs at a time. The lock system was designed
for multi-threaded execution but the loop is single-threaded.

**Impact**: 30+ minute Art task blocked by 5-minute QA tasks. Total time
= sum of all tasks instead of max(parallel groups).

**Fix Options**:
- A) `threading.Thread` per task (simplest, but subprocess calls may conflict)
- B) `multiprocessing` per task (true isolation, heavier)
- C) Launch long-running tasks as background processes, poll for completion
- D) Separate dispatch into "fast loop" (eng/qa) and "slow loop" (art) runners

## Issue 2: Art Task YAML Matching is Wrong

**Symptom**: `art_overnight_batch` task was matched to `poop_emotions.yaml`
instead of the intended card_back/button fix tasks.

**Root Cause**: Handler `run_art_iterate` matches task YAML by keyword in
filename (`task_id.split("_")`). "art_overnight_batch" → "art" → first
match was poop_emotions.yaml.

**Impact**: Wrong autoresearch task executed. Wasted ComfyUI time.

**Fix**: Art tasks in dispatch YAML should specify the exact task YAML path:

```yaml
- id: art_overnight_batch
  agent: art
  action: iterate
  task_yaml: autoresearch/tasks/card_back_v2.yaml  # explicit path
```

## Issue 3: Engineering Handler Permission Issue (from first run)

**Symptom**: `claude -p --dangerously-skip-permissions` still produced
"waiting for permission" results in some cases.

**Root Cause**: Claude Code CLI in `-p` (pipe) mode may not fully honor
`--dangerously-skip-permissions` for all tool types, or the prompt didn't
trigger actual file edits.

**Impact**: Layout fixes marked "done" but no actual code changes made.

**Fix Options**:
- A) Use `claude --dangerously-skip-permissions -p` (flag before -p)
- B) Write a Python script that makes the edits directly instead of
     delegating to Claude CLI
- C) Pre-generate a patch file and apply with `git apply`

## Issue 4: QA Handler Captures Wrong Panel

**Symptom**: qa.review tasks all use `gopoo-capture-panel` with "GamePanel"
hardcoded, regardless of which panel the task says to review.

**Root Cause**: Handler doesn't parse the panel name from task input.

**Fix**: Parse panel name from task input string, pass to capture tool.

## Issue 5: No Result Validation

**Symptom**: Tasks marked "done" with results like "waiting for permission"
or wrong YAML match — dispatch doesn't verify the result makes sense.

**Root Cause**: Any handler return value is accepted as success.

**Fix**: Add result validators per task type:
- Engineering: check "compile" or "error" in result
- Art: check "score=" in result
- QA: check JSON parseable with "sections" key

## Issue 6: Report Handler Doesn't Send Screenshots

**Symptom**: Final Feishu report was text-only. QA captured screenshots
but they were never sent to the user.

**Root Cause**: `run_studio_report()` just returns "report" — doesn't
collect QA screenshots or art finals and attach to Feishu message.

**Fix**: Report handler should:
1. Find all `qa_*.png` screenshots from this dispatch run
2. Find all art `final.png` outputs
3. Build a grid image
4. Send via `send_image()` to Feishu

## Priority After Dispatch Completes

1. **Issue 2** (wrong YAML match) — quick fix, prevents wasted compute
2. **Issue 4** (panel name parsing) — quick fix, QA reviews wrong thing
3. **Issue 1** (parallelism) — medium effort, biggest time savings
4. **Issue 5** (result validation) — prevents silent failures
5. **Issue 3** (permission) — may need alternative to claude -p

## v0.7 Dispatch Execution Summary

Ran v07-deliverable.yaml: 12 tasks, 4 completed before dispatch was stopped.

### QA Scores (all panels reviewed as GamePanel due to Issue #4)

| Panel | rendering | text | touch | layout | hierarchy | consistency | overall |
|---|---|---|---|---|---|---|---|
| MainMenu (mm_review) | 7 | 5 | 6 | 6 | 7 | 8 | 6.5 |
| Lobby (lobby_review) | 7 | 6 | 7 | 5 | 6 | 8 | 6.3 |
| Result (result_review) | 7 | 5 | 7 | 6 | 7 | 8 | 6.5 |

Common issues across all panels:
- Text too small / no outline on busy backgrounds
- Hand cards clipped at screen edges (safe area)
- Background decorations compete with UI elements

### What Got Done vs What Didn't

| Done | Not Done |
|---|---|
| gp_layout_fix (engineering code changes) | gp_capture_review (blocked by single-thread) |
| mm_review (QA scored 6.5) | mm_fixes |
| lobby_review (QA scored 6.3) | lobby_fixes |
| result_review (QA scored 6.5) | result_fixes |
| | art_overnight_batch (interrupted) |
| | full_build, final_screenshots, deliver |

See also: [[dispatch-lessons]], [[dispatch-automation-plan]]
