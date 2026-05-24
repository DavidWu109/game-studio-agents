# Game Studio Agents

A self-learning multi-agent system for game development. Each department agent
maintains a **two-layer knowledge base** — universal lessons that carry across
projects, and project-specific knowledge that stays scoped to one game.

## Architecture

Built on three foundations:
- **[Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)** — persistent, compounding knowledge
- **[Hermes Agent](https://github.com/nousresearch/hermes-agent)** — closed learning loop, skills, curator
- **[AutoResearch](https://github.com/karpathy/autoresearch)** — feedback optimization loop for all agents

See [FRAMEWORK.md](FRAMEWORK.md) for the full design.

## Two-Layer Knowledge

```
base/           ← universal (carries to every future game)
  "Flux ignores negative prompt at CFG=1"
  "Unity 9-slice border must < image size"
  "Go table-driven test pattern"

projects/gopoo/ ← project-specific (GoPoo only)
  "CotL style, deep purple #3A1B4A palette"
  "63 cards + 11 Diarrhea"
  "Server on port 9090"
```

The more games you ship, the smarter every agent starts on day one of the next.

## Agents

| Agent | Role | AutoResearch Loop |
|---|---|---|
| **Art** | Visual assets (Flux + ComfyUI) | prompt → generate → vision score → revise |
| **Engineering** | Unity/Tuanjie client | code → compile → test+screenshot → fix |
| **Go Dev** | Game server (Go) | code → build+test → benchmark → fix |
| **Design** | Rules and balance | values → simulate 1000 games → analyze → adjust |
| **QA** | Quality assurance | test → screenshot → diff → report |
| **Marketing** | User acquisition | creative → render → predict → iterate |
| **Studio** | Cross-department coordination | collect → prioritize → allocate |

## Structure

```
game-studio-agents/
├── FRAMEWORK.md              # system design document
├── core/                     # shared framework code
│   ├── agent.py              # StudioAgent base class (two-layer)
│   ├── wiki.py               # wiki operations (ingest/query/lint)
│   ├── skills.py             # skill management + curator
│   ├── loop.py               # AutoResearch iterate loop
│   └── bus.py                # cross-agent message bus
│
├── base/                     # UNIVERSAL KNOWLEDGE
│   ├── art/                  # "thick mask = thick outline" (any game)
│   ├── engineering/          # "Assets/Refresh to recompile" (any Unity)
│   ├── go-dev/               # "table-driven tests" (any Go server)
│   ├── design/               # "Monte Carlo for balance" (any card game)
│   ├── qa/                   # "dual-layer scoring" (any UI)
│   ├── marketing/
│   └── studio/
│
└── projects/                 # PROJECT-SPECIFIC KNOWLEDGE
    ├── gopoo/                # GoPoo: poop card game
    │   ├── PROJECT.md        # identity, repos, status
    │   ├── art/              # CotL style, poop mascot
    │   ├── engineering/      # GoPoo client architecture
    │   ├── go-dev/           # GoPoo server endpoints
    │   ├── design/           # 63 cards, balance rules
    │   ├── qa/
    │   ├── marketing/
    │   └── studio/
    └── <next-game>/          # future project, clean slate + all base knowledge
```

Each `<dept>/` directory has:
```
<dept>/
├── AGENTS.md         # schema: identity, conventions, workflows
├── wiki/             # declarative knowledge
│   ├── index.md      # content catalog
│   ├── log.md        # chronological action log
│   └── pages/        # entity/concept/comparison pages
└── skills/           # procedural memory
    └── <skill-name>/
        ├── SKILL.md
        ├── references/
        ├── templates/
        └── scripts/
```

## Quick Start

```bash
# Initialize an Art agent for GoPoo
python -m core.agent art --project gopoo

# Run an AutoResearch loop
python -m core.loop --agent art --project gopoo --task tasks/generate_button.yaml

# Query across both layers
python -m core.wiki query art --project gopoo "Why does Flux add glass highlights?"
```

## License

MIT
