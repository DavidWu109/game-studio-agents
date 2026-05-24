---
title: Dispatch Automation Plan
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [dispatch, automation, plan, runner]
sources: [dispatch-lessons.md]
confidence: medium
---

# Dispatch Automation Plan

Turn the manual dispatch process into a self-running system.
Ordered by impact and dependency.

## Phase 1: Task Status Persistence (simplest, do first)

**Problem**: YAML status stays "planned" after task completes.

**Solution**: `core/dispatch.py` — a runner that:
1. Reads task YAML
2. After each task, updates `status: done`, `completed: timestamp`, `result: ...`
3. Writes YAML back

```python
def mark_done(yaml_path, task_id, result):
    """Update task status in dispatch YAML."""
    tasks = load_yaml(yaml_path)
    for t in tasks["tasks"]:
        if t["id"] == task_id:
            t["status"] = "done"
            t["completed"] = now_iso()
            t["result"] = result
    save_yaml(yaml_path, tasks)
```

**Effort**: ~30 min. No external dependencies.

## Phase 2: Dependency Resolver (enables auto-trigger)

**Problem**: No automatic "task X done → start task Y".

**Solution**: Add to `core/dispatch.py`:
1. Find all tasks with `status: planned`
2. Check if all `depends_on` are `status: done`
3. If yes → task is "ready"
4. Return list of ready tasks

```python
def get_ready_tasks(yaml_path):
    """Return tasks whose dependencies are all satisfied."""
    tasks = load_yaml(yaml_path)["tasks"]
    done_ids = {t["id"] for t in tasks if t["status"] == "done"}
    ready = []
    for t in tasks:
        if t["status"] != "planned":
            continue
        deps = set(t.get("depends_on", []))
        if deps.issubset(done_ids):
            ready.append(t)
    return ready
```

**Effort**: ~30 min. Depends on Phase 1.

## Phase 3: Agent Launcher (maps task → execution)

**Problem**: Each task type needs different execution.

**Solution**: Task type → handler mapping:

```python
HANDLERS = {
    ("art", "iterate"): run_art_iterate,      # python3 -m autoresearch.loop
    ("engineering", "code"): run_claude_code,  # claude -p with CLAUDE.md context
    ("qa", "review"): run_qa_review,           # capture + checklist scoring
    ("studio", "report"): run_feishu_report,   # collect + notify
}

def run_art_iterate(task):
    """Launch autoresearch loop for the task."""
    task_yaml = find_or_create_task_yaml(task)
    subprocess.run(["python3", "-m", "autoresearch.loop", task_yaml])
    return detect_result(task)  # check final.png, read score

def run_claude_code(task):
    """Delegate to Claude Code for code changes."""
    prompt = f"Read these files first:\n{task['input']}\n\nThen make the changes."
    result = subprocess.run(["claude", "-p", prompt, "--output-format", "json"], ...)
    return parse_result(result)
```

**Effort**: ~2 hours. Depends on Phase 2.

## Phase 4: Resource Manager (prevent contention)

**Problem**: Two Art tasks can't use ComfyUI simultaneously.

**Solution**: Resource locks per shared resource:

```python
RESOURCES = {
    "comfyui": Lock(),    # only one Art iterate at a time
    "unity_mcp": Lock(),  # only one Engineering build at a time
}

def acquire_resource(task):
    resource = RESOURCE_MAP.get((task["agent"], task["action"]))
    if resource and not RESOURCES[resource].acquire(blocking=False):
        return False  # resource busy, try later
    return True
```

**Effort**: ~1 hour. Optional — can also just serialize Art tasks.

## Phase 5: Dispatch Runner Loop (ties it all together)

**Problem**: Need someone to poll for ready tasks and launch them.

**Solution**: A loop that runs continuously (or via cron):

```python
def dispatch_loop(yaml_path, poll_interval=30):
    """Main dispatch loop — runs until all tasks done or blocked."""
    while True:
        ready = get_ready_tasks(yaml_path)
        if not ready:
            if all_done(yaml_path):
                notify("Studio", "✅ Dispatch complete")
                break
            if all_blocked(yaml_path):
                notify("Studio", "❌ Dispatch blocked, human intervention needed")
                break
            sleep(poll_interval)
            continue

        for task in ready:
            if not acquire_resource(task):
                continue
            mark_status(yaml_path, task["id"], "in_progress")
            notify(task["agent"], f"Starting: {task['id']}")
            try:
                result = HANDLERS[(task["agent"], task["action"])](task)
                mark_done(yaml_path, task["id"], result)
                notify(task["agent"], f"✅ Done: {task['id']} — {result}")
            except Exception as e:
                mark_blocked(yaml_path, task["id"], str(e))
                notify(task["agent"], f"❌ Blocked: {task['id']} — {e}")
```

**Effort**: ~2 hours. Depends on Phases 1-4.

## Implementation Order

```
Week 2:
  Day 1: Phase 1 (status persistence) + Phase 2 (dependency resolver)
  Day 2: Phase 3 (agent launcher — Art + Engineering handlers)
  Day 3: Phase 5 (dispatch loop) — test with gamepanel-fixes.yaml
  Day 4: Fix issues, add QA handler
  Day 5: Phase 4 (resource manager) if contention is a real problem

Week 3:
  Add Go Dev handler
  Add cross-agent wiki_insight messages
  Run first fully-unattended overnight dispatch
```

## Success Criteria

The dispatch is "automated" when:
1. Human writes the task YAML (goal + tasks + dependencies)
2. Human runs `python3 -m core.dispatch projects/gopoo/studio/tasks/gamepanel-fixes.yaml`
3. System executes all tasks in correct order, handles failures, notifies via Feishu
4. Human wakes up to a Feishu summary with before/after screenshots

Human still writes the YAML. System does everything else.

See also: [[dispatch-lessons]], [[roadmap]]
