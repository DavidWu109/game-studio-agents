---
title: Architecture Upgrade Plan — Agent Patterns Analysis
created: 2026-05-25
updated: 2026-05-25
type: comparison
tags: [architecture, react, plan-execute, agentic-search, hierarchical, decision]
sources: [analysis of core/dispatch.py, core/agent.py, core/search.py, autoresearch/loop.py, Anthropic agent patterns docs]
confidence: high
---

# Architecture Upgrade Plan

## Context

Evaluated whether to adopt four classic agent patterns (ReAct, Plan-and-Execute,
Hierarchical, Agentic Search) based on our actual system bottlenecks.

## Current Architecture (what we already have)

| Component | Pattern | Location |
|-----------|---------|----------|
| Art iteration | Custom feedback loop (Generate→Execute→Evaluate→Synthesize) | `autoresearch/{loop,generator,executor,evaluator,synthesis}.py` |
| Task execution | Parallel DAG executor with resource locks | `core/dispatch.py` |
| Knowledge | Two-layer wiki (base + project) with linear keyword search | `core/search.py` |
| Agents | 10 flat peers, no hierarchy, manual invocation | `core/agent.py` base class |
| Coordination | File-based message bus (designed, not wired) | `core/agent.py` send/check_inbox |

## Decisions

### ✅ Add: QA Feedback Loop (Interface #1)

**Classic pattern**: ReAct (Reasoning + Acting loop)
**Our adaptation**: At dispatch level, NOT inside individual agents

**Why dispatch level, not agent-internal**: Our actions are heavyweight — Art
takes 30 minutes, Engineering takes 5 minutes per cycle. A micro-loop inside
the agent would produce one observation every 3-30 minutes. The feedback
loop belongs at the task boundary where QA evaluates completed work.

**Mechanism**:
```
Engineering builds → QA scores 5.0 → dispatch finds upstream
→ agent.on_qa_feedback(task, qa_issues) → retry with feedback
→ QA re-scores → pass or escalate after MAX_QA_RETRIES(2)
```

**Interface locations**:
- `core/dispatch.py`: `_handle_qa_feedback()`, `QA_GATE_THRESHOLD = 7.5`, `MAX_QA_RETRIES = 2`
- `core/agent.py`: `on_qa_feedback(original_task, qa_result) → revised_task`

**Call site**: dispatch_loop, after QA task completes, before mark_status("done")

---

### ✅ Add: Dynamic Replan (Interface #2)

**Classic pattern**: Plan-and-Execute
**Our adaptation**: PjM agent replans; dispatch detects trigger conditions

**Why PjM owns replanning**: Replanning requires understanding project context,
priorities, and cross-department dependencies. That's PjM's domain knowledge.
dispatch.py is a dumb executor — it shouldn't make planning decisions.

**Mechanism**:
```
dispatch detects trigger (task blocked 30min / QA exhausted retries / art plateau)
→ PjM.replan(dispatch_data, trigger_reason)
→ PjM reads wiki + current state → outputs revised YAML
→ dispatch replaces planned tasks, continues
```

**Trigger conditions** (defined in `REPLAN_TRIGGERS`):
- `any_blocked_over_30min` — transient failure likely; try different approach
- `qa_failed_after_max_retries` — upstream can't self-correct; need scope change
- `all_art_plateaued` — ControlNet/seed/approach change needed

**Interface locations**:
- `core/dispatch.py`: `_check_replan_triggers()`, `_apply_replan()`, `REPLAN_TRIGGERS`
- `core/agent.py`: `replan(dispatch_data, trigger_reason) → revised_data`

---

### ✅ Add: Agentic Search (Interface #3)

**Classic pattern**: Anthropic's recommended search→evaluate→refine loop
**Our adaptation**: Two phases — fast filter (no LLM) first, agentic (LLM) later

**Why needed**: LESSONS.md is 1100+ lines. `generator.py` reads it linearly,
wasting context window and missing cross-task patterns. As wiki grows past
500 pages, keyword grep becomes noise.

**Phase A — keyword relevance filter** (no LLM, implement first):
```python
filter_by_task("blank_button_template", issue_keywords=["outline", "glossy"])
→ 8 relevant lessons (instead of 200 total)
```

**Phase B — agentic search** (LLM-in-the-loop, implement later):
```
question → initial search → LLM evaluates sufficiency
→ if insufficient: LLM refines query → search again
→ max 3 rounds → return consolidated results
```

**Interface locations**:
- `core/search.py`: `filter_by_task()`, `evaluate_results()`, `agentic_search()`
- `core/agent.py`: `load_relevant_lessons(task, current_issues)` — drop-in replacement for `load_lessons()`

---

### ✅ Add: Director Daemon (Interface #4)

**Classic pattern**: Hierarchical multi-agent
**Our adaptation**: Single coordinator daemon, flat agent peers (no middle managers)

**Why one level, not hierarchy**: 10 agents cooperating on one game don't need
middle management. One Director routing messages and triggering dispatches is
sufficient. Hierarchy adds latency and decision-making bottlenecks.

**Mechanism**:
```
StudioDaemon ticks every 30s:
  1. Scan dispatch inbox for new YAMLs → start dispatch_loop() threads
  2. Check active dispatches for replan triggers
  3. Route cross-agent messages (inbox → inbox)
  4. Tick each agent's loop() for background work
```

**Message routing table**:
| Message type | From | To |
|---|---|---|
| `asset_request` | Design/Marketing | Art |
| `asset_delivery` | Art | Engineering |
| `build_ready` | Engineering | QA |
| `bug_report` | QA | Engineering |
| `quality_gate_result` | QA | Studio + upstream |
| `wiki_insight` | any | target dept |
| `escalation` | any | Studio Director → human |
| `priority_update` | PM | PjM |

**Interface location**: `core/daemon.py` — StudioDaemon class

---

## ❌ Rejected Patterns

### Agent-internal ReAct micro-loops
**Why not**: Actions too heavy. Flux generation = 3 min, Unity build = 1 min.
A think→act→observe cycle at 3-minute granularity is worse than batch
generate→batch evaluate. Our AutoResearch loop already handles this better
with parallel sample generation + batch evaluation.

### RAG / embedding search
**Why not**: Wiki has < 500 pages. Keyword filter + tag search with relevance
scoring is sufficient and has zero maintenance cost. Embedding vectors need
re-indexing on every wiki edit, add a vector DB dependency, and don't
meaningfully improve recall at this scale. Revisit at 2000+ pages.

### Multi-layer hierarchy
**Why not**: Adding "team lead" agents between Director and department agents
creates indirection without value. 10 agents can coordinate through shared
wiki + message bus. Hierarchy is for when you have 50+ agents or need
budgetary/approval chains.

### Full unsupervised overnight operation
**Why not**: Safety risk. Art generation is sandboxed (ComfyUI only), but
Engineering writes to Unity project and QA captures screenshots in Play Mode.
An unsupervised loop that retries Engineering code 2x with QA feedback could
introduce subtle bugs. Daemon is opt-in via CLI, not always-on.

## Implementation Priority

| Week | Interface | Why first |
|------|-----------|-----------|
| 1 | QA feedback loop (#1) | Highest ROI — directly reduces manual "fix and re-score" cycles |
| 2 | Lesson relevance filter (#3 Phase A) | No LLM cost, immediate Art iteration improvement |
| 3 | Dynamic replan (#2) | Dispatch self-correction, reduces human babysitting |
| 4 | Daemon + message bus (#4) | Ties everything together for semi-autonomous operation |

## Files Changed

All 4 interfaces have stubs committed with full docstrings and call-site comments:
- `core/agent.py` — `on_qa_feedback()`, `replan()`, `load_relevant_lessons()`
- `core/dispatch.py` — `_handle_qa_feedback()`, `_check_replan_triggers()`, constants
- `core/search.py` — `filter_by_task()`, `evaluate_results()`, `agentic_search()`
- `core/daemon.py` — StudioDaemon class (new file)
- `ARCHITECTURE.md` — Full system diagram + 10 agent responsibilities (new file)

See also: [[roadmap]], [[dispatch-daemon]], [[dispatch-automation-plan]]
