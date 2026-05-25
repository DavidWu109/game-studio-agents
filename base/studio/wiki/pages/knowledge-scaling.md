---
title: Knowledge Scaling — Dynamic Retrieval for Multi-Genre Studio
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [knowledge, scaling, search, retrieval, architecture]
sources: [human direction 2026-05-25]
confidence: high
---

# Knowledge Scaling

## Problem

Base wiki is not "card game knowledge" — it's "game studio knowledge".
Future projects include tower defense, turn-based RPG, 2D to 3.5D.
Knowledge must be genre-agnostic and dynamically retrievable.

## Current State

- ~20 wiki pages, all manually browsed via index.md
- Pages implicitly assume card game context (hand area, card frames)
- No search capability

## Target State

- Hundreds of pages across multiple genres and domains
- Agent queries: "how do mobile games handle hand/inventory areas?"
- System returns relevant pages regardless of which genre they came from
- A tower defense project benefits from card game UI lessons (and vice versa)

## Knowledge Organization Principle

**Tag by capability, not by genre.**

```
BAD:  base/art/wiki/pages/card-game-hand-area.md
GOOD: base/art/wiki/pages/industry-player-inventory-display.md
      tags: [layout, inventory, hand, mobile, touch-zone]
```

A page about "how to display items the player currently holds" is useful
for card hands, tower defense inventories, RPG equipment screens, etc.

## Tagging Taxonomy (cross-genre)

### Universal Capabilities
- `layout` — spatial arrangement of UI elements
- `touch-zone` — thumb-reachable areas, tap targets
- `inventory` — player's owned items/cards/units display
- `opponent` — showing other players' state
- `status` — health/score/turn indicators
- `action-button` — primary interaction trigger
- `overlay` — modal/popup over game view
- `notification` — alerts, prompts, turn indicators
- `animation` — transitions, feedback, juice
- `onboarding` — tutorial, first-time experience

### Visual Capabilities
- `sprite-pipeline` — generation, post-processing, deployment
- `text-rendering` — fonts, outlines, contrast, hierarchy
- `color-system` — palette, contrast, accessibility
- `style-anchor` — visual identity definition

### Technical Capabilities
- `asset-loading` — sprite paths, texture import, caching
- `build-pipeline` — prefab generation, scene management
- `screenshot` — capture methods, comparison tools
- `mcp-integration` — editor automation

## Dynamic Retrieval (Implementation Plan)

### Phase 1: Frontmatter Tags (now)

Every wiki page already has `tags:` in frontmatter.
Search = grep tags across all pages.

```bash
# Find pages about inventory/hand display for mobile
grep -rl "tags:.*inventory\|tags:.*hand\|tags:.*touch-zone" base/*/wiki/pages/
```

### Phase 2: CLI Search Tool (Week 3)

```python
# core/search.py
def search_wiki(query: str, departments: list = None) -> list[Page]:
    """Search across all base wiki pages by tag + content."""
    # 1. Tag match (fast, precise)
    # 2. Keyword match in content (broader)
    # 3. Return ranked results with snippets
```

### Phase 3: Embedding Search (Month 2+)

When pages exceed ~200:
- Embed all pages with sentence-transformers
- On query: embed query → cosine similarity → top-k pages
- Or use qmd (Karpathy recommended) for hybrid BM25/vector

### Phase 4: Agent Auto-Retrieval (Month 3+)

Before any agent acts, it auto-queries:
```python
class StudioAgent:
    def before_action(self, task):
        relevant = search_wiki(task["input"], departments=[self.department])
        self.context += relevant  # inject into prompt
```

## Migration: Current Pages

Existing pages should be re-tagged with genre-agnostic tags:

| Current Page | Add Tags |
|---|---|
| flux-priors | sprite-pipeline, generation, model-behavior |
| controlnet-guide | sprite-pipeline, generation, shape-control |
| evaluator-calibration | scoring, review, automation |
| page-review-checklist | review, layout, touch-zone, text-rendering |
| unity-gotchas | build-pipeline, asset-loading |
| sprite-path-gotcha | asset-loading |
| knowledge-routing | meta-process |

## Key Rule

When writing a new wiki page, ask:
> "If we were making a tower defense game, would this page's TITLE
> still make sense?"

If not, generalize the title and tags. The content can reference
the specific game as an example, but the page should be discoverable
by any future project.

See also: [[knowledge-routing]], [[wiki-lifecycle]]
