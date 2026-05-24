---
title: Framework Roadmap and Direction
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [planning, priority, direction, decision]
sources: []
confidence: high
---

# Framework Direction (2026-05-24)

## Architecture Decision

Keep all 7 departments + core/ even though most are empty. The framework
is the target state — goal is to fill it with real content over the next month.

## Priority

1. **Fill knowledge through real pipeline runs** — every GoPoo task should
   write lessons back to the appropriate wiki layer
2. **Make AutoResearch iterate loop work across departments** — Art is proven,
   Engineering and Go Dev next
3. **Hermes/Feishu bridge is low priority** — "good enough" for occasional use
4. **core/agent.py stays skeleton** — implement when there's a real automation need

See also: [[knowledge-routing]], [[page-review-checklist]]

## What Makes This System Valuable

Not the Python code. Not the framework classes. The **markdown files themselves**.
Any LLM that reads the wiki pages and skill files immediately works better.
The system's value = accumulated knowledge in base/ and projects/.

## Key Principle

The system is LLM-agnostic. Today we use Claude Code CLI + Hermes. Tomorrow
it might be something else. The knowledge layer (wiki + skills) survives
any tool change because it's just markdown.

## Repos

| Repo | Visibility | Purpose |
|---|---|---|
| game-studio-agents | Public | Framework + base knowledge |
| gopoo-studio-project | Private | GoPoo-specific knowledge |

## Current Integration Points

- `synthesis.py` → writes to LESSONS.md AND project wiki/skills
- `generator.py` → reads from base wiki + project wiki
- `evaluator.py` → references style-anchor from project wiki
- `CLAUDE.md` in comfyui_workflow → points to all knowledge sources
