# Studio Wiki Log (Base)

> Chronological record of all wiki actions. Append-only.

## [2026-05-24] create | Wiki initialized
- Created: roadmap (framework direction and priorities)

## [2026-05-24] create | knowledge-routing
- Two tests: "how to do?" → skill, "true for any game?" → base

## [2026-05-25] update | roadmap rewritten
- Added month roadmap: 4-week plan from manual → automated team
- Added progress bar, weekly milestones, agent host mapping
- Updated priority from "fill knowledge" to "build autonomous agents"

## [2026-05-25] create | task-dispatch skill
- First dispatch skill: decompose goals → agent tasks → dependency graph
- Task YAML format, parallel/sequential rules, status tracking
- First real task file: gopoo/studio/tasks/gamepanel-fixes.yaml (6 tasks, 3 parallel)

## [2026-05-25] ingest | dispatch-lessons
- Source: first real gamepanel-fixes dispatch execution
- Created: dispatch-lessons.md (what worked, what didn't, automation gap table)
- Key finding: Feishu notifications + parallel execution worked; manual orchestration + no status persistence didn't

## [2026-05-25] create | dispatch-automation-plan
- 5-phase automation plan: status → deps → launcher → resources → loop
- Implementation order mapped to Week 2-3 of roadmap
- Success criteria: human writes YAML, system does everything else

## [2026-05-25] update | dispatch-issues-v2
- 6 issues total: single-thread, YAML match, permissions, panel name, validation, report screenshots
- All 6 fixed in core/dispatch.py + core/safety.py
- Verified: 12/12 tasks completed on v07-deliverable dispatch

## [2026-05-25] create | session-2026-05-24
- Foundation day summary: 35 commits, 18 wiki pages, 10 skills, 3 core modules
- Framework from zero to working dispatch runner in one session

## [2026-05-25] create | dispatch-daemon
- Hermes cron-based dispatch monitoring (5-min poll)
- Auto-reset stale in_progress tasks on startup (Issue #7 fix)
- Future upgrade path: custom daemon with file watcher

## [2026-05-25] create | wiki-lifecycle
- Page lifecycle: active → stale → archived (never deleted)
- What to archive (sessions, dispatch logs, version reviews) vs never archive (concepts, routing, skills)
- Lint checks: staleness (90d), orphans, contradictions, index drift, superseded content

## [2026-05-25] architecture-analysis | Evaluated ReAct/Plan-Execute/Agentic-Search/Hierarchical patterns against current system; committed 4 interface stubs + ARCHITECTURE.md; wrote [[architecture-upgrade-plan]]

## [2026-05-25] memory-intercept | Auto-memory purged, pending wiki triage
- `test_architecture_note`: QA feedback loop should retry upstream tasks when score < 7.5
- Action needed: review content, write to appropriate wiki page if valuable, discard if not

## [2026-05-25] memory-intercept | New content needs wiki triage
- `feedback_dispatch_lessons`: Dispatch automation parallel execution and dependency resolution lessons
- `project_new_marketing_plan`: Soft launch strategy for GoPoo beta on TestFlight before App Store submission
- Action: review inbox, write to appropriate dept wiki page, then delete from inbox

## [2026-05-25] memory-intercept | New content needs wiki triage
- `project_new_marketing_plan`: Soft launch strategy for GoPoo beta on TestFlight before App Store submission
- Action: review inbox, write to appropriate dept wiki page, then delete from inbox

## [2026-05-25] create | memory-intercept-hook
- SessionEnd hook: intercept auto-memory → keyword compare against wiki → triage new content to inbox or silent discard
- Files: comfyui_workflow/.claude/hooks/purge-memory.sh, .claude/settings.json

## [2026-05-25] update | session-2026-05-25 afternoon handoff
- GamePanel v0.7 fixes applied (not yet Unity-built), architecture stubs committed, memory-intercept hook live, wiki discipline in CLAUDE.md

## [2026-05-25] create | provider-cost-analysis
- Full cost comparison: DeepSeek V4 Pro vs Claude API vs Max 20x
- Key finding: DeepSeek V4 Pro ≈ Sonnet quality at 1/12 price; Max weekly cap limits real Opus throughput to ~20K/month
- Routing strategy: DeepSeek for 60% daily tasks, Max Opus for QA/architecture/creative
- Implementation plan: core/provider.py with fallback escalation

## [2026-05-25] create | agent-cli-references
- Studied openai/codex, claude-code-cli, anthropics/claude-code for tool loop patterns
- Key patterns: pre-inject context, decision-complete plans, tool call budget, batch reads

## [2026-05-25] implement | core/provider.py + core/tool_runner.py + core/planner.py
- Multi-provider routing (DeepSeek V4 Pro / CLI / SDK) with fallback escalation
- Tool execution loop (read/write/edit/bash) with safety enforcement
- Plan-and-Execute system: classify → gather knowledge → generate plan → execute with verify → replan
- Critical fix: deepseek-chat was V4 Flash not V4 Pro; V4 Pro needs reasoning_content passback

## [2026-05-25] implement | core/search.py filter_by_task
- Implemented Phase A knowledge retrieval — sprite-path-gotcha.md now correctly found
- Keyword extraction with stopwords, domain terms, CamelCase splitting

## [2026-05-25] update | session-2026-05-25 Session 3 handoff
- Multi-provider + plan-and-execute + tool runner all running
- Next: tune plan generation (only 1 step instead of 5-8), GamePanel rewrite, QA feedback loop
