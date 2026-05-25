# Game Studio Agents — Architecture & Agent Responsibilities

## System Overview

```
Human Direction
    │
    ▼
┌─────────┐     ┌──────────┐     ┌──────────────┐
│   PM    │────▶│   PjM    │────▶│  Dispatch     │
│ (what)  │     │ (plan)   │     │  (execute)    │
└─────────┘     └──────────┘     └──────┬───────┘
                                        │
                    ┌───────────────────┬┴──────────────────┐
                    ▼                   ▼                    ▼
              ┌──────────┐       ┌───────────┐       ┌──────────┐
              │   Art    │       │Engineering│       │  Design  │
              │(generate)│       │  (build)  │       │ (mockup) │
              └────┬─────┘       └─────┬─────┘       └──────────┘
                   │                   │
                   └──────┬────────────┘
                          ▼
                    ┌──────────┐     ┌──────────┐
                    │    QA    │────▶│  Studio  │────▶ Feishu / Human
                    │ (judge)  │     │ (report) │
                    └──────────┘     └──────────┘
```

## Agent Responsibilities (10 departments)

### PM — Product Manager
**Owner**: Requirements and acceptance criteria
**Input**: Human direction (vague, creative, strategic)
**Output**: Structured requirements YAML with priorities (P0-P3)

| Operation | Description |
|-----------|------------|
| Decompose | Human vision → measurable requirements with acceptance criteria |
| Prioritize | Assign P0-P3 based on user impact and dependencies |
| Validate | Check that completed work matches acceptance criteria |

**Boundary**: PM says WHAT to build. Does not say HOW (that's Design/Engineering).
**Message types**: Sends `priority_update` to PjM. Receives nothing (human-driven).

---

### PjM — Project Manager
**Owner**: Execution plan and schedule
**Input**: PM requirements
**Output**: Dispatch YAML (task DAG with agent assignments)

| Operation | Description |
|-----------|------------|
| Plan | Requirements → task breakdown → dependency resolution → time estimates |
| Dispatch | Write YAML with `depends_on` chains and agent assignments |
| Monitor | Track progress, detect blockers, update estimates |
| **Replan** | *(Interface #2)* Dynamically revise task DAG when conditions change |

**Boundary**: PjM plans WHEN and WHO. Does not do the work itself.
**Message types**: Sends dispatch YAML to Studio Director. Receives `priority_update` from PM.

**Replan triggers** (Interface #2, not yet implemented):
- Any task blocked > 30 minutes
- QA failed after MAX_QA_RETRIES
- All art tasks plateaued
- Human override

---

### Studio Director
**Owner**: Cross-department coordination and reporting
**Input**: Dispatch YAML from PjM, results from all agents
**Output**: Feishu reports, escalation notifications

| Operation | Description |
|-----------|------------|
| Execute dispatch | Run `dispatch_loop()` — resolve dependencies, launch agents in parallel |
| Route messages | Deliver cross-agent messages from inbox to inbox |
| Escalate | Surface blocked/failed tasks to human attention |
| Report | Collect screenshots + scores → build comparison grid → send to Feishu |

**Boundary**: Studio Director routes and reports. Does not make creative or technical decisions.
**Message types**: Receives `escalation` from any agent. Sends notifications to Feishu.

**Daemon interface** (Interface #4, not yet implemented):
- `core/daemon.py` — StudioDaemon class
- Watches for new dispatch YAMLs
- Ticks each agent's `loop()` on schedule
- Routes messages across inboxes

---

### Art
**Owner**: Visual assets (sprites, icons, backgrounds, UI elements)
**Input**: Design mockups, style-anchor spec, task YAML
**Output**: PNG assets deployed to Unity `Assets/Art/`

| Operation | Description |
|-----------|------------|
| Iterate (AutoResearch) | Generate → Execute (Flux/ControlNet) → Evaluate (Claude vision) → Synthesize (LESSONS.md) |
| Postprocess | Smart color-key (HSV, not rembg), feather, trim, pad to canvas |
| Deploy | Copy final PNG to Unity project with `.bak` backup |

**Boundary**: Art owns visual style, colors, and asset quality. Does not own layout structure (that's Design).
**Tools**: ComfyUI (Flux + Union ControlNet), Claude vision evaluator
**Message types**: Receives `asset_request` from Design/Engineering. Sends `asset_delivery` to Engineering.

**Key wiki pages**:
- `base/art/wiki/pages/flux-priors.md` — Flux model behaviors and token biases
- `base/art/wiki/pages/controlnet-guide.md` — thick mask = thick outline
- `base/art/wiki/pages/color-keying.md` — HSV post-processing
- `project/art/wiki/pages/style-anchor.md` — CotL × poop × deep purple

---

### Design
**Owner**: Game rules, UX flow, layout structure, mockups
**Input**: PM requirements, player feedback
**Output**: Mockup PNGs, layout spec JSON, balance parameters

| Operation | Description |
|-----------|------------|
| Layout | Define UI hierarchy, element positions, information architecture |
| Mockup | Generate pixel-accurate mockups (PIL composites via Claude) |
| Balance | Card values, scoring rules, Monte Carlo simulation |
| Self-review | Checklist verification before handing off to Engineering |

**Boundary**: Design owns structure and flow. Art owns the visual style.
**Message types**: Sends `asset_request` to Art (need new asset for mockup). Receives `wiki_insight` from QA (usability issues).

---

### Engineering
**Owner**: Code quality, Unity integration, build automation
**Input**: Design mockups + Art assets + layout spec JSON
**Output**: Unity prefabs, C# builders, working game panels

| Operation | Description |
|-----------|------------|
| Build | Read layout spec → generate/update C# panel builders → compile → save prefab |
| Integrate | Import art assets, configure sprite settings, wire up references |
| Automate | Sync scripts (e.g. `sync_layout_spec.py`), build pipelines |

**Boundary**: Engineering owns code and Unity integration. Does not own visual style (Art) or layout decisions (Design).
**Tools**: Unity/Tuanjie MCP, `claude -p` for code generation
**Message types**: Receives `asset_delivery` from Art. Sends `build_ready` to QA.

**Key gotchas** (from wiki):
- `Assets/Refresh` required to recompile `.cs` files
- `Resources/Art/` path for sprites (not `Art/` — Tuanjie bug)
- Validate `spriteBorder < image size` before deploy

---

### QA
**Owner**: Quality assurance and gate keeping
**Input**: Built prefabs from Engineering
**Output**: Screenshot + dual-layer score + issues list

| Operation | Description |
|-----------|------------|
| Capture | Build panel → Play Mode → ScreenCapture → 2x resolution PNG |
| Evaluate | Claude vision scores 8 dimensions → component scores + weighted overall |
| Gate | Pass ≥ 8.0, warning 6-8, fail < 6. Any component < 6 blocks shipment |

**Boundary**: QA judges quality. Does not fix issues (sends feedback to upstream agent).
**Message types**: Sends `quality_gate_result` to Studio + upstream agent.

**QA feedback loop** (Interface #1, not yet implemented):
- Score below `QA_GATE_THRESHOLD` (7.5) → find upstream task → call `agent.on_qa_feedback()`
- Upstream agent revises its work → QA re-evaluates
- Max `MAX_QA_RETRIES` (2) before escalating to human

**Scoring dimensions**:
rendering, text, touch, layout, hierarchy, players, content, consistency

---

### Go Dev
**Owner**: Game server (Go), REST/WebSocket APIs, multiplayer
**Input**: Design game rules, Engineering client requirements
**Output**: Working game server on port 9090

| Operation | Description |
|-----------|------------|
| API | REST endpoints for lobby, game state, player actions |
| Realtime | WebSocket for turn-based multiplayer |
| State | Game state machine, deck management, scoring logic |

**Boundary**: Go Dev owns server logic. Client-side game logic mirror is Engineering's responsibility.
**Message types**: Sends `build_ready` to QA. Receives `bug_report` from QA.

---

### Creative Director (CD)
**Owner**: Aesthetic vision and creative judgment
**Input**: Human "gut feeling" reactions ("I don't like it", "feels off")
**Output**: Concrete analysis of WHY + actionable options for Art/Design

| Operation | Description |
|-----------|------------|
| Interpret | Translate vague human feelings → specific aesthetic criteria |
| Judge | Evaluate Art output against style anchor and brand consistency |
| Direct | Propose 2-3 concrete options with recommendation when stuck |

**Boundary**: CD interprets vision. Does not generate assets (Art) or write requirements (PM).
**Message types**: Sends `wiki_insight` to Art/Design (style guidance).

---

### Marketing
**Owner**: Player acquisition, App Store presence, social content
**Input**: Final assets from Art, quality results from QA
**Output**: Store screenshots, promotional materials, social posts

| Operation | Description |
|-----------|------------|
| Assets | Request promotional art from Art department |
| Content | Generate store descriptions, social media copy |
| Analytics | Track store performance metrics (when implemented) |

**Boundary**: Marketing owns external-facing materials. Does not modify in-game assets.
**Message types**: Sends `asset_request` to Art. Receives `asset_delivery` from Art, `quality_gate_result` from QA.

---

## Architecture Interfaces (Stubs)

### Interface #1: QA Feedback Loop (ReAct at dispatch level)
**Location**: `core/dispatch.py` → `_handle_qa_feedback()`, `core/agent.py` → `on_qa_feedback()`
**Pattern**: Execute → Evaluate → Retry (not agent-internal, but dispatch-level)
**Why at dispatch level**: Actions are heavyweight (Art 30min, Engineering 5min). Micro-loops inside agents would be too slow. The feedback loop operates across task boundaries.

```
Engineering builds → QA scores 5.0 → dispatch retries Engineering with QA issues → QA re-scores
```

### Interface #2: Dynamic Replan (Plan-and-Execute)
**Location**: `core/dispatch.py` → `_check_replan_triggers()`, `core/agent.py` → `replan()`
**Pattern**: Plan → Execute → Monitor → Replan (PjM is the planner, dispatch is the executor)
**Why PjM owns this**: Replanning requires understanding project context, priorities, and dependencies — that's PjM's domain knowledge.

```
dispatch detects "art blocked 30min" → PjM reads wiki + state → PjM outputs revised YAML → dispatch continues
```

### Interface #3: Agentic Search
**Location**: `core/search.py` → `agentic_search()`, `filter_by_task()`, `evaluate_results()`
**Pattern**: Search → Evaluate → Refine (LLM-in-the-loop retrieval)
**Why needed**: LESSONS.md is 1100+ lines and growing. Linear scan wastes context window and misses relevant cross-task patterns.

```
generator needs lessons → filter_by_task("button", ["glossy"]) → 8 relevant lessons (not 200)
```

### Interface #4: Daemon + Message Bus
**Location**: `core/daemon.py` → `StudioDaemon`
**Pattern**: Hierarchical coordination (Director daemon → department agents)
**Why separate from dispatch**: Dispatch runs one YAML. Daemon watches for new YAMLs, routes messages, and ticks agent background work.

```
daemon ticks → finds new dispatch YAML → starts dispatch_loop() → routes messages → ticks agents
```

## Knowledge Architecture

```
game-studio-agents/
  base/                          ← Universal (any game)
    art/
      AGENTS.md                  ← Agent schema
      wiki/pages/*.md            ← Declarative knowledge
      skills/*/SKILL.md          ← Procedural memory
    engineering/
    design/
    qa/
    ...

gopoo-studio-project/            ← Project-specific (GoPoo)
    art/
      AGENTS.md                  ← Project overlay
      wiki/pages/*.md            ← GoPoo-specific lessons
      skills/*/                  ← GoPoo-specific procedures
    engineering/
    ...
```

**Two-layer read order**: Agent reads base first, then project overlay.
**Write classification**: `classify_lesson()` decides base vs. project.
**Compounding**: Base layer is the studio's lasting asset. Every game enriches base; next game starts richer.

## Core Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| `core/agent.py` | 350+ | Base class: knowledge ops, iterate loop, message bus, interface stubs |
| `core/dispatch.py` | 730+ | Task runner: dependency DAG, parallel execution, resource locks, interface stubs |
| `core/search.py` | 200+ | Wiki search: tag/content + agentic search stubs |
| `core/safety.py` | 226 | Guardrails: per-agent write boundaries, forbidden commands |
| `core/daemon.py` | 160+ | Director daemon stub: watches dispatches, routes messages, ticks agents |
