---
title: Dispatch Daemon — Hermes Cron Based
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [dispatch, daemon, cron, hermes, automation]
sources: [dispatch-issues-v2.md Issue #7]
confidence: medium
---

# Dispatch Daemon

## Problem

Dispatch runner is a one-shot process. If it dies (context window limit,
terminal close, system sleep), tasks get stuck in `in_progress` forever.
No auto-restart, no heartbeat, no recovery.

## Solution: Hermes Cron

Use Hermes gateway's built-in cron scheduler to periodically check for
pending dispatch YAML files and execute them.

### Setup

```bash
hermes -p gamestudio cron add \
  --schedule "*/5 * * * *" \
  --name "dispatch-check" \
  --prompt "Check for pending dispatch YAMLs in ~/Projects/gopoo-studio-project/studio/tasks/. For each YAML where status != done and has planned/in_progress tasks, run: cd ~/Projects/game-studio-agents && python3 -m core.dispatch <yaml_path> --poll 10. Report results via Feishu." \
  --delivery feishu
```

### How It Works

```
Every 5 minutes:
  1. Hermes cron fires
  2. Scans studio/tasks/*.yaml for active dispatches
  3. For each:
     - _reset_stale_in_progress() clears crashed tasks
     - get_ready_tasks() finds unblocked work
     - If ready tasks exist → run dispatch loop
     - If all done → skip
  4. Dispatch loop runs tasks, updates YAML, sends Feishu
  5. Cron exits, next tick in 5 minutes
```

### Recovery Behavior

| Scenario | What Happens |
|---|---|
| Dispatch dies mid-task | Next cron tick resets in_progress → planned, retries |
| Mac goes to sleep | Cron resumes after wake, picks up where it left off |
| Terminal closed | Hermes gateway is a launchd service, keeps running |
| Context window limit | Current dispatch exits, next tick starts fresh |
| All tasks done | Cron tick is a no-op |

### Why Hermes Cron, Not Custom Daemon

- Hermes gateway already runs as launchd service (survives logout)
- Cron has built-in Feishu delivery
- No new process to manage
- 5-minute granularity is fine (tasks take minutes not seconds)
- Can upgrade to custom daemon later if needed

### Limitations

- 5-minute polling means up to 5 min delay after a task completes
- Cron sessions have 3-minute hard timeout in Hermes — long dispatches
  need the cron job to launch dispatch as a background process
- Hermes cron skips memory providers — dispatch won't benefit from
  Hermes memory/skills in the cron context

### Future: Custom Daemon

When 5-minute polling isn't fast enough:

```python
# core/daemon.py — file watcher + dispatch executor
# Watch studio/tasks/*.yaml for changes
# On change: check ready tasks, execute immediately
# Heartbeat file for health monitoring
# systemd/launchd service definition
```

This is a Week 3-4 upgrade. Hermes cron covers Week 2.

See also: [[dispatch-automation-plan]], [[dispatch-issues-v2]], [[roadmap]]
