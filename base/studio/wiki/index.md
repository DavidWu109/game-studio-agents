# Studio Wiki Index (Base)

> Cross-department coordination knowledge.
> Last updated: 2026-05-25 | Total pages: 12 | Skills: 2

## Architecture

- [[architecture-upgrade-plan]] — ReAct / Plan-Execute / Agentic Search / Hierarchical: what to add, what to reject, and why
- [[roadmap]] — 4-week plan: manual → automated agent team (10 agents)

## Dispatch

- [[dispatch-automation-plan]] — 5-phase plan (implemented in core/dispatch.py)
- [[dispatch-issues-v2]] — 7 issues found and fixed across dispatch runs
- [[dispatch-daemon]] — Hermes cron-based dispatch monitoring, crash recovery
- [[dispatch-lessons]] — First real multi-agent dispatch: what worked, what didn't

## Knowledge System

- [[knowledge-routing]] — Wiki vs skill vs raw, wiki discipline rules
- [[knowledge-scaling]] — Multi-genre studio: tag by capability not genre, dynamic retrieval plan
- [[wiki-lifecycle]] — Page retention, archival rules, lint checks
- [[memory-intercept-hook]] — SessionEnd hook: intercept Claude auto-memory → compare wiki → triage or discard

## Provider & Cost

- [[provider-cost-analysis]] — DeepSeek V4 Pro vs Claude API vs Max 20x: pricing, quality tiers, routing strategy
- [[agent-cli-references]] — openai/codex, claude-code-cli, anthropics/claude-code: tool loop & safety patterns to study

## Sessions

- [[session-2026-05-24]] — Foundation day: framework + dispatch + wiki + 35 commits

## Skills

- `task-dispatch/` — Decompose goals into agent tasks with dependency graph, parallel/sequential execution
- `industry-research/` — Two-layer research: industry standards (base) + competitor analysis (project)
