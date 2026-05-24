---
name: task-dispatch
description: "Decompose goals into agent tasks with dependencies."
version: 1.0.0
created_by: agent
tags: [dispatch, scheduling, dependency, coordination]
---

# Task Dispatch Skill

Break a high-level goal into concrete agent tasks, resolve dependencies,
and execute in the correct order.

## When to Use

When a goal involves multiple departments or requires sequential steps
across agents. Single-department tasks don't need dispatch — they go
directly to that agent.

## Procedure

### Step 1: Decompose

Break the goal into atomic tasks. Each task has:

```yaml
task_id: unique_name
agent: art | engineering | go-dev | design | qa | marketing
action: iterate | ingest | code | review | generate
input: what the agent needs to start
output: what the agent produces
depends_on: [list of task_ids that must complete first]
```

### Step 2: Dependency Graph

Draw the execution order. Rules:
- Tasks with no dependencies can run in **parallel**
- A task starts only when ALL `depends_on` tasks are done
- Circular dependencies = design error, restructure

### Step 3: Execute

For each ready task (all dependencies satisfied):
1. Load the agent's AGENTS.md + relevant wiki + skills
2. Execute the task (iterate / code change / review)
3. Write output to agreed location
4. Mark task complete in dispatch log
5. Check what tasks are now unblocked

### Step 4: Report

After all tasks complete (or a task fails):
- Collect results from each agent
- Run QA review if applicable
- Report to human via Feishu
- Write lessons to wiki

## Task File Format

Store in `projects/<project>/studio/tasks/`:

```yaml
# projects/gopoo/studio/tasks/gamepanel-fixes.yaml
goal: "Fix GamePanel remaining issues to 8.0/10"
created: 2026-05-25
status: in_progress  # planned | in_progress | done | blocked

tasks:
  - id: toilet_art
    agent: art
    action: iterate
    input: "Generate toilet/card-draw-station asset (马桶造型, not card stack)"
    output: "assets/toilet_draw.png deployed to Unity"
    depends_on: []
    status: planned

  - id: layout_refactor
    agent: engineering
    action: code
    input: "Refactor GamePanelBuilder: avatar resize, sprite path fix, layout"
    output: "GamePanel.prefab rebuilt"
    depends_on: []
    status: planned

  - id: integrate_toilet
    agent: engineering
    action: code
    input: "Replace toilet_stack with new toilet_draw asset in GamePanelBuilder"
    output: "GamePanel.prefab with new toilet"
    depends_on: [toilet_art, layout_refactor]
    status: planned

  - id: qa_review
    agent: qa
    action: review
    input: "Screenshot GamePanel, run page-review-checklist"
    output: "Score + issue list"
    depends_on: [integrate_toilet]
    status: planned

  - id: report
    agent: studio
    action: report
    input: "Collect all results, send Feishu"
    output: "Human notification"
    depends_on: [qa_review]
    status: planned
```

## Execution Visualization

```
toilet_art ─────────────┐
  (Art, parallel)       ├──→ integrate_toilet ──→ qa_review ──→ report
layout_refactor ────────┘     (Engineering)       (QA)         (Studio)
  (Engineering, parallel)
```

## Parallel vs Sequential Rules

| Scenario | Approach |
|---|---|
| Art asset + code refactor (independent) | **Parallel** |
| New asset + integrate into code | **Sequential** (asset first) |
| Code change + test | **Sequential** (code first) |
| Multiple asset types (button + card) | **Parallel** |
| Build + screenshot + review | **Sequential** (chain) |

## Status Tracking

After each task completes, update the YAML:

```yaml
  - id: toilet_art
    status: done
    completed: 2026-05-25T23:00:00
    result: "toilet_draw.png 8.0/10, deployed to Assets/Art/UI/"
```

When a task fails:

```yaml
  - id: toilet_art
    status: blocked
    blocked_reason: "Flux architectural ceiling — needs strategy change"
    escalate_to: human
```

## Safety Rules for Automated Execution

Agent handlers use `claude -p --dangerously-skip-permissions` for
unattended execution. Safety is enforced via prompt constraints:

| Agent | Allowed | Forbidden |
|---|---|---|
| Engineering | Modify Assets/Editor/, Assets/Scripts/ | Delete .cs files, modify outside project |
| QA | Read screenshots, read wiki | Modify any files |
| Art | Run autoresearch loop, write to runs/ | Modify source code |
| Studio | Read status, send notifications | Modify task files during execution |

These rules are embedded in the handler prompts in `core/dispatch.py`.
They are NOT enforced by the system — a misbehaving LLM could violate them.
For critical deployments, add file system sandboxing.

## Pitfalls

- Don't start dependent tasks before dependencies are done (obvious but easy to forget)
- Don't skip QA review to save time — it catches issues that compound
- Report results even on failure — the failure itself is information
- Write to wiki DURING dispatch, not just at the end — partial progress has value
- `claude -p` permission errors will silently "succeed" with no actual changes — check results
