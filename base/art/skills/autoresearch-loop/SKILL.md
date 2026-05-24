---
name: autoresearch-loop
description: "Automated generate-evaluate-revise loop for art assets."
version: 1.0.0
created_by: human
tags: [autoresearch, loop, flux, comfyui, evaluate]
---

# AutoResearch Loop Skill

Automated feedback loop for visual asset generation. Runs overnight on local
hardware, produces hundreds of candidates, auto-scores with Claude vision,
and distills failure modes for the next round.

Inspired by [Karpathy's AutoResearch](https://github.com/karpathy/autoresearch).

## When to Use

- Batch asset production (5+ variants of same type)
- Overnight unattended generation runs
- Any asset with measurable success criteria and enough sample volume

## When NOT to Use

- Single hero assets (logo, key art) — needs human creative direction
- When the problem is architectural (mask/LoRA/prompt framework), not parametric
- When the model has a strong prior that prompt iteration can't overcome

## Architecture

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐
│Generator │ → │Executor  │ → │Evaluator  │ → │Synthesis │ ─┐
│(revise   │    │(ComfyUI) │    │(Claude    │    │(append   │  │
│ prompt)  │    │          │    │ vision)   │    │ lessons) │  │
└──────────┘    └──────────┘    └───────────┘    └──────────┘  │
     ▲                                                         │
     └─────────────────────────────────────────────────────────┘
```

## Procedure

### 1. Define Task (YAML)

```yaml
task_id: <asset_name>
asset_type: character_sprite | button | background | card | frame
dimensions: { width: 512, height: 512 }

variants:
  - name: happy
    target_description: "happy mischievous grin, sparkling eyes"
  - name: angry
    target_description: "frowning brow, puffed cheeks"

checklist:
  - "Matches target emotion?"
  - "Thick black ink outline (Cult of the Lamb style)?"
  - "No text, no watermark?"
  - "Consistent with style anchor?"

pass_threshold: 8.5
max_iterations: 8
samples_per_round: 3
```

### 2. Run Loop

```python
from autoresearch.loop import run_loop
run_loop("tasks/my_task.yaml")
```

Each round:
1. Generator reads previous evaluation + LESSONS → revises prompt
2. Executor submits to ComfyUI API → generates image(s)
3. Evaluator sends to Claude vision → scores against checklist
4. Synthesis appends failure modes to wiki, updates prompt templates

### 3. Collect Results

Best candidates saved in `runs/<date>_<task>/final.png`.
All rounds preserved for analysis.

## Convergence Behavior (Validated)

| Round | Typical Score | What Happens |
|---|---|---|
| 1 | 5-6 | Major issues (wrong expression, no outline) |
| 2 | 7-8 | Big corrections land, most issues fixed |
| 3 | 8-9 | Fine-tuning, may pass threshold |
| 4+ | 6-8 oscillating | Diminishing returns, may oscillate |

**Ceiling rule**: if score plateaus for 3 consecutive rounds, the problem
is architectural. Stop the loop and change strategy:
- Switch mask (thin → thick)
- Remove/change LoRA
- Reframe the scene description entirely
- Use a different ControlNet type

## Cost Estimation (Local Mac MPS)

| Asset Size | Time per Image | 24h Capacity |
|---|---|---|
| 256×256 | ~20s | ~4300 |
| 512×512 | ~30-40s | ~2500 |
| 1024×384 | ~60s | ~1400 |
| 1920×1088 | ~480s | ~180 |

Claude API evaluation: ~$0.015/image (Sonnet vision).
Typical overnight run (1000 images): **~$15**.

## Pitfalls

- Always smoke-test 1 image before launching a batch — parameter parsing
  errors waste entire overnight runs
- Generator prompt rewrites are effective for rounds 1-3, then diminish
- "Fix A breaks B" oscillation = architectural ceiling, not prompt problem
- Evaluator scoring is reliable for structured checklists but drifts on
  subjective aesthetics — use anchor images to calibrate

## References

- `references/convergence-patterns.md` — detailed score curves from past runs
- `templates/task-template.yaml` — blank task definition
- `scripts/smoke_test.py` — single-image test before batch
