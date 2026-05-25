---
name: industry-research
description: "Research industry standards and competitor products."
version: 1.0.0
created_by: agent
tags: [research, industry, competitor, reference]
---

# Industry & Competitor Research Skill

Two-layer research framework for game development decisions.

## When to Use

- Before making design decisions (layout, interaction, visual style)
- When an agent's output gets rejected and the reason is "doesn't feel right"
- At project kickoff (competitive landscape scan)
- When entering a new feature area (e.g. first time building multiplayer lobby)

## Two Layers

### Layer 1: Industry Standards (base wiki)

Universal knowledge about how games/apps solve common problems.
Not specific to any competitor — these are established patterns.

Research by department:

| Department | What to Research | Example Output |
|---|---|---|
| CD | Visual style taxonomy, color psychology, genre conventions | "Dark card games use warm spotlights on dark felt to create intimacy" |
| Design | UI layout patterns, interaction paradigms, information architecture | "Card game hand areas: 95% use bottom-of-screen curved tray" |
| Art | Asset pipeline standards, resolution targets, sprite conventions | "Mobile card sprites: 256×384 @2x, transparent PNG, 9-slice for frames" |
| Engineering | Tech stack patterns, performance benchmarks | "Unity UGUI: ScreenSpaceCamera for 3D-over-UI effects" |
| PM | Market sizing, monetization models, retention benchmarks | "Casual card games: D1 retention 35-45%, session length 8-12 min" |
| QA | Testing standards, accessibility guidelines | "WCAG contrast ratio ≥ 4.5:1 for text on background" |

Output: `base/<dept>/wiki/pages/industry-<topic>.md`

### Layer 2: Competitor Analysis (project wiki)

Specific games analyzed for specific features. Screenshots + analysis.

Research template per competitor:

```yaml
competitor: Hearthstone
platform: iOS/Android
genre: CCG (collectible card game)
relevance: "same genre, gold standard for card game UI"

analysis:
  hand_area:
    description: "Curved tray at bottom, cards fan out with hover-to-enlarge"
    screenshot: "references/hearthstone_hand.png"
    lessons: "Tray has subtle shadow, no hard border line"
    
  opponent_area:
    description: "Mirror layout at top, smaller scale"
    screenshot: "references/hearthstone_opponent.png"
    lessons: "Name + portrait + card count, always visible"
    
  card_pile:
    description: "Deck on right side, glowing when drawable"
    lessons: "Clear affordance — glow = interactive"
```

Output: `projects/<game>/<dept>/wiki/pages/competitor-<name>.md`

## Procedure

### Step 1: Define Research Questions

Before searching, list specific questions:

```
For GamePanel hand area:
- How do top card games display the player's hand?
- Is there a container/tray or do cards float?
- How is the boundary between table and hand indicated?
- How do they handle 5 vs 15 cards?
```

### Step 2: Gather Sources

Methods:
- Web search for UI screenshots + analysis articles
- App Store / Google Play — download and screenshot competitors
- YouTube gameplay videos — pause at key UI moments
- Game UI databases (gameuidatabase.com, mobbin.com)

Save raw sources to `raw/references/` (immutable).

### Step 3: Analyze & Compare

Create comparison tables:

```markdown
| Feature | Hearthstone | Exploding Kittens | UNO | Slay the Spire |
|---|---|---|---|---|
| Hand position | bottom tray | bottom fan | bottom arc | bottom row |
| Hand boundary | shadow gradient | none (cards float) | subtle line | dark bar |
| Max visible cards | 10 (shrink) | 7 (scroll) | unlimited (shrink) | 12 (shrink) |
```

### Step 4: Extract Patterns

From comparison, identify industry patterns:

```
PATTERN: Hand Area Design
- 100% of competitors put hands at bottom (thumb zone)
- 80% use curved/fan layout (not straight row)
- 60% use shadow gradient for boundary (not hard line)
- Card count overflow: 70% shrink cards, 30% scroll
→ Write to: base/<dept>/wiki/pages/industry-hand-area.md
```

### Step 5: Inform Decisions

When CD/Design/Art needs to make a decision:
1. Check base wiki for industry standard
2. Check project wiki for competitor specifics
3. Make decision WITH reference, not from scratch

## Who Does What

| Agent | Research Role |
|---|---|
| CD | Visual style references, mood/atmosphere comparisons |
| Design | UI layout patterns, interaction flow analysis |
| Art | Asset style references, technique analysis |
| PM | Market data, feature prioritization against competitors |
| All | Can request research via `research_request` message |

## Pitfalls

- Don't just collect screenshots — ANALYZE them (what works, why, lesson)
- Don't copy competitors — extract PATTERNS, then apply to your style
- Don't research everything at once — research when you need to make a decision
- Save raw screenshots to raw/references/ — they're immutable sources
- Industry standards go to base/ (any game), competitor specifics go to project/
