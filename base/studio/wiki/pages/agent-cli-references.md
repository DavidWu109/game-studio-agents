---
title: Agent CLI Reference Implementations
created: 2026-05-25
updated: 2026-05-25
type: reference
tags: [agent, cli, tool-use, reference, architecture]
sources: [session discussion]
confidence: high
---

# Agent CLI Reference Implementations

Three open-source CLI agent implementations to study for our tool execution loop design.

## Repositories

| Repo | What to learn |
|------|--------------|
| [openai/codex](https://github.com/openai/codex) | OpenAI's CLI agent — tool definitions, execution sandbox, multi-step loop |
| [huangserva/claude-code-cli](https://github.com/huangserva/claude-code-cli) | Community Claude Code reimplementation — how CLI wraps API + tools |
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | Official Claude Code — tool schemas, safety model, context management |

## What to extract

1. **Tool schema format** — how they define read_file, write_file, bash tools
2. **Execution loop** — message → tool_calls → execute → append results → repeat
3. **Safety boundaries** — sandboxing, path restrictions, command filtering
4. **Context management** — how they handle long conversations and token limits
5. **Provider abstraction** — how they swap between models/providers

## Relevance

Our `core/tool_runner.py` (to be built) needs to implement the same loop pattern
but provider-agnostic. These repos show battle-tested approaches.

See also: [[provider-cost-analysis]], [[architecture-upgrade-plan]]
