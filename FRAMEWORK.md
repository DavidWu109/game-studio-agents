# Self-Learning Agent Framework — Game Studio Foundation

> Sources:
> - [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — persistent compounding knowledge
> - [Hermes Agent](https://github.com/nousresearch/hermes-agent) — closed learning loop, skills, curator
> Adapted for: GoPoo Game Studio multi-agent system
> Created: 2026-05-24

---

## Zero: Two Ideas, One System

**Karpathy's LLM Wiki**: knowledge is compiled once into an interlinked wiki and kept
current — not re-derived from scratch on every query. The wiki is a persistent,
compounding artifact. The LLM writes and maintains it; you curate sources and direct
analysis.

**Hermes Agent's Learning Loop**: after every conversation turn, the agent spawns a
background review that asks "what should I remember? what skill should I create or
improve?" Knowledge flows into two stores: **memory** (who the user is, preferences,
state) and **skills** (how to do a class of task). A background **curator** periodically
audits, archives stale skills, and consolidates overlapping ones.

Combined: each agent in the studio maintains a **wiki** (Karpathy's compounding
knowledge) AND a **skill library** (Hermes' procedural memory). The wiki is what the
agent knows; the skills are what the agent knows how to do. Both compound over time.

---

## One: Three-Layer Architecture (per agent)

```
┌─────────────────────────────────────────────┐
│  Schema (AGENTS.md)                         │
│  Structure rules, conventions, workflows.   │
│  The agent's operating manual.              │
├─────────────────────────────────────────────┤
│  Wiki (wiki/)          │  Skills (skills/)  │
│  Declarative knowledge │  Procedural memory │
│  Entity/concept pages  │  SKILL.md + refs   │
│  Cross-referenced,     │  Self-improving,   │
│  indexed, linted       │  curated, versioned│
├─────────────────────────────────────────────┤
│  Raw Sources (raw/)                         │
│  Immutable. Never modified by the agent.    │
│  Source of truth.                           │
└─────────────────────────────────────────────┘
```

### Raw Sources — immutable inputs

The agent reads but never modifies. Every source gets frontmatter:

```yaml
---
source_url: https://...        # origin, if applicable
ingested: 2026-05-24
sha256: <hex of body content>  # detect drift on re-ingest
---
```

### Wiki — declarative knowledge (what the agent knows)

LLM-generated markdown pages. Entity pages, concept pages, comparisons,
synthesis. Interlinked with `[[wikilinks]]`. The agent owns this entirely:
creates, updates, cross-references, keeps consistent.

Navigation files:
- **index.md** — content catalog. Sectioned by type. One-line summaries.
  The LLM reads this first to find relevant pages for any query.
- **log.md** — chronological append-only record. Parseable:
  `grep "^## \[" log.md | tail -5`

Page types: entity, concept, comparison, query, summary.

Required frontmatter:
```yaml
---
title: Page Title
created: 2026-05-24
updated: 2026-05-24
type: entity | concept | comparison | query | summary
tags: [from taxonomy in SCHEMA.md]
sources: [raw/articles/source-name.md]
confidence: high | medium | low
---
```

### Skills — procedural memory (what the agent knows how to do)

Inspired by Hermes Agent's skill system. Each skill is a directory:

```
skills/
├── <skill-name>/
│   ├── SKILL.md          # instructions, when to use, procedure, pitfalls
│   ├── references/       # knowledge banks, session-specific detail
│   ├── templates/        # starter files to copy and modify
│   └── scripts/          # runnable actions the skill can invoke
```

SKILL.md frontmatter:
```yaml
---
name: skill-name
description: "One sentence, ≤60 chars."
version: 1.0.0
created_by: agent | human
tags: [relevant tags]
---
```

Skills vs wiki pages:
- **Wiki page**: "ControlNet Union Pro 2.0 requires a VAE input" (fact)
- **Skill**: "How to generate a GoPoo button asset" (procedure, with steps,
  pitfalls, and templates)

---

## Two: The Learning Loop

After every meaningful interaction, the agent runs a background review.
This is the mechanism that makes the system self-improving.

```
┌──────────────────────────────────────────────────────────┐
│                    Conversation Turn                      │
│  User message → Agent thinks → Uses tools → Responds     │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              Background Review (post-turn)                │
│                                                          │
│  The agent asks itself:                                  │
│                                                          │
│  MEMORY: Did the user reveal preferences, persona,       │
│  expectations? → Save to wiki (entity/concept pages)     │
│                                                          │
│  SKILLS: Did a technique emerge? Did a skill fail?       │
│  Did the user correct my approach? →                     │
│    1. Update a loaded skill (first choice)               │
│    2. Update an existing umbrella skill                   │
│    3. Add a reference/template under existing skill      │
│    4. Create a new class-level skill (last resort)       │
│                                                          │
│  WIKI: Should any wiki page be updated with new          │
│  information from this conversation?                     │
│                                                          │
│  Nothing to save? → Say so and stop. But this should     │
│  NOT be the default — most sessions produce learning.    │
└──────────────────────────────────────────────────────────┘
```

### What to capture vs what to skip

**Capture:**
- User corrections (style, approach, workflow) → skill update
- Non-trivial techniques, workarounds, debugging paths → skill or wiki
- Facts about the domain → wiki page
- User preferences and persona → wiki entity page
- Contradictions with existing knowledge → wiki update with both positions

**Do NOT capture:**
- Environment-dependent failures (missing binaries, unconfigured creds)
- Negative claims about tools ("X is broken") — these harden into refusals
- Transient errors that resolved during the session
- One-off task narratives that aren't a class of work

---

## Three: The Curator (background maintenance)

Periodically, the agent runs a curator pass on its skill library:

```
┌──────────────────────────────────────────────┐
│  Curator (runs on idle, every N hours)        │
│                                              │
│  1. Track skill usage (use_count, last_used) │
│  2. Auto-transition lifecycle states:        │
│     active → stale (30 days unused)          │
│     stale → archived (90 days unused)        │
│  3. Never delete — only archive (recoverable)│
│  4. Consolidate overlapping skills           │
│  5. Pinned skills skip all auto-transitions  │
│  6. Only touches agent-created skills        │
│     (human-authored skills are protected)    │
└──────────────────────────────────────────────┘
```

Combined with wiki lint:

```
┌──────────────────────────────────────────────┐
│  Wiki Lint (periodic health check)           │
│                                              │
│  1. Contradictions between pages             │
│  2. Stale claims superseded by newer sources │
│  3. Orphan pages (no inbound links)          │
│  4. Missing pages (referenced but not exist) │
│  5. Missing cross-references                 │
│  6. Source drift (sha256 mismatch)           │
│  7. Oversized pages (>200 lines → split)     │
│  8. Tag audit (tags not in taxonomy)         │
│  9. Log rotation (>500 entries → rotate)     │
│  10. confidence: low pages needing review    │
└──────────────────────────────────────────────┘
```

---

## Four: The Iterative Loop (AutoResearch)

Inspired by [Karpathy's AutoResearch](https://github.com/karpathy/autoresearch).
A closed feedback loop where the output of one round directly informs the next.
This is a **framework-level capability** shared by all agents, not specific to
any department.

### The Universal Pattern

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐
│Generator │ → │Executor  │ → │Evaluator  │ → │Synthesis │ ─┐
│(revise   │    │(run it)  │    │(judge     │    │(distill  │  │
│ input)   │    │          │    │ output)   │    │ lessons) │  │
└──────────┘    └──────────┘    └───────────┘    └──────────┘  │
     ▲                                                         │
     └─────────────────────────────────────────────────────────┘
```

### Per-Agent Instantiation

| Agent | Generator | Executor | Evaluator | Synthesis |
|---|---|---|---|---|
| **Art** | LLM revises Flux prompt | ComfyUI generates image | Claude vision scores against checklist | Append failure mode to wiki, update prompt skill |
| **Unity Dev** | LLM revises C# code | `Assets/Refresh` → Build → Play | Compile errors + test assertions + screenshot diff | Append bug pattern to wiki, update coding skill |
| **Go Dev** | LLM revises Go code | `go build` + `go test` + run server | Test pass/fail + coverage + benchmark | Append API pattern to wiki, update service skill |
| **Design** | LLM adjusts card values | Monte Carlo simulation (1000 games) | Win rate + card usage rate + fun metrics | Update balance wiki, adjust simulation skill |
| **QA** | LLM writes/revises test case | Run test suite + screenshot | Pass/fail + regression diff + coverage | Update test wiki, refine test skill |
| **Marketing** | LLM revises copy/layout | Generate image + render text | A/B click-through prediction | Update playbook wiki, refine template skill |

### Loop Behavior (validated by Art agent, applies to all)

- **Rounds 1-3**: fast improvement (big-direction fixes)
- **Round 4+**: diminishing returns, may oscillate (fix A breaks B)
- **Ceiling detection**: if score plateaus for 3 consecutive rounds,
  the problem is architectural — escalate to human or switch strategy
- **max_iterations**: hard cap per task (4-8 rounds), prevents spin
- **Synthesis is the compounding mechanism**: every round's lessons
  flow into the wiki and skills, benefiting ALL future tasks

### Integration with Wiki + Learning Loop

```
AutoResearch round N
    │
    ├─→ Evaluator finds issue "spriteBorder > image size"
    │
    ├─→ Synthesis writes to wiki: engineering/wiki/pages/unity-gotchas.md
    │   (declarative: "spriteBorder L+R must < width")
    │
    ├─→ Synthesis updates skill: engineering/skills/asset-integration/
    │   (procedural: step added to SKILL.md, pitfall documented)
    │
    └─→ Next round's Generator reads BOTH wiki + skill before revising
         (avoids repeating the same mistake)
```

The AutoResearch loop **produces** knowledge. The wiki **stores** it.
The learning loop **distributes** it. The curator **maintains** it.
Four mechanisms, one compounding system.

### Task Definition (YAML)

```yaml
task_id: fix_lobby_panel
agent: engineering
max_iterations: 6
samples_per_round: 1

target: "Lobby panel renders correctly with room items, no overlap"

checklist:
  - "Compiles without errors"
  - "Room items fill ≥80% panel width"
  - "No element overlap"
  - "FULL status visible in red"
  - "Back button deprioritized"

executor:
  steps:
    - "Assets/Refresh"           # recompile
    - "GoPoo/Build Panels/Lobby" # rebuild prefab
    - "GoPoo/Preview/Lobby"      # preview
    - "gopoo-screenshot"         # capture

evaluator:
  type: vision                   # Claude vision scoring
  pass_threshold: 8.0
```

For code agents (Unity/Go), the executor steps are different but the
YAML structure is the same:

```yaml
task_id: implement_poo_story
agent: go_dev
max_iterations: 6

target: "PooStory endpoint returns story text for card combination"

checklist:
  - "go build succeeds"
  - "go test ./handlers/... passes"
  - "POST /api/poo-story returns 200 with valid JSON"
  - "Story text references both cards"
  - "Response time < 200ms"

executor:
  steps:
    - "go build ./..."
    - "go test ./handlers/... -v"
    - "curl -X POST localhost:9090/api/poo-story -d '{...}'"

evaluator:
  type: structured               # parse test output + curl response
  pass_threshold: all_pass       # all checklist items must pass
```

---

## Five: Six Operations

### 1. Ingest

New source arrives → read → extract → integrate:

1. Save to `raw/` with frontmatter (immutable)
2. Check what already exists (read index, search wiki)
3. Write/update wiki pages (entities, concepts, cross-refs)
4. Update index.md and log.md
5. If a procedure emerged, update or create a skill
6. A single source may touch 10-15 wiki pages — this is normal

### 2. Query

Question against the wiki:

1. Read index.md → find relevant pages
2. Read those pages
3. Synthesize answer with citations `[[page-name]]`
4. If answer is substantial, file back as a new wiki page
5. Update log.md

### 3. Iterate (AutoResearch loop)

Closed feedback loop for production tasks:

1. Generator reads wiki + skills → produces input (prompt/code/config)
2. Executor runs it (ComfyUI/compiler/test suite/simulator)
3. Evaluator judges output against checklist
4. Synthesis distills lessons → wiki + skills
5. If passed threshold → done; if plateaued → escalate; else → round N+1

### 4. Lint

Periodic health check on wiki + skills (see section Three).

### 5. Learn (post-turn background review)

After each conversation turn (see section Two).

### 6. Curate (periodic skill maintenance)

Background skill lifecycle management (see section Three).

---

## Five: Two-Layer Knowledge Architecture

Knowledge splits into two layers: **base** (universal, carries across projects)
and **project** (specific to one game). When an agent works, it reads both.
When it learns, it decides which layer to write to.

### The Rule

```
Is this lesson true regardless of which game we're making?
  YES → base     "Unity 9-slice border must < image size"
                  "Flux negative prompt is ineffective at CFG=1"
                  "Go test table-driven pattern"
  NO  → project  "GoPoo uses CotL style with deep purple palette"
                  "Card #23 Diarrhea triggers at 15% probability"
                  "GoPoo server runs on port 9090"
```

### Directory Structure

```
game-studio-agents/
│
├── FRAMEWORK.md                 # this file (the meta-framework)
├── README.md
├── core/                        # framework code (open-source)
│   ├── agent.py                 # StudioAgent base class
│   ├── wiki.py                  # Wiki operations
│   ├── skills.py                # Skill management + curator
│   ├── loop.py                  # AutoResearch iterate loop
│   └── bus.py                   # Cross-agent message bus
│
├── base/                        # BASE KNOWLEDGE (universal, cross-project)
│   │                            # This layer is the studio's lasting asset.
│   │                            # Carries to every future game.
│   │
│   ├── art/
│   │   ├── AGENTS.md            # schema for art agent (universal part)
│   │   ├── wiki/
│   │   │   ├── index.md
│   │   │   ├── log.md
│   │   │   └── pages/
│   │   │       ├── flux-priors.md           # "Flux T5 binds 'pill' to medicine"
│   │   │       ├── controlnet-guide.md      # "thick mask = thick outline output"
│   │   │       ├── lora-behavior.md         # "LoRA overrides prompt semantics"
│   │   │       ├── color-keying.md          # "HSV > rembg for UI elements"
│   │   │       └── prompt-engineering.md    # "no negative prompt at CFG=1"
│   │   └── skills/
│   │       ├── generate-button/             # universal button generation skill
│   │       ├── autoresearch-loop/           # the iterate loop itself
│   │       └── asset-postprocess/           # trim, pad, color-key
│   │
│   ├── engineering/
│   │   ├── AGENTS.md
│   │   ├── wiki/
│   │   │   └── pages/
│   │   │       ├── unity-gotchas.md         # "Assets/Refresh to recompile"
│   │   │       ├── 9-slice-rules.md         # "spriteBorder < image size"
│   │   │       ├── tmp-sdf-fonts.md         # "Dynamic atlas needs TryAddCharacters"
│   │   │       └── mcp-integration.md       # "Tuanjie process name ≠ Unity"
│   │   └── skills/
│   │       ├── unity-build-pipeline/
│   │       ├── asset-integration/
│   │       └── screenshot-capture/
│   │
│   ├── go-dev/
│   │   ├── AGENTS.md
│   │   ├── wiki/
│   │   │   └── pages/
│   │   │       ├── go-patterns.md
│   │   │       ├── testing-patterns.md
│   │   │       └── server-architecture.md
│   │   └── skills/
│   │       ├── api-endpoint/
│   │       └── websocket-handler/
│   │
│   ├── design/
│   │   ├── AGENTS.md
│   │   ├── wiki/
│   │   └── skills/
│   │       └── balance-simulation/
│   │
│   ├── qa/
│   │   ├── AGENTS.md
│   │   ├── wiki/
│   │   │   └── pages/
│   │   │       ├── ui-scoring-system.md     # dual-layer scoring method
│   │   │       └── touch-target-rules.md    # ≥48pt on mobile
│   │   └── skills/
│   │       ├── ui-review/                   # universal UI review checklist
│   │       └── screenshot-compare/
│   │
│   ├── marketing/
│   │   ├── AGENTS.md
│   │   ├── wiki/
│   │   └── skills/
│   │
│   └── studio/
│       ├── AGENTS.md
│       ├── wiki/
│       └── skills/
│           ├── daily-standup/
│           └── milestone-review/
│
└── projects/                    # PROJECT KNOWLEDGE (game-specific)
    │
    ├── gopoo/                   # GoPoo: 2-4 player poop card game
    │   ├── PROJECT.md           # project identity, goals, timeline
    │   │
    │   ├── art/
    │   │   ├── AGENTS.md        # project overlay (extends base/art/AGENTS.md)
    │   │   ├── raw/
    │   │   │   ├── references/  # CotL screenshots, mood boards
    │   │   │   ├── flux_outputs/
    │   │   │   └── evaluations/
    │   │   ├── wiki/
    │   │   │   ├── index.md
    │   │   │   ├── log.md
    │   │   │   └── pages/
    │   │   │       ├── style-anchor.md      # "CotL × poop × dark purple"
    │   │   │       ├── color-tokens.md      # GoPoo specific palette
    │   │   │       ├── poop-mascot.md       # mascot design specs
    │   │   │       └── button-iterations.md # GoPoo button history
    │   │   └── skills/
    │   │       ├── gopoo-button/            # GoPoo-specific button generation
    │   │       └── gopoo-emotion/           # poop mascot emotion generation
    │   │
    │   ├── engineering/
    │   │   ├── AGENTS.md
    │   │   ├── wiki/
    │   │   │   └── pages/
    │   │   │       ├── architecture.md      # GoPoo client architecture
    │   │   │       ├── panel-builder.md     # GoPoo panel build system
    │   │   │       └── asset-paths.md       # GoPoo asset path mapping
    │   │   └── skills/
    │   │       └── gopoo-panel-build/
    │   │
    │   ├── go-dev/
    │   │   ├── AGENTS.md
    │   │   ├── wiki/
    │   │   │   └── pages/
    │   │   │       ├── game-rules.md        # GoPoo server game logic
    │   │   │       └── api-endpoints.md     # GoPoo API spec
    │   │   └── skills/
    │   │
    │   ├── design/
    │   │   ├── wiki/
    │   │   │   └── pages/
    │   │   │       ├── card-database.md     # 63 cards + 11 diarrhea
    │   │   │       ├── category-design.md   # Person/Size/Color/Consistency/Smell
    │   │   │       └── balance-rules.md     # GoPoo specific balance
    │   │   └── skills/
    │   │
    │   ├── qa/
    │   │   ├── wiki/
    │   │   └── skills/
    │   │
    │   ├── marketing/
    │   │   ├── wiki/
    │   │   └── skills/
    │   │
    │   └── studio/
    │       ├── wiki/
    │       │   └── pages/
    │       │       ├── milestone-tracker.md
    │       │       └── priority-matrix.md
    │       └── skills/
    │
    └── <next-game>/             # future project, same structure
        ├── PROJECT.md
        ├── art/
        ├── engineering/
        └── ...
```

### How Agents Read Both Layers

When an agent starts working on a project, it loads knowledge in order:

```
1. base/<dept>/AGENTS.md          # universal rules
2. projects/<project>/<dept>/AGENTS.md  # project overlay (extends, not replaces)
3. base/<dept>/wiki/index.md      # universal knowledge index
4. projects/<project>/<dept>/wiki/index.md  # project knowledge index
5. base/<dept>/skills/            # universal skills
6. projects/<project>/<dept>/skills/  # project-specific skills
```

Project AGENTS.md **extends** base AGENTS.md — it adds project-specific
tag taxonomy, asset specs, style rules, but inherits universal conventions.

### How the Learning Loop Decides Where to Write

In the background review (post-turn), the agent classifies each lesson:

```
Lesson: "Flux at CFG=1 ignores negative prompt"
  → Is this GoPoo-specific? NO — true for any Flux project
  → Write to: base/art/wiki/pages/flux-priors.md

Lesson: "GoPoo buttons use amber #FFB300 with deep purple #5E2A82"
  → Is this GoPoo-specific? YES — another game has different colors
  → Write to: projects/gopoo/art/wiki/pages/color-tokens.md

Lesson: "rembg fails on light-colored UI elements, use HSV color-key"
  → Is this GoPoo-specific? NO — applies to any UI asset pipeline
  → Write to: base/art/wiki/pages/color-keying.md

Lesson: "GoPoo card #23 'Massive Dump' is OP at current values"
  → Is this GoPoo-specific? YES
  → Write to: projects/gopoo/design/wiki/pages/balance-rules.md
```

The classification prompt:

```
Would this lesson still be true and useful if we were making
a completely different game with a different art style, different
rules, and different tech stack?

YES → base (universal)
NO  → project (game-specific)
PARTIALLY → split: extract the universal principle to base,
            keep the specific application in project
```

### What Carries to the Next Game

When you start `projects/next-game/`, you get:
- All of `base/` — every universal lesson from GoPoo (and any previous game)
- Empty `projects/next-game/` — clean slate for project-specific knowledge
- The framework itself (`core/`) — the agent loop, wiki ops, skill management

The base layer is the studio's **lasting competitive advantage**. The more
games you ship, the smarter every agent starts on day one of the next project.

---

## Six: Cross-Agent Communication

Agents communicate through typed messages. Messages are sources — when
received, they get ingested into the receiving agent's wiki.

```python
@dataclass
class Message:
    from_agent: str        # "art", "design", "engineering", ...
    to_agent: str          # target or "broadcast"
    type: str              # message type (see below)
    payload: dict          # type-specific data
    timestamp: str

# Message types and their flows:
#
# design → art:          asset_request
# art → engineering:     asset_delivery
# engineering → qa:      build_ready
# qa → engineering:      bug_report
# qa → studio:           quality_gate_result
# studio → broadcast:    priority_update
# any → any:             wiki_insight (cross-pollinate knowledge)
```

Cross-wiki references use namespace prefixes:

```markdown
This style was defined in [[art:style-anchor]] and the
touch target requirement comes from [[qa:quality-gate#touch-targets]].
```

Rule: an agent can read another department's wiki but never writes to it.
Cross-pollination happens via `wiki_insight` messages that the receiving
agent integrates into its own wiki.

---

## Seven: Agent Base Protocol

```python
class StudioAgent:
    """Base protocol for all Game Studio agents."""

    def __init__(self, department: str, base_dir: str = "game-studio"):
        self.department = department
        self.base = f"{base_dir}/{department}"
        self.raw_dir = f"{self.base}/raw/"
        self.wiki_dir = f"{self.base}/wiki/"
        self.skills_dir = f"{self.base}/skills/"
        self.schema = f"{self.base}/AGENTS.md"
        self.index = f"{self.base}/wiki/index.md"
        self.log = f"{self.base}/wiki/log.md"

    # --- Knowledge Operations (Karpathy) ---

    def ingest(self, source_path: str):
        """New source → read → extract → integrate into wiki + skills."""

    def query(self, question: str) -> str:
        """Answer from wiki. File good answers back as pages."""

    def lint(self):
        """Health-check wiki and skills."""

    # --- Production Operation (AutoResearch) ---

    def iterate(self, task: dict):
        """Closed feedback loop: generate → execute → evaluate → synthesize.

        Each agent implements its own Generator/Executor/Evaluator/Synthesis.
        The loop structure is universal; the components are department-specific.

        Args:
            task: YAML task definition with target, checklist,
                  executor steps, evaluator config, max_iterations.
        """
        prompt_or_code = self.generate(task, lessons=self.load_lessons())
        for round_n in range(task["max_iterations"]):
            output = self.execute(prompt_or_code, task)
            evaluation = self.evaluate(output, task["checklist"])
            self.synthesize(evaluation)  # → wiki + skills

            if evaluation["score"] >= task["pass_threshold"]:
                return output  # done

            if self.is_plateauing(window=3):
                self.escalate("ceiling detected, need architectural change")
                return None

            prompt_or_code = self.generate(task, evaluation, self.load_lessons())

    # Subclass hooks (each agent implements these):
    def generate(self, task, evaluation=None, lessons=None): ...
    def execute(self, input, task): ...
    def evaluate(self, output, checklist): ...
    def synthesize(self, evaluation): ...
    def load_lessons(self) -> list: ...
    def is_plateauing(self, window=3) -> bool: ...
    def escalate(self, reason: str): ...

    # --- Learning Loop (Hermes) ---

    def background_review(self, conversation_messages: list):
        """Post-turn review: update memory (wiki) and skills."""

    def curate(self):
        """Periodic skill maintenance: track usage, archive stale."""

    # --- Studio Operations ---

    def receive_message(self, message: Message):
        """Ingest message from another agent into wiki."""

    def send_message(self, to: str, type: str, payload: dict):
        """Send typed message to another agent."""

    # --- Self-Loop ---

    def loop(self):
        """Agent's autonomous loop."""
        # 1. Check inbox for messages from other agents
        # 2. Check raw/ for new unprocessed sources
        # 3. Run department-specific logic (may call iterate())
        # 4. Ingest new sources
        # 5. Respond to queries
        # 6. Periodic lint + curate
```

---

## Eight: Schema Template (AGENTS.md)

Each department's AGENTS.md follows this structure:

```markdown
# [Department] Agent Schema

## Identity
One sentence: what this agent is and what it protects.

## Domain
What this wiki covers. Boundaries of responsibility.

## Wiki Conventions
- File naming: lowercase, hyphens, no spaces
- Required frontmatter fields
- Tag taxonomy (10-20 tags, add here before using)
- Page thresholds (when to create vs update vs skip)
- Update policy (how to handle contradictions)
- Cross-reference minimum (≥2 outbound links per page)

## Skill Conventions
- Skill naming: class-level, not session-specific
- When to create vs update vs add reference
- Protected skills list

## Ingest Workflow
Step-by-step for this department's source types.

## Query Conventions
How to answer questions, what formats to use.

## Learning Loop Rules
What to capture vs skip in post-turn review.
Department-specific signals to watch for.

## Lint Rules
Department-specific health checks.

## Loop Logic
What triggers this agent's autonomous cycle.
When to escalate to Studio Director.

## Cross-Agent Protocols
What messages this agent sends and receives.
How to integrate incoming messages.
```

---

## Nine: Existing Knowledge Migration

Current GoPoo docs split across base and project layers:

| Current File | Base (universal) | Project (GoPoo-specific) |
|---|---|---|
| `STYLE_ANCHOR.md` | — | `projects/gopoo/art/wiki/pages/style-anchor.md` |
| `LESSONS.md` | Extract universal patterns → `base/art/wiki/` | GoPoo-specific iterations → `projects/gopoo/art/skills/*/references/` |
| `DEBUG_LESSONS.md` | Flux/Unity/rembg lessons → `base/art/wiki/` + `base/engineering/wiki/` | GoPoo panel/asset specifics → `projects/gopoo/` |
| `AUTORESEARCH_LOOP.md` | Loop mechanism → `base/art/skills/autoresearch-loop/` | GoPoo task definitions → `projects/gopoo/art/skills/` |
| `UI_REVIEW_CHECKLIST.md` | Scoring system + flow → `base/qa/skills/ui-review/` | GoPoo panel checklists → `projects/gopoo/qa/skills/` |
| `autoresearch/*.py` | stays in comfyui_workflow repo, referenced by skills | — |
| `workflows/*.py` | stays in comfyui_workflow repo, referenced by skills | — |

Examples of the split:

```
DEBUG_LESSONS.md §1.1 "Flux negative prompt is fake at CFG=1"
  → base/art/wiki/pages/flux-priors.md (universal)

DEBUG_LESSONS.md §4.1 "Tuanjie process name ≠ Unity"
  → base/engineering/wiki/pages/unity-gotchas.md (universal)

STYLE_ANCHOR.md "deep grape purple #3A1B4A as bg"
  → projects/gopoo/art/wiki/pages/style-anchor.md (GoPoo only)

LESSONS.md "按钮 round 5 score=7.0, glossy highlight残留"
  → projects/gopoo/art/skills/gopoo-button/references/ (GoPoo only)

UI_REVIEW_CHECKLIST.md "dual-layer scoring, ≥7.5 to ship"
  → base/qa/skills/ui-review/SKILL.md (universal method)

UI_REVIEW_CHECKLIST.md "MainMenu: Logo突出面板框上方"
  → projects/gopoo/qa/skills/gopoo-panels/references/ (GoPoo only)
```

---

## Ten: Bootstrap Sequence

1. Create directory structure (`base/` + `projects/gopoo/`)
2. Write `base/art/AGENTS.md` — universal art agent rules
3. Write `projects/gopoo/art/AGENTS.md` — GoPoo art overlay
4. Migrate knowledge with base/project split:
   - Universal Flux/CN/rembg lessons → `base/art/wiki/pages/`
   - GoPoo style/color/iterations → `projects/gopoo/art/wiki/pages/`
   - Universal UI scoring → `base/qa/skills/ui-review/`
   - GoPoo panel checklists → `projects/gopoo/qa/skills/`
5. Generate initial `index.md` + `log.md` for both layers
6. Validate: run one Art agent cycle reading both layers
7. Bring up engineering (base Unity lessons + GoPoo architecture)
8. Bring up remaining agents
9. When starting next game: create `projects/<next>/`, inherit all of `base/`

Start with one agent. Validate the two-layer read. Then scale.

---

## Eleven: Why This Works

**Karpathy's insight**: humans abandon wikis because maintenance burden grows
faster than value. LLMs don't get bored and can touch 15 files in one pass.

**Hermes' insight**: the agent should learn from every interaction without
being told to. Background review + curator = continuous improvement with zero
human maintenance cost.

**Combined for a Game Studio**: every playtest, every generated asset, every
bug fix, every competitive analysis is a source. The wikis compound. The skills
sharpen. By launch, each department has comprehensive, interlinked knowledge —
not scattered in chat history, not locked in someone's head. And the agents
get better at their jobs with every session, not just more knowledgeable.

> The human's job: curate sources, direct the game, make creative and
> strategic decisions. The agent's job: everything else — including
> remembering what it learned and getting better at it.

---

## References

- Karpathy. [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- Karpathy. [AutoResearch repo](https://github.com/karpathy/autoresearch)
- Nous Research. [Hermes Agent](https://github.com/nousresearch/hermes-agent) — self-improving agent
- Hermes Agent `agent/background_review.py` — learning loop implementation
- Hermes Agent `agent/curator.py` — skill lifecycle management
- Hermes Agent `skills/research/llm-wiki/SKILL.md` — Karpathy wiki skill
- Bush, Vannevar. "As We May Think" (1945) — the Memex vision
