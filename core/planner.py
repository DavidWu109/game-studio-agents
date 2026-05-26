"""Plan-and-Execute system for complex agent tasks.

Ensures multi-step tasks are properly planned before execution,
with wiki knowledge gathering and step-by-step verification.

Flow:
    1. classify_complexity() — heuristic, no LLM
    2. gather_knowledge() — search wiki for relevant lessons
    3. generate_plan() — Opus/CLI creates structured steps
    4. execute_plan() — DeepSeek + tool_runner, step by step with verify
    5. replan() — on step failure, Opus revises remaining steps

Usage from dispatch handlers:
    planner = Planner(agent="engineering", cwd="/path/to/project")
    result = planner.run(task)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None

from core.provider import ProviderResult, run_phase
from core.search import filter_by_task, search_by_content
from core.safety import build_safety_prompt

logger = logging.getLogger("planner")

STUDIO_DIR = Path(__file__).parent.parent
PLANS_DIR = STUDIO_DIR / "plans"


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class StepStatus(Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    id: str
    description: str
    instruction: str
    expected_outcome: str
    verify_command: Optional[str] = None
    verify_check: Optional[str] = None
    depends_on: list = field(default_factory=list)
    status: StepStatus = StepStatus.PLANNED
    result: str = ""
    error: str = ""
    retry_count: int = 0


@dataclass
class Plan:
    task_id: str
    goal: str
    complexity: TaskComplexity
    knowledge: list = field(default_factory=list)
    knowledge_sources: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    replan_count: int = 0
    max_replans: int = 2
    created_at: str = ""
    completed_at: str = ""


COMPLEX_KEYWORDS = [
    "rewrite", "refactor", "redesign", "rebuild", "overhaul",
    "from scratch", "entire", "重写", "重构", "重新设计",
]

VERIFY_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class Planner:

    def __init__(self, agent: str, cwd: str):
        self.agent = agent
        self.cwd = cwd

    # --- Entry Point ---

    def run(self, task: dict) -> ProviderResult:
        complexity = self.classify_complexity(task)
        task_id = task.get("id", f"task_{int(time.time())}")

        if complexity == TaskComplexity.SIMPLE:
            logger.info("[%s] SIMPLE — skip planning, direct execution", task_id)
            return self._run_simple(task)

        logger.info("[%s] %s — entering plan-and-execute", task_id, complexity.value)

        knowledge, sources = self.gather_knowledge(task)
        logger.info("[%s] gathered %d wiki lessons from %d pages",
                    task_id, len(knowledge), len(sources))

        plan = self.generate_plan(task, knowledge)
        plan.task_id = task_id
        plan.knowledge = knowledge
        plan.knowledge_sources = sources
        plan.created_at = datetime.now(timezone.utc).isoformat()

        plan_path = self._plan_path(task_id)
        self.save_plan(plan, plan_path)
        logger.info("[%s] plan generated: %d steps", task_id, len(plan.steps))

        try:
            from core.db import record_step, emit_event
            for step in plan.steps:
                record_step(task_id, step.id, step.description, step.instruction, step.expected_outcome)
            emit_event("plan_generated", task_id=task_id, phase="plan",
                       data={"step_count": len(plan.steps), "complexity": complexity.value})
        except Exception:
            pass

        result = self.execute_plan(plan, plan_path, task=task)
        return result

    def _run_simple(self, task: dict) -> ProviderResult:
        task_input = task.get("input", "")
        task_id = task.get("id", "")
        safety = build_safety_prompt(self.agent)
        prompt = f"{safety}\n\nTask: {task_input}\n\nReport what you changed concisely."
        return run_phase("simple", prompt, cwd=self.cwd, task_id=task_id)

    # --- Phase 1: Complexity Classification ---

    def classify_complexity(self, task: dict) -> TaskComplexity:
        explicit = task.get("complexity")
        if explicit:
            return TaskComplexity(explicit)
        if task.get("plan_required"):
            return TaskComplexity.COMPLEX

        task_input = task.get("input", "")
        word_count = len(task_input.split())

        file_refs = re.findall(r'\b\w+\.(cs|py|go|ts|yaml|json|md)\b', task_input)
        unique_files = len(set(file_refs))

        has_complex_kw = any(kw in task_input.lower() for kw in COMPLEX_KEYWORDS)

        issue_markers = (task_input.count("\n-") + task_input.count("\n1.")
                         + task_input.count("\n2.") + task_input.count("\n3."))

        if has_complex_kw or unique_files > 3 or word_count > 150 or issue_markers >= 3:
            return TaskComplexity.COMPLEX
        elif unique_files > 1 or word_count > 50 or issue_markers >= 2:
            return TaskComplexity.MODERATE
        return TaskComplexity.SIMPLE

    # --- Phase 2: Knowledge Gathering ---

    def gather_knowledge(self, task: dict) -> Tuple[List[str], List[str]]:
        task_input = task.get("input", "")
        task_id = task.get("id", "")

        keywords = self._extract_keywords(task_input)
        logger.info("Knowledge search keywords: %s", keywords[:10])

        results = filter_by_task(task_id, issue_keywords=keywords)

        extra = search_by_content(keywords)
        seen_paths = {r[0] for r in results}
        for path, hits, snippet in extra:
            if path not in seen_paths and hits >= 2:
                results.append((path, hits * 0.1, snippet))
                seen_paths.add(path)

        results.sort(key=lambda x: -x[1])
        top = results[:5]

        texts = []
        sources = []
        total_chars = 0
        max_total = 8000
        for path, score, _ in top:
            if total_chars >= max_total:
                break
            try:
                content = path.read_text(encoding="utf-8")
                budget = min(2000, max_total - total_chars)
                if len(content) > budget:
                    content = content[:budget] + "\n... (truncated)"
                texts.append(f"## {path.name}\n\n{content}")
                sources.append(str(path))
                total_chars += len(content)
            except Exception:
                pass

        return texts, sources

    def _extract_keywords(self, text: str) -> List[str]:
        stopwords = {"the", "and", "for", "from", "with", "that", "this", "all",
                     "not", "are", "was", "has", "but", "its", "fix", "use", "set",
                     "add", "get", "new", "can", "will", "should", "must", "after",
                     "each", "check", "make", "file", "line", "code", "change"}
        # CamelCase identifiers
        words = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', text)
        # snake_case identifiers
        words += re.findall(r'[a-z]+_[a-z_]+', text)
        # Domain terms
        words += re.findall(r'\b(?:RectTransform|SafeArea|SafeAreaAdapter|sprite|'
                            r'avatar|anchor|sizeDelta|prefab|shader|Canvas|layout|'
                            r'font|outline|TrySetSprite|LoadAssetAtPath|preserveAspect|'
                            r'gotcha|deform|white\s*strip)\b', text, re.I)
        # File names without extension
        file_names = re.findall(r'\b(\w+)\.(cs|py|png|prefab)\b', text)
        words += [f[0] for f in file_names]
        unique = list(dict.fromkeys(
            w.lower() for w in words if len(w) > 3 and w.lower() not in stopwords
        ))
        return unique[:20]

    # --- Phase 3: Plan Generation ---

    def generate_plan(self, task: dict, knowledge: List[str]) -> Plan:
        task_input = task.get("input", "")
        safety = build_safety_prompt(self.agent)
        # Compress knowledge to key points only — full text wastes thinking tokens
        knowledge_summary = []
        for k in knowledge[:3]:
            lines = k.split("\n")
            # Keep title + first 5 non-empty content lines
            title = lines[0] if lines else ""
            content_lines = [l for l in lines[1:] if l.strip() and not l.startswith("---")][:5]
            knowledge_summary.append(title + "\n" + "\n".join(content_lines))
        knowledge_block = "\n\n".join(knowledge_summary) if knowledge_summary else "(none)"

        prompt = f"""Create a YAML list of steps to complete this task. Each step has: id, description, instruction, expected_outcome, verify_command (optional).

## Knowledge (apply these lessons)
{knowledge_block}

## Task
{task_input}

## Rules
- One step per logical change. Include exact file paths in instruction.
- The executor has tools: read_file, edit_file, bash. Write instructions accordingly.
- Include verify_command (grep or bash) to confirm each edit worked.
- Output ONLY a flat YAML list starting with "- id:". No other text."""

        result = run_phase("plan", f"{safety}\n\n{prompt}", cwd=self.cwd)

        if result.text.startswith("ERROR:"):
            logger.error("Plan generation failed: %s", result.text[:200])
            return Plan(task_id="", goal=task_input,
                        complexity=TaskComplexity.COMPLEX, steps=[])

        logger.info("Plan raw output (%d chars): %s", len(result.text), result.text[:300])
        steps = self._parse_plan_yaml(result.text)
        return Plan(
            task_id="",
            goal=task_input,
            complexity=TaskComplexity.COMPLEX,
            steps=steps,
        )

    def _parse_plan_yaml(self, text: str) -> List[PlanStep]:
        yaml_match = re.search(r'```yaml\s*\n(.*?)```', text, re.DOTALL)
        raw = yaml_match.group(1) if yaml_match else text

        if not raw.strip().startswith("-"):
            lines = raw.strip().split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith("-"):
                    raw = "\n".join(lines[i:])
                    break

        try:
            data = yaml.safe_load(raw)
        except Exception:
            logger.warning("Failed to parse plan YAML, trying line-by-line")
            return [PlanStep(id="step_1_fallback",
                             description="Execute task directly (plan parse failed)",
                             instruction=raw[:500],
                             expected_outcome="Task completed")]

        # Handle nested {"steps": [...]} or flat [...]
        if isinstance(data, dict):
            data = data.get("steps", data.get("plan", []))
        if not isinstance(data, list):
            return [PlanStep(id="step_1_fallback",
                             description="Execute task directly (plan not a list)",
                             instruction=str(data)[:500],
                             expected_outcome="Task completed")]

        steps = []
        for item in data:
            if not isinstance(item, dict):
                continue
            # Flexible field names: id/name, instruction/action/changes
            step_id = item.get("id", item.get("name", f"step_{len(steps)+1}"))
            step_id = re.sub(r'[^a-zA-Z0-9_]', '_', str(step_id))[:40]
            instruction = item.get("instruction", "")
            if not instruction:
                # Fallback: build instruction from other fields
                parts = []
                if item.get("action"): parts.append(str(item["action"]))
                if item.get("changes"): parts.append(str(item["changes"]))
                if item.get("target"): parts.append(f"Target: {item['target']}")
                if item.get("file"): parts.append(f"File: {item['file']}")
                instruction = "\n".join(parts) if parts else item.get("description", "")

            steps.append(PlanStep(
                id=step_id,
                description=item.get("description", ""),
                instruction=instruction,
                expected_outcome=item.get("expected_outcome", ""),
                verify_command=item.get("verify_command"),
                verify_check=item.get("verify_check"),
                depends_on=item.get("depends_on", []),
            ))
        return steps

    # --- Phase 4: Plan Execution ---

    def execute_plan(self, plan: Plan, plan_path: Path,
                     task: Optional[dict] = None) -> ProviderResult:
        all_results = []
        total_cost = 0.0
        total_in = 0
        total_out = 0
        self._task = task

        for step in plan.steps:
            if step.status == StepStatus.DONE:
                continue
            if step.status == StepStatus.SKIPPED:
                continue

            if not self._deps_met(plan, step):
                step.status = StepStatus.SKIPPED
                step.error = "dependency not met"
                logger.warning("[%s] skipped: deps not met", step.id)
                continue

            step.status = StepStatus.IN_PROGRESS
            self.save_plan(plan, plan_path)
            logger.info("[%s] executing: %s", step.id, step.description)
            try:
                from core.db import update_step as _db_us, emit_event as _db_em
                _db_em("step_started", task_id=plan.task_id, step_id=step.id, phase="execute")
            except Exception:
                pass

            success, result, step_pr = self._execute_step(plan, step)

            if success and step.verify_command:
                verified, verify_details = self._verify_step(step)
                if not verified:
                    success = False
                    result = f"Execution OK but verification failed: {verify_details}"

            if success:
                step.status = StepStatus.DONE
                step.result = result
                all_results.append(f"[{step.id}] OK: {result[:200]}")
                logger.info("[%s] done", step.id)
                try:
                    from core.db import update_step as _db_us, emit_event as _db_em
                    _db_us(plan.task_id, step.id, "done", result=result, provider_result=step_pr)
                    _db_em("step_done", task_id=plan.task_id, step_id=step.id, phase="execute")
                except Exception:
                    pass
            else:
                step.status = StepStatus.FAILED
                step.error = result
                step.retry_count += 1
                logger.warning("[%s] failed: %s", step.id, result[:200])
                try:
                    from core.db import update_step as _db_us, emit_event as _db_em
                    _db_us(plan.task_id, step.id, "failed", error=result, provider_result=step_pr)
                    _db_em("step_failed", task_id=plan.task_id, step_id=step.id, phase="execute",
                           data={"error": result[:200]})
                except Exception:
                    pass

                if plan.replan_count < plan.max_replans:
                    revised = self.replan(plan, step, result)
                    if revised:
                        plan.replan_count += 1
                        plan.steps = revised.steps
                        self.save_plan(plan, plan_path)
                        logger.info("Replan #%d applied, %d steps",
                                    plan.replan_count, len(plan.steps))
                        return self.execute_plan(plan, plan_path, task=self._task)

                all_results.append(f"[{step.id}] FAILED: {result[:200]}")
                break

            self.save_plan(plan, plan_path)

        plan.completed_at = datetime.now(timezone.utc).isoformat()
        self.save_plan(plan, plan_path)

        return ProviderResult(
            text="\n".join(all_results) if all_results else "No steps executed",
            provider="planner",
            model="mixed",
            loop_count=len([s for s in plan.steps if s.status == StepStatus.DONE]),
        )

    def _pre_read_files(self, instruction: str) -> str:
        """Extract file paths from instruction and pre-read their contents."""
        patterns = [
            re.findall(r'Assets/\S+\.cs', instruction),
            re.findall(r'Assets/\S+\.py', instruction),
            re.findall(r'Assets/\S+\.meta', instruction),
            re.findall(r'~/Projects/\S+\.\w+', instruction),
        ]
        paths = []
        for group in patterns:
            paths.extend(group)
        paths = list(dict.fromkeys(paths))[:5]

        blocks = []
        total = 0
        for p in paths:
            full = Path(os.path.expanduser(p)) if p.startswith("~") else Path(self.cwd) / p
            full = full.resolve()
            if not full.exists() or not full.is_file():
                continue
            try:
                content = full.read_text(errors="replace")
                budget = min(4000, 12000 - total)
                if budget <= 0:
                    break
                if len(content) > budget:
                    content = content[:budget] + "\n... (truncated)"
                lines = content.split("\n")
                numbered = "\n".join(f"{i+1}\t{l}" for i, l in enumerate(lines))
                blocks.append(f"### {p}\n```\n{numbered}\n```")
                total += len(content)
            except Exception:
                pass
        return "\n\n".join(blocks) if blocks else ""

    def _execute_step(self, plan: Plan, step: PlanStep) -> Tuple[bool, str, ProviderResult]:
        prior_context = "\n".join(
            f"- {s.id}: {s.result[:100]}"
            for s in plan.steps if s.status == StepStatus.DONE
        )

        knowledge_block = ""
        if plan.knowledge:
            knowledge_block = "\n\n---\n\n".join(plan.knowledge[:3])

        safety = build_safety_prompt(self.agent)

        pre_read = self._pre_read_files(step.instruction)

        prompt = f"""{safety}

## Prior completed steps
{prior_context or "(first step)"}

## Relevant knowledge
{knowledge_block[:3000] or "(none)"}

## Pre-loaded file contents (already read for you — do NOT re-read these)
{pre_read or "(no files pre-loaded)"}

## Current step: {step.id}
{step.instruction}

## Expected outcome
{step.expected_outcome}

## Rules
- The file contents above are ALREADY LOADED. Do NOT read_file for files shown above.
- If you need other files, read them ALL in your first tool call (batch parallel reads).
- Make your edits directly using edit_file with the exact old_string from the pre-loaded content.
- Be surgical: one edit_file call per change, using exact strings from the file above.
- Report what you changed concisely."""

        result = run_phase("execute", prompt, cwd=self.cwd,
                           task_id=plan.task_id, step_id=step.id)

        if result.text.startswith("ERROR:"):
            return False, result.text, result

        return True, result.text, result

    def _verify_step(self, step: PlanStep) -> Tuple[bool, str]:
        if not step.verify_command:
            return True, "no verification"

        try:
            result = subprocess.run(
                step.verify_command, shell=True,
                capture_output=True, text=True,
                timeout=VERIFY_TIMEOUT, cwd=self.cwd,
            )
            output = (result.stdout + result.stderr).strip()

            if step.verify_check:
                if step.verify_check.lower() in output.lower():
                    return True, f"verify passed: found '{step.verify_check}'"
                if "error" in step.verify_check.lower() and result.returncode != 0:
                    return False, f"verify failed (exit {result.returncode}): {output[:300]}"
                if "no" in step.verify_check.lower() and "error" in step.verify_check.lower():
                    if result.returncode == 0 and "error" not in output.lower():
                        return True, "verify passed: no errors"
                    return False, f"verify failed: {output[:300]}"
                return False, f"verify_check '{step.verify_check}' not found in output"

            return result.returncode == 0, output[:300]
        except subprocess.TimeoutExpired:
            return False, f"verify timed out after {VERIFY_TIMEOUT}s"
        except Exception as e:
            return False, f"verify error: {e}"

    def _deps_met(self, plan: Plan, step: PlanStep) -> bool:
        if not step.depends_on:
            return True
        done_ids = {s.id for s in plan.steps if s.status == StepStatus.DONE}
        return all(d in done_ids for d in step.depends_on)

    # --- Phase 5: Replan ---

    def replan(self, plan: Plan, failed_step: PlanStep,
              failure_context: str) -> Optional[Plan]:
        if plan.replan_count >= plan.max_replans:
            logger.warning("Max replans (%d) reached", plan.max_replans)
            return None

        completed = "\n".join(
            f"- {s.id} (DONE): {s.result[:100]}"
            for s in plan.steps if s.status == StepStatus.DONE
        )
        remaining = "\n".join(
            f"- {s.id}: {s.description}"
            for s in plan.steps if s.status == StepStatus.PLANNED
        )

        knowledge_block = "\n\n---\n\n".join(plan.knowledge[:3]) if plan.knowledge else "(none)"

        prompt = f"""A plan step failed. Revise the remaining plan.

## Original goal
{plan.goal}

## Wiki knowledge
{knowledge_block[:3000]}

## Completed steps
{completed or "(none)"}

## Failed step
ID: {failed_step.id}
Description: {failed_step.description}
Instruction: {failed_step.instruction}
Error: {failure_context[:500]}

## Remaining planned steps
{remaining or "(none)"}

## Instructions
1. Analyze WHY the step failed
2. Create a REVISED plan for the remaining work (do NOT redo completed steps)
3. Fix the root cause of the failure in the revised steps
4. Output ONLY a YAML list of revised steps (same format as before)
"""

        result = run_phase("replan", prompt, cwd=self.cwd)
        if result.text.startswith("ERROR:"):
            logger.error("Replan failed: %s", result.text[:200])
            return None

        new_steps = self._parse_plan_yaml(result.text)
        if not new_steps:
            return None

        done_steps = [s for s in plan.steps if s.status == StepStatus.DONE]
        revised = Plan(
            task_id=plan.task_id,
            goal=plan.goal,
            complexity=plan.complexity,
            knowledge=plan.knowledge,
            knowledge_sources=plan.knowledge_sources,
            steps=done_steps + new_steps,
            replan_count=plan.replan_count,
            max_replans=plan.max_replans,
            created_at=plan.created_at,
        )
        return revised

    # --- Plan Persistence ---

    def save_plan(self, plan: Plan, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": plan.task_id,
            "goal": plan.goal[:200],
            "complexity": plan.complexity.value,
            "replan_count": plan.replan_count,
            "created_at": plan.created_at,
            "completed_at": plan.completed_at,
            "knowledge_sources": plan.knowledge_sources,
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "instruction": s.instruction[:300],
                    "expected_outcome": s.expected_outcome,
                    "verify_command": s.verify_command,
                    "status": s.status.value,
                    "result": s.result[:200],
                    "error": s.error[:200],
                    "retry_count": s.retry_count,
                }
                for s in plan.steps
            ],
        }
        if yaml:
            path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))
        else:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load_plan(self, path: Path) -> Plan:
        text = path.read_text()
        data = yaml.safe_load(text) if yaml else json.loads(text)
        steps = [
            PlanStep(
                id=s["id"],
                description=s.get("description", ""),
                instruction=s.get("instruction", ""),
                expected_outcome=s.get("expected_outcome", ""),
                verify_command=s.get("verify_command"),
                verify_check=s.get("verify_check"),
                status=StepStatus(s.get("status", "planned")),
                result=s.get("result", ""),
                error=s.get("error", ""),
                retry_count=s.get("retry_count", 0),
            )
            for s in data.get("steps", [])
        ]
        return Plan(
            task_id=data.get("task_id", ""),
            goal=data.get("goal", ""),
            complexity=TaskComplexity(data.get("complexity", "complex")),
            knowledge_sources=data.get("knowledge_sources", []),
            steps=steps,
            replan_count=data.get("replan_count", 0),
            created_at=data.get("created_at", ""),
        )

    def _plan_path(self, task_id: str) -> Path:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        return PLANS_DIR / f"{task_id}_{int(time.time())}.yaml"
