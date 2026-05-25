---
title: Wiki Page Lifecycle — Retention, Archival, Lint
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [wiki, lifecycle, archive, lint, maintenance]
sources: []
confidence: high
---

# Wiki Page Lifecycle

Pages are never deleted. They move through lifecycle stages.

## Lifecycle Stages

```
created → active → stale → archived
                     ↑
                  (lint detects)
```

| Stage | Meaning | Action |
|---|---|---|
| active | Referenced, accurate, useful | None |
| stale | >90 days since `updated`, may be outdated | Review: update or archive |
| archived | Superseded or no longer relevant | Move to `_archive/`, remove from index |

## What to Archive (eventually)

| Page Type | When to Archive | Why |
|---|---|---|
| Session summaries | 3 months after creation | Key findings already extracted to concept pages |
| Dispatch issue logs | All issues fixed + verified | Historical, no longer guides behavior |
| Version-specific reviews (v07-asset-review) | Next version's review exists | Superseded |
| Iteration logs (gamepanel-review-log) | Panel redesigned or shipped | Snapshot of old state |

## What to NEVER Archive

| Page Type | Why Permanent |
|---|---|
| Concept pages (flux-priors, evaluator-calibration) | Accumulated knowledge, continuously referenced |
| Routing rules (knowledge-routing) | System behavior depends on it |
| Roadmap | Living document, updated not archived |
| Skills (SKILL.md) | Operational procedures — archive via Curator lifecycle instead |

## Archive Procedure

```
1. Create _archive/ in the wiki directory if not exists
2. Move page to _archive/ preserving filename
3. Remove entry from index.md
4. Update pages that linked to it: [[page]] → [[_archive/page]] or plain text
5. Log in log.md: "## [date] archive | page-name — reason"
```

## Lint Checks (periodic)

Run during wiki lint (manual or cron):

### Staleness
```
For each page in pages/:
  if (today - page.updated) > 90 days:
    flag as stale
    add to lint report
```

### Orphans
```
For each page in pages/:
  count inbound [[wikilinks]] from other pages
  if count == 0:
    flag as orphan candidate for archive
```

### Contradictions
```
For each page with confidence: high:
  check if any newer page contradicts its claims
  if yes: mark older page contested: true
```

### Index Drift
```
Compare pages/ file listing against index.md entries
  Missing from index → add
  In index but file deleted → remove
  Page count in header doesn't match → fix
```

### Superseded Content
```
For version-specific pages (v07-*, v08-*):
  if a newer version page exists:
    archive the older one
```

## When to Run Lint

- After every dispatch completes (automated, Week 2 goal)
- Weekly manual review (until automated)
- Before any milestone delivery

See also: [[knowledge-routing]], [[roadmap]]
