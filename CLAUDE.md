# 铁砧魔坊 · Anvil — AI Game Studio Agent

## What This Is

Anvil is a multi-agent dispatch system for game development. It coordinates
department agents (Art, Engineering, Design, QA, Studio) to execute task DAGs
with dependency resolution, parallel execution, and QA feedback loops.

Current game project: **GoPoo** (card game, Unity/Tuanjie client).

## Key Paths

```
core/                    ← Anvil runtime
  dispatch.py            — task YAML executor with dependency resolution
  planner.py             — Plan-and-Execute (classify → knowledge → plan → execute → replan)
  provider.py            — multi-LLM routing (deepseek T2, cli/opus T1, sdk future)
  tool_runner.py         — gives LLMs read/write/bash tools with safety checks
  safety.py              — write guards and command allowlists
  search.py              — wiki knowledge retrieval
  skills.py              — skill registry
  agent.py               — agent base class
  daemon.py              — watches for new YAML, auto-dispatches

base/                    ← universal knowledge (carries across all games)
  art/                   — Flux, ControlNet, LoRA, color-keying
  engineering/           — Unity gotchas, sprite paths, build patterns
  design/                — game design patterns
  qa/                    — review checklists, screenshot scoring
  studio/                — coordination, dispatch lessons
  pm/, pjm/              — product/project management
  go-dev/                — Go server patterns

projects/gopoo/          ← GoPoo-specific overlay (→ ~/Projects/gopoo-studio-project/)
plans/                   ← dispatch YAML files (task DAGs)
```

## Project Relatives

| Path | Role |
|------|------|
| `~/Projects/go-poo-client/` | Unity/Tuanjie game client |
| `~/Projects/gopoo-studio-project/` | GoPoo project knowledge overlay |
| `~/Projects/comfyui_workflow/` | Art asset pipeline (ComfyUI) |

## Running Dispatch

```bash
# Execute a task DAG
python3 -m core.dispatch plans/some_task.yaml

# Dry run (show ready tasks without executing)
python3 -m core.dispatch plans/some_task.yaml --dry

# Custom poll interval
python3 -m core.dispatch plans/some_task.yaml --poll 10
```

## Task YAML Format

```yaml
task_id: fix_something
goal: "One-line description of what this dispatch accomplishes"
complexity: complex
tasks:
- id: step_one
  agent: engineering        # art | engineering | design | qa | studio
  action: code              # code | iterate | review | report
  provider: cli             # cli (Claude Code) | deepseek | sdk
  input: >
    Detailed instruction for the agent.
  status: planned

- id: step_two
  agent: qa
  action: review
  depends_on: [step_one]
  status: planned
```

## Provider Routing

| Provider | When | Cost |
|----------|------|------|
| `deepseek` | Default for code gen (T2 tasks) | API pay-per-token |
| `cli` | Architecture, creative, complex re-coding (T1 tasks) | Max subscription |
| `sdk` | Future: when Anthropic SDK credits available | API pay-per-token |

Set `provider: cli` in task YAML to force Claude Code CLI for a task.
DeepSeek API key is currently not configured — use `provider: cli` for all tasks.

## MCP Integration (Unity/Tuanjie)

Unity MCP server runs inside Tuanjie Editor. Port is dynamic — find it with:
```bash
lsof -iTCP -sTCP:LISTEN -P -n | grep unity-mcp
```

MCP session helper script: `/tmp/mcp.sh` (auto-initializes, auto-renews sessions)
```bash
bash /tmp/mcp.sh init                    # initialize session
bash /tmp/mcp.sh call "tool-name" '{}'   # call any MCP tool
bash /tmp/mcp.sh list                    # list available tools
```

Key MCP tools:
- `gopoo-exec-menu` — execute Unity menu items (build panels, etc.)
- `gopoo-game-state` — set game state + play mode screenshot
- `gopoo-preview-panel` — prefab preview screenshot (no play mode)
- `assets-refresh` — force AssetDatabase refresh
- `console-get-logs` — read Unity console (errors, warnings)
- `script-execute` — run C# code in editor

## Feishu Notifications

```python
# Via hermes gateway
from tools.send_message_tool import send_message_tool
send_message_tool({
    'action': 'send',
    'target': 'feishu:<chat_id>',
    'message': 'text\nMEDIA:/path/to/image.png'
})
```

Hermes Python: `/Users/davidagent/.hermes/hermes-agent/venv/bin/python3`

## Wiki Discipline

Knowledge goes into the wiki, not Claude Code auto-memory.
When you produce project knowledge (architecture decisions, lessons learned):

1. Write a wiki page with frontmatter to the correct department under `base/` or project overlay
2. Update `wiki/index.md`
3. Append to `wiki/log.md`
4. Add `[[wikilinks]]` to related pages

## Key Rules

1. Always use dispatch system for multi-step tasks — don't manually edit-test-repeat
2. All screenshots go through play mode (`gopoo-game-state`) not prefab preview
3. Compare against mockups at `~/Projects/gopoo-studio-project/design/mockups/`
4. Provider defaults to deepseek but currently needs `provider: cli` (no API key)
5. After code changes: refresh → compile check → rebuild prefab → play mode screenshot → feishu

## Session Discipline

Every session must follow this lifecycle:

### Session Start
1. Check `git status` — working directory must be clean. If not, resolve before starting new work.
2. Read memory index (`MEMORY.md`) for context from prior sessions.

### During Session
1. **Plan lifecycle**: completed plans move to `plans/archive/`. Failed plans get deleted or annotated.
2. **Commit often**: don't accumulate uncommitted changes across session boundaries.
3. **One concern per commit**: separate feature work from cleanup from docs.

### Session End Checklist
1. `git status` — nothing should be left uncommitted without reason.
2. Move completed/obsolete plans to `plans/archive/`.
3. If you learned something non-obvious, save it to memory (not wiki, not CLAUDE.md).
4. Write session handoff to wiki if there's in-progress work for the next session.

### Plan File Hygiene
- Active plans live in `plans/`. Finished/abandoned plans go to `plans/archive/`.
- Plan filenames: `{task_id}_{unix_timestamp}.yaml`
- Never leave more than 3 active plans in `plans/` — if you have more, something is wrong with scoping.
