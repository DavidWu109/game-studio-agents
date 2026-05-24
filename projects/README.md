# Projects

Each game project lives in its own repository under this directory.
Clone your project repo here:

```bash
cd projects/
git clone git@github.com:YourOrg/your-game-studio-project.git your-game
```

Project repos follow this structure:

```
your-game/
├── PROJECT.md           # identity, goals, repos, status
├── art/
│   ├── AGENTS.md        # project overlay (extends base/art/AGENTS.md)
│   ├── raw/             # immutable sources
│   ├── wiki/            # project-specific art knowledge
│   └── skills/          # project-specific art skills
├── engineering/
├── go-dev/
├── design/
├── qa/
├── marketing/
└── studio/
```

Projects are gitignored from the framework repo. The `base/` layer
carries universal knowledge; project repos carry game-specific knowledge.
