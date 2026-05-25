---
title: Framework Roadmap and Direction
created: 2026-05-24
updated: 2026-05-25
type: concept
tags: [planning, priority, direction, decision]
sources: []
confidence: high
---

# Framework Direction

## Target (2026-06-25)

A self-running agent team where each department agent has its own loop,
autonomously ingests sources, iterates on tasks, lints its wiki, and
learns from every interaction. Human role = creative direction + approval.

## Where We Are Now (2026-05-25)

```
Knowledge layer:   ████████░░  80% — wiki + skills exist, actively used
Integration:       ██████░░░░  60% — synthesis/generator read/write wiki
Agent automation:  █░░░░░░░░░  10% — core/agent.py is skeleton, all ops manual
Team coordination: ░░░░░░░░░░   0% — no agent-to-agent communication
```

## Month Roadmap: Manual → Automated Team

### Week 1 (done): Knowledge Foundation
- ✅ Two-layer wiki architecture (base + project)
- ✅ Migrate existing knowledge from comfyui_workflow
- ✅ Art pipeline reads/writes wiki (synthesis.py + generator.py)
- ✅ LLM Wiki compliance (index, log, wikilinks, frontmatter)
- ✅ Evaluator calibration lessons (holistic + dimensional scoring)
- ✅ Page review checklist (8 sections, universal)

### Week 2: First Autonomous Agent (Art)
- [ ] Implement Art agent loop: watch for new tasks → iterate → evaluate → synthesize
- [ ] Wiki lint script (the audit we ran manually, automated as cron)
- [ ] Overnight batch: Art agent runs task YAML queue unattended
- [ ] Auto-commit wiki changes after each iterate session
- [ ] Feishu notification on pass/fail (already working via API)

### Week 3: Engineering + QA Agents
- [ ] Engineering agent: watch for asset_delivery → reimport → build → test → report
- [ ] QA agent: post-build screenshot → run page-review-checklist → score → report
- [ ] Inter-agent messages: Art→Engineering (asset_delivery), Engineering→QA (build_ready)
- [ ] File-based message bus (inbox/ directories, already designed)

### Week 4: Team Orchestration
- [ ] Studio Director agent: daily status collection from all agents
- [ ] Milestone tracking: auto-update from agent reports
- [ ] Go Dev agent: watch for design changes → implement → test
- [ ] Cross-agent wiki insight sharing

## Team Structure (10 agents)

```
Human (老板: approve/reject + gut feelings)
  ↓
Creative Director (分析"为什么不好" → 创意方案 + 推荐)
  ↓
Product Manager (方案→需求→验收标准)
  ↓
Project Manager (需求→dispatch YAML→跟进度)
  ↓
Studio Director (执行 dispatch→资源协调→飞书通知)
  ↓
┌─────────┬──────────────┬──────────┬─────────┬──────────┐
│  Design │     Art      │Engineering│  Go Dev │    QA    │
│ mockups │   assets     │  Unity   │  server │  review  │
│ UX/flow │  Flux/CN     │  C#/MCP  │  Go API │ compare  │
│ states  │  postprocess │  prefab  │  test   │  score   │
└─────────┴──────────────┴──────────┴─────────┴──────────┘
        ↑                                         │
        └────── Marketing (later) ────────────────┘
```

## Automation Approach

Not building a custom agent runtime. Using existing tools as agent hosts:

| Agent | Host | Loop Trigger |
|---|---|---|
| Product Manager | Claude Code CLI | human direction, QA results |
| Project Manager | Claude Code CLI | PM requirements → write YAML, monitor dispatch |
| Art | Claude Code CLI (`claude -p`) | cron / task YAML queue |
| Design | Claude Code CLI + PIL | PM requirement → mockup |
| Engineering | Claude Code CLI | message from Art/Design |
| QA | Script + Claude vision | post-build hook |
| Studio Director | core/dispatch.py | PjM's YAML |
| Go Dev | Claude Code CLI | message from Design/PM |

Each agent reads its AGENTS.md (schema) + wiki + skills before acting.
Each agent writes back to wiki + skills after acting.
The knowledge layer IS the coordination mechanism — agents don't need
real-time communication, they read each other's wiki.

## Key Principle

The system is LLM-agnostic. The knowledge layer (wiki + skills) survives
any tool change. Agents can be Claude Code today, Hermes tomorrow,
a custom runtime next month. The markdown is the lasting asset.

## Repos

| Repo | Visibility | Purpose |
|---|---|---|
| game-studio-agents | Public | Framework + base knowledge |
| gopoo-studio-project | Private | GoPoo-specific knowledge |

See also: [[knowledge-routing]], [[page-review-checklist]]
