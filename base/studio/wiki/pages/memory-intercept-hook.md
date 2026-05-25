---
title: Memory Intercept Hook — Preventing Claude Code Auto-Memory Drift
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [memory, hooks, wiki-discipline, claude-code, automation]
sources: [session analysis of auto-memory vs LLM wiki conflict]
confidence: high
---

# Memory Intercept Hook

## Problem

Claude Code has a built-in auto-memory system (`~/.claude/projects/<project>/memory/`).
When Claude writes to memory, it believes it has "remembered" the information and
won't write it to the wiki. But memory is:

- Not readable by other agents
- Not part of the two-layer wiki architecture
- Not indexed, tagged, or linked
- Creates a false sense of persistence ("I already saved this")

This causes **knowledge drift**: information that should compound in the wiki
gets siloed in memory where it provides no lasting value.

## Solution

A SessionEnd hook that intercepts memory writes and routes them through the
wiki's triage process.

**Location**: `comfyui_workflow/.claude/hooks/purge-memory.sh`
**Config**: `comfyui_workflow/.claude/settings.json` → hooks.SessionEnd

## How It Works

```
SessionEnd fires
    │
    ▼
Scan memory dir for new .md files
    │
    ├── For each file: extract description → 3 significant keywords
    │
    ├── Search wiki: does ANY page contain ALL keywords?
    │       │
    │       ├── YES (≥1 page covers it) → silent delete
    │       │
    │       └── NO (not covered) → copy to inbox + append to wiki log + terminal warning
    │
    └── Always: delete all memory files + clear MEMORY.md
```

## Keyword Matching Logic

- Extract keywords from the `description:` frontmatter field
- Filter: ≥5 chars, not stopwords, deduplicated, top 3
- A wiki page must contain **all** keywords to count as "covered"
  (prevents false positives from common words like "launch" or "update")
- If <2 keywords extractable → treat as new (can't compare)

## File Locations

| File | Purpose |
|------|---------|
| `comfyui_workflow/.claude/hooks/purge-memory.sh` | The hook script |
| `comfyui_workflow/.claude/settings.json` | Hook registration (SessionEnd) |
| `base/studio/inbox/memory-intercept/` | Timestamped copies of new content for triage |
| `base/studio/wiki/log.md` | Append-only record of intercepted items |

## Triage Workflow

When the hook catches new content:

1. Terminal shows `⚠️ [memory-purge] New content not yet in wiki:`
2. File is saved to `studio/inbox/memory-intercept/{timestamp}_{name}.md`
3. Entry appended to `studio/wiki/log.md`
4. Human reviews inbox → writes proper wiki page in the correct department → deletes from inbox

## Why Not Disable Auto-Memory Entirely

Claude Code doesn't have a per-project setting to disable auto-memory
(security restriction — project settings can't control memory path).
The hook approach works within this constraint: let Claude write, then
immediately intercept and redirect.

## Limitations

- Keyword matching is approximate — a semantically similar page with different
  vocabulary won't be detected as "covered"
- Hook runs at SessionEnd only — within a session, Claude still sees its
  MEMORY.md and may behave as if it has memory (but MEMORY.md is always
  empty at session start)
- The `description:` field must be meaningful for comparison to work;
  files without description are always treated as new

See also: [[architecture-upgrade-plan]], [[knowledge-routing]], [[wiki-lifecycle]]
