---
title: LLM Provider Cost Analysis & Routing Strategy
created: 2026-05-25
updated: 2026-05-25
type: comparison
tags: [cost, provider, deepseek, claude, routing, scaling]
sources: [session discussion, pricepertoken.com, user reviews, Anthropic docs]
confidence: high
---

# LLM Provider Cost Analysis & Routing Strategy

## Unit Pricing (per million tokens)

| Model | Input $/1M | Output $/1M | Blended (3:1) | Per-call (8K in + 4K out) |
|-------|-----------|------------|---------------|--------------------------|
| DeepSeek V4 Pro | $0.435 | $0.87 | $0.54 | **$0.007** |
| Claude Haiku 4.5 | $1.00 | $5.00 | $2.00 | $0.028 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | $6.00 | $0.084 |
| Claude Opus 4.7 | $5.00 | $25.00 | $10.00 | $0.14 |

DeepSeek V4 Pro permanent price is 1/4 of original (official, not promo).

## Claude Max 20x ($200/month) Real Constraints

| Constraint | Value |
|-----------|-------|
| 5h rolling window | ~900 messages/5h |
| **Weekly cap (Opus)** | ~40 hours |
| **Weekly cap (Sonnet)** | ~480 hours |
| Monthly Opus (estimated) | ~20,000 calls |
| Monthly Sonnet (estimated) | ~495,000 calls |
| SDK Credits (from 2026-06-15) | $200/month at standard API rates |

**Why:** weekly cap is the real binding constraint, not the 5h window.
Anthropic does not publish exact numbers; they shift with server load.

## Max 20x Breakeven Points

| vs what | Max is cheaper when monthly calls exceed |
|---------|----------------------------------------|
| Opus API | ~1,430 calls (daily ~48) |
| Sonnet API | ~2,380 calls (daily ~80) |
| DeepSeek V4 Pro | ~28,500 calls (daily ~950) — unlikely to reach |

At current usage (25/day), Max costs $200 while DeepSeek would cost $5.

## Monthly Cost by Phase

| Phase | Daily calls | Max 20x | Opus API | Sonnet API | DeepSeek V4 |
|-------|-----------|---------|----------|------------|-------------|
| Current | 25 | $200 | $105 | $63 | **$5** |
| Phase 2 | 80 | $200 | $336 | $202 | **$17** |
| Phase 3 | 200 | $200 | $840 | $504 | **$42** |
| Phase 4 | 500 | $200+ | $2,100 | $1,260 | **$104** |
| 24/7 full | 4,300 | $200+overage | $18,200 | $10,920 | **$905** |

## DeepSeek V4 Pro Quality Assessment

Real user consensus (Reddit, Zhihu, V2EX, 40M-token tests):

**80% of daily coding tasks ≈ Sonnet quality. 20% hard tasks need Opus.**

### Strengths
- LiveCodeBench 93.5 > Sonnet 88.8 (pure code generation)
- Terminal-Bench 67.9 > Opus 65.4 (shell tasks)
- 1M context window vs Sonnet 200K
- Sustained 60-minute coding sessions without drift

### Weaknesses
- 94% hallucination rate (almost never says "I don't know")
- Complex multi-constraint instructions: drops requirements
- Multi-file refactors / architecture: weaker than Opus
- Agent self-correction loops: needs more iterations
- Needs explicit full context; won't discover files on its own

## Routing Strategy (Decided)

```
Task arrives
    │
    ├─ Single-file code / template / wiki → DeepSeek V4 Pro ($0.007)
    │
    ├─ Multi-constraint scoring / agent loop → DeepSeek V4 first
    │       └─ loop > threshold → escalate to Max Opus ($0)
    │
    ├─ QA scoring → Max Opus directly (hallucination risk too high)
    │
    └─ Architecture / creative / multi-file → Max Opus directly ($0)
```

**Why QA must use Claude:** DeepSeek's hallucination rate means it will
confidently score 8.0 when actual quality is 5-6. This exact failure
happened in session 2026-05-25 (evaluator self-score vs honest assessment).

## Projected Cost (Mixed Routing)

| Phase | DeepSeek (60%) | Max Opus (40%) | Total |
|-------|---------------|----------------|-------|
| Current | $3 | $0 (subscription) | $200 + $3 |
| Phase 2 | $8 | $0 | $200 + $8 |
| Phase 3 | $25 | $0 | $200 + $25 |
| Phase 4 | $62 | $0 | $200 + $62 |

## Scaling Decision Points

1. **Now → June 15**: DeepSeek V4 Pro for self-built path, Max CLI for fallback
2. **June 15**: Activate $200 SDK credits, add Claude SDK as middle tier
3. **Daily >950 calls**: Max subscription begins saving vs DeepSeek — re-evaluate
4. **Daily >4,300 calls (24/7 full)**: Max weekly cap becomes bottleneck, need API overflow

## Implementation

See: [[dispatch-automation-plan]], [[architecture-upgrade-plan]]

Core changes:
- `core/provider.py` — unified interface: `run_prompt(prompt, provider, tools)`
- `core/dispatch.py` — replace hardcoded `claude -p` with provider routing
- Task YAML — per-task `provider` and `max_self_loops` config
- Fallback: DeepSeek → escalate Opus → report human
