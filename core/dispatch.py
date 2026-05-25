"""Dispatch runner — execute a task YAML with dependency resolution.

Usage:
    python3 -m core.dispatch tasks.yaml [--dry] [--poll 30]

Fixes from v0.7 dispatch (dispatch-issues-v2.md):
1. Parallel execution via threading (not single-threaded)
2. Explicit task_yaml field for art tasks (no guessing)
3. Parse panel name from task input for QA
4. Result validation before marking done
5. --dangerously-skip-permissions with proper flag ordering

Architecture Interfaces (stubs at end of file):

Interface #1 — QA Feedback Loop (ReAct at dispatch level)
    After QA task completes, check score against QA_GATE_THRESHOLD.
    If below, find upstream task → call agent.on_qa_feedback() → retry.
    Constants: QA_GATE_THRESHOLD, MAX_QA_RETRIES
    Functions: _handle_qa_feedback(), _find_upstream_task()

Interface #2 — Dynamic Replan (Plan-and-Execute)
    Dispatch loop checks replan triggers each round.
    If fired, calls PjM agent's replan() → replaces planned tasks.
    Constants: REPLAN_TRIGGERS
    Functions: _check_replan_triggers(), _apply_replan()

Interface #4 — Daemon hook
    dispatch_loop() can be called by daemon.py instead of CLI main().
    daemon.py watches for new YAML files and starts dispatch_loop() per file.
    See: core/daemon.py (to be created)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("pip install pyyaml", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("dispatch")

STUDIO_DIR = Path(__file__).parent.parent
COMFYUI_DIR = Path(os.path.expanduser("~/Projects/comfyui_workflow"))
GOPOO_CLIENT = Path(os.path.expanduser("~/Projects/go-poo-client"))

# ---------------------------------------------------------------------------
# Phase 1: Task Status Persistence
# ---------------------------------------------------------------------------

_yaml_lock = threading.Lock()


def load_dispatch(yaml_path: Path) -> dict:
    with yaml_path.open() as f:
        return yaml.safe_load(f)


def save_dispatch(yaml_path: Path, data: dict):
    with yaml_path.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def mark_status(yaml_path: Path, task_id: str, status: str,
                result: str = "", error: str = ""):
    with _yaml_lock:
        data = load_dispatch(yaml_path)
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["status"] = status
                if status == "done":
                    t["completed"] = datetime.now(timezone.utc).isoformat()
                    t["result"] = result
                elif status == "blocked":
                    t["blocked_reason"] = error
                elif status == "in_progress":
                    t["started"] = datetime.now(timezone.utc).isoformat()
        save_dispatch(yaml_path, data)


# ---------------------------------------------------------------------------
# Phase 2: Dependency Resolver
# ---------------------------------------------------------------------------

def get_ready_tasks(data: dict) -> List[dict]:
    done_ids = {t["id"] for t in data["tasks"] if t.get("status") == "done"}
    ready = []
    for t in data["tasks"]:
        if t.get("status") not in (None, "planned"):
            continue
        deps = set(t.get("depends_on") or [])
        if deps.issubset(done_ids):
            ready.append(t)
    return ready


def all_done(data: dict) -> bool:
    return all(t.get("status") == "done" for t in data["tasks"])


def any_blocked(data: dict) -> bool:
    return any(t.get("status") == "blocked" for t in data["tasks"])


def get_status_summary(data: dict) -> str:
    counts = {}
    for t in data["tasks"]:
        s = t.get("status", "planned")
        counts[s] = counts.get(s, 0) + 1
    return " | ".join(f"{k}:{v}" for k, v in sorted(counts.items()))


# ---------------------------------------------------------------------------
# Phase 3: Agent Launcher — FIX #2: explicit task_yaml field
# ---------------------------------------------------------------------------

def run_art_iterate(task: dict) -> str:
    """Run autoresearch loop for an art asset task."""
    # FIX #2: use explicit task_yaml field if provided
    explicit_yaml = task.get("task_yaml")
    if explicit_yaml:
        task_yaml = COMFYUI_DIR / explicit_yaml
    else:
        task_id = task["id"]
        candidates = list(COMFYUI_DIR.glob(f"autoresearch/tasks/{task_id}*.yaml"))
        if candidates:
            task_yaml = candidates[0]
        else:
            return f"ERROR: no task YAML found for '{task_id}'. Add task_yaml field to dispatch."

    if not task_yaml.exists():
        return f"ERROR: task YAML not found: {task_yaml}"

    logger.info("Art iterate: using %s", task_yaml)
    result = subprocess.run(
        [sys.executable, "-m", "autoresearch.loop", str(task_yaml)],
        cwd=str(COMFYUI_DIR), capture_output=True, text=True, timeout=3600)

    lines = result.stdout.strip().split("\n")
    for line in reversed(lines):
        if "best_score=" in line:
            return line.strip()
    if result.returncode == 0:
        return f"completed (exit 0), output: {lines[-1] if lines else 'none'}"
    return f"failed (exit {result.returncode}): {result.stderr[-200:]}"


def run_engineering_code(task: dict) -> str:
    """Delegate code changes via planner (complex) or tool runner (simple)."""
    from core.planner import Planner

    planner = Planner(agent="engineering", cwd=str(GOPOO_CLIENT))
    result = planner.run(task)
    if result.text.startswith("ERROR:"):
        return f"planner failed ({result.provider}): {result.text[:300]}"
    return result.text[:500]


def _parse_panel_name(task_input: str) -> str:
    """FIX #4: Extract panel name from task input."""
    panels = ["MainMenuPanel", "GamePanel", "LobbyPanel", "ResultPanel"]
    for p in panels:
        if p.lower() in task_input.lower():
            return p
    # Try shorter names
    for short, full in [("mainmenu", "MainMenuPanel"), ("main menu", "MainMenuPanel"),
                        ("lobby", "LobbyPanel"), ("game", "GamePanel"),
                        ("result", "ResultPanel")]:
        if short in task_input.lower():
            return full
    return "GamePanel"


def run_qa_review(task: dict) -> str:
    """Capture screenshot and evaluate against checklist."""
    task_input = task.get("input", "")
    panel_name = _parse_panel_name(task_input)

    out_path = COMFYUI_DIR / "runs" / f"qa_{panel_name}_{int(time.time())}.png"

    # Build panel first
    subprocess.run(
        ["npx", "--yes", "unity-mcp-cli", "run-tool", "gopoo-exec-menu",
         "--input", json.dumps({"menuPath": f"GoPoo/Build Panels/{panel_name.replace('Panel','').strip()} Panel"})],
        capture_output=True, text=True, timeout=30,
        cwd=str(GOPOO_CLIENT))
    time.sleep(3)

    # Capture
    subprocess.run(
        ["npx", "--yes", "unity-mcp-cli", "run-tool", "gopoo-capture-panel",
         "--input", json.dumps({"panelName": panel_name,
                                "outPath": str(out_path), "extraWait": 5})],
        capture_output=True, text=True, timeout=60,
        cwd=str(GOPOO_CLIENT))
    time.sleep(18)

    if not out_path.exists():
        return f"capture failed for {panel_name} — screenshot not generated"

    checklist_path = STUDIO_DIR / "base/qa/wiki/pages/page-review-checklist.md"
    checklist = checklist_path.read_text()[:3000] if checklist_path.exists() else "standard review"

    prompt = f"""Read the screenshot at {out_path}. This is the {panel_name}.

Evaluate against this checklist:
{checklist}

Score each section 0-10. Return ONLY this JSON:
{{"panel": "{panel_name}", "sections": {{"rendering": N, "text": N, "touch": N, "layout": N, "hierarchy": N, "players": N, "content": N, "consistency": N}}, "overall": N, "issues": ["..."], "recommendations": ["..."]}}
"""
    # QA always routes to CLI (hallucination risk too high for DeepSeek)
    from core.provider import run_prompt
    qa_task = dict(task, provider="cli")
    result = run_prompt(prompt, qa_task)
    return result.text[:800]


def run_studio_report(task: dict) -> str:
    """Collect all results, build screenshot grid, send Feishu report with images."""
    from PIL import Image, ImageDraw

    # Collect screenshots (QA captures + art finals)
    screenshots = {}
    runs_dir = COMFYUI_DIR / "runs"

    # Find QA screenshots (newest per panel name)
    for f in sorted(runs_dir.glob("qa_*.png"), key=lambda p: p.stat().st_mtime):
        for panel in ["GamePanel", "MainMenuPanel", "LobbyPanel", "ResultPanel"]:
            if panel.lower() in f.name.lower():
                screenshots[panel] = f

    # Find art finals from recent runs
    for run_dir in sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not run_dir.is_dir():
            continue
        for final in run_dir.rglob("final.png"):
            name = run_dir.name
            if name not in screenshots:
                screenshots[name] = final
            if len(screenshots) >= 8:
                break

    if not screenshots:
        return "report: no screenshots found"

    # Build grid
    items = list(screenshots.items())[:8]
    cols = min(len(items), 2)
    rows = (len(items) + cols - 1) // cols
    thumb_w, thumb_h = 640, 360
    grid = Image.new("RGB", (cols * thumb_w, rows * thumb_h + 40), (30, 30, 30))
    draw = ImageDraw.Draw(grid)
    draw.text((10, 8), f"Dispatch Report — {len(items)} screenshots", fill="white")

    for i, (name, path) in enumerate(items):
        try:
            img = Image.open(path).resize((thumb_w, thumb_h), Image.LANCZOS)
        except Exception:
            img = Image.new("RGB", (thumb_w, thumb_h), (60, 60, 60))
        x = (i % cols) * thumb_w
        y = (i // cols) * thumb_h + 40
        grid.paste(img, (x, y))
        draw.text((x + 5, y + 3), name, fill="yellow")

    grid_path = runs_dir / f"dispatch_report_{int(time.time())}.png"
    grid.save(grid_path)

    # Send via Feishu
    try:
        sys.path.insert(0, str(COMFYUI_DIR))
        from autoresearch.feishu_notify import send_image
        send_image("Studio", f"📋 Dispatch 截图报告 ({len(items)} panels)", str(grid_path))
    except Exception as e:
        logger.warning("Report image send failed: %s", e)

    return f"report sent with {len(items)} screenshots: {[n for n,_ in items]}"


def run_design_code(task: dict) -> str:
    """Run Design agent code tasks via planner (complex) or tool runner (simple)."""
    from core.planner import Planner

    project_dir = Path(os.path.expanduser("~/Projects/gopoo-studio-project"))
    planner = Planner(agent="design", cwd=str(project_dir))
    result = planner.run(task)
    if result.text.startswith("ERROR:"):
        return f"planner failed ({result.provider}): {result.text[:300]}"
    return result.text[:500]


HANDLERS: Dict[tuple, Callable] = {
    ("art", "iterate"): run_art_iterate,
    ("art", "generate"): run_art_iterate,
    ("design", "code"): run_design_code,
    ("engineering", "code"): run_engineering_code,
    ("qa", "review"): run_qa_review,
    ("studio", "report"): run_studio_report,
}


def _gather_knowledge(dept: str) -> str:
    parts = []
    for base in [STUDIO_DIR / "base" / dept,
                 Path(os.path.expanduser("~/Projects/gopoo-studio-project")) / dept]:
        agents_md = base / "AGENTS.md"
        if agents_md.exists():
            parts.append(agents_md.read_text()[:3000])
        index_md = base / "wiki" / "index.md"
        if index_md.exists():
            parts.append(index_md.read_text()[:2000])
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 4: Resource Manager
# ---------------------------------------------------------------------------

class ResourceManager:
    def __init__(self):
        self._locks: Dict[str, threading.Lock] = {
            "comfyui": threading.Lock(),
            "unity_mcp": threading.Lock(),
        }
        self._resource_map = {
            ("art", "iterate"): "comfyui",
            ("art", "generate"): "comfyui",
            ("engineering", "code"): "unity_mcp",
            ("qa", "review"): "unity_mcp",
        }

    def acquire(self, agent: str, action: str) -> bool:
        resource = self._resource_map.get((agent, action))
        if resource is None:
            return True
        return self._locks[resource].acquire(blocking=False)

    def release(self, agent: str, action: str):
        resource = self._resource_map.get((agent, action))
        if resource and self._locks[resource].locked():
            self._locks[resource].release()


# ---------------------------------------------------------------------------
# Phase 5: Result Validation — FIX #5
# ---------------------------------------------------------------------------

def validate_result(task: dict, result: str) -> tuple[bool, str]:
    """Check if result indicates real success, not a permission/error message."""
    agent, action = task["agent"], task["action"]
    result_lower = result.lower()

    # Generic failure indicators
    failure_phrases = [
        "waiting for you to grant",
        "permission",
        "could you approve",
        "could you grant",
        "i need access",
        "cannot proceed",
        "error: response data is null",
    ]
    for phrase in failure_phrases:
        if phrase in result_lower:
            return False, f"result contains failure indicator: '{phrase}'"

    # Per-type validation
    if agent == "art" and action == "iterate":
        if "score=" not in result and "completed" not in result_lower:
            return False, "art result missing score or completion indicator"

    if agent == "engineering" and action == "code":
        if len(result) < 20:
            return False, "engineering result too short — likely no changes made"

    if agent == "qa" and action == "review":
        if "sections" not in result and "rendering" not in result:
            return False, "QA result missing sections/scores"

    return True, "ok"


# ---------------------------------------------------------------------------
# Phase 6: Dispatch Loop — FIX #1: parallel execution
# ---------------------------------------------------------------------------

TASK_TIMEOUT = {
    ("art", "iterate"): 1800,
    ("engineering", "code"): 600,
    ("qa", "review"): 300,
    ("studio", "report"): 120,
}


def notify(agent: str, message: str):
    try:
        sys.path.insert(0, str(COMFYUI_DIR))
        from autoresearch.feishu_notify import send
        send(agent, message)
    except Exception as e:
        logger.warning("Feishu notify failed: %s", e)


def _run_task(task: dict, yaml_path: Path, resources: ResourceManager) -> tuple[str, str]:
    """Execute a single task. Returns (task_id, result_or_error)."""
    agent, action = task["agent"], task["action"]
    task_id = task["id"]

    handler = HANDLERS.get((agent, action))
    if not handler:
        return task_id, f"ERROR: no handler for {agent}.{action}"

    # Acquire resource (blocking wait with timeout for parallel tasks)
    resource_key = resources._resource_map.get((agent, action))
    if resource_key:
        lock = resources._locks[resource_key]
        acquired = lock.acquire(timeout=TASK_TIMEOUT.get((agent, action), 600))
        if not acquired:
            return task_id, "ERROR: resource timeout"
    else:
        lock = None

    try:
        from core.safety import pre_execute_check, post_execute_check
        ok, reason = pre_execute_check(agent, task)
        if not ok:
            return task_id, f"SAFETY_BLOCK: {reason}"

        mark_status(yaml_path, task_id, "in_progress")
        notify(agent, f"⚙️ 开始: {task_id}")
        logger.info("Starting: %s (%s.%s)", task_id, agent, action)

        timeout = TASK_TIMEOUT.get((agent, action), 600)
        result = handler(task)

        # FIX #5: validate result
        valid, reason = validate_result(task, str(result))
        if not valid:
            notify(agent, f"⚠️ 结果无效: {task_id} — {reason}")
            logger.warning("Invalid result for %s: %s", task_id, reason)
            return task_id, f"INVALID: {reason} | raw: {str(result)[:200]}"

        warnings = post_execute_check(agent, task, str(result))
        for w in warnings:
            notify(agent, f"⚠️ {w}")

        return task_id, str(result)[:500]

    except Exception as e:
        return task_id, f"ERROR: {str(e)[:300]}"
    finally:
        if lock and lock.locked():
            lock.release()


def _reset_stale_in_progress(yaml_path: Path, max_age_seconds: int = 600):
    """On startup, reset tasks stuck in_progress from a crashed previous run."""
    with _yaml_lock:
        data = load_dispatch(yaml_path)
        now = datetime.now(timezone.utc)
        reset_count = 0
        for t in data["tasks"]:
            if t.get("status") != "in_progress":
                continue
            started = t.get("started", "")
            if started:
                try:
                    started_dt = datetime.fromisoformat(started)
                    age = (now - started_dt).total_seconds()
                    if age > max_age_seconds:
                        logger.warning("Resetting stale task %s (in_progress for %ds)", t["id"], int(age))
                        t["status"] = "planned"
                        if "started" in t:
                            del t["started"]
                        reset_count += 1
                except (ValueError, TypeError):
                    t["status"] = "planned"
                    reset_count += 1
            else:
                t["status"] = "planned"
                reset_count += 1
        if reset_count:
            save_dispatch(yaml_path, data)
            logger.info("Reset %d stale in_progress tasks", reset_count)
        return reset_count


def dispatch_loop(yaml_path: Path, poll_interval: int = 15, dry_run: bool = False):
    """Main dispatch loop with parallel execution."""
    yaml_path = Path(yaml_path).resolve()

    # Recover from previous crash
    reset_count = _reset_stale_in_progress(yaml_path)
    if reset_count:
        notify("Studio", f"🔄 恢复: 重置了 {reset_count} 个上次崩溃遗留的 in_progress 任务")

    data = load_dispatch(yaml_path)
    goal = data.get("goal", "unknown")
    total = len(data["tasks"])

    logger.info("Dispatch: %s (%d tasks)", goal, total)
    notify("Studio", f"🚀 Dispatch 开始: {goal}\n任务数: {total}\n{get_status_summary(data)}")

    if dry_run:
        ready = get_ready_tasks(data)
        logger.info("Dry run — ready tasks: %s", [t["id"] for t in ready])
        for t in ready:
            logger.info("  %s → %s.%s (resource: %s)", t["id"], t["agent"], t["action"],
                       ResourceManager()._resource_map.get((t["agent"], t["action"]), "none"))
        return

    resources = ResourceManager()
    max_rounds = total * 3
    executor = ThreadPoolExecutor(max_workers=3)

    for round_n in range(max_rounds):
        data = load_dispatch(yaml_path)

        if all_done(data):
            logger.info("All tasks done!")
            break

        ready = get_ready_tasks(data)
        if not ready:
            in_progress = [t["id"] for t in data["tasks"] if t.get("status") == "in_progress"]
            if in_progress:
                logger.info("Round %d: waiting for %s", round_n, in_progress)
                time.sleep(poll_interval)
                continue
            if any_blocked(data):
                blocked = [t["id"] for t in data["tasks"] if t.get("status") == "blocked"]
                notify("Studio", f"❌ 阻塞: {blocked}")
                break
            notify("Studio", f"⚠️ 卡住了\n{get_status_summary(data)}")
            break

        # FIX #1: Launch ready tasks in parallel via ThreadPoolExecutor
        logger.info("Round %d: launching %d tasks: %s", round_n,
                    len(ready), [t["id"] for t in ready])

        futures = {}
        for task in ready:
            future = executor.submit(_run_task, task, yaml_path, resources)
            futures[future] = task

        for future in as_completed(futures):
            task = futures[future]
            task_id = task["id"]
            try:
                tid, result = future.result(timeout=1900)

                if result.startswith("ERROR:") or result.startswith("SAFETY_BLOCK:"):
                    mark_status(yaml_path, tid, "blocked", error=result)
                    notify(task["agent"], f"❌ {tid}: {result[:150]}")
                    logger.error("Blocked: %s → %s", tid, result[:100])
                elif result.startswith("INVALID:"):
                    mark_status(yaml_path, tid, "blocked", error=result)
                    notify(task["agent"], f"⚠️ {tid} 结果无效，标记阻塞:\n{result[:150]}")
                    logger.warning("Invalid: %s → %s", tid, result[:100])
                else:
                    mark_status(yaml_path, tid, "done", result=result)
                    notify(task["agent"], f"✅ {tid}\n{result[:150]}")
                    logger.info("Done: %s → %s", tid, result[:80])
            except Exception as e:
                mark_status(yaml_path, task_id, "blocked", error=str(e)[:300])
                notify(task["agent"], f"❌ {task_id}: {str(e)[:150]}")

    # Final summary
    executor.shutdown(wait=False)
    data = load_dispatch(yaml_path)
    lines = []
    for t in data["tasks"]:
        s = t.get("status", "planned")
        icon = {"done": "✅", "blocked": "❌", "in_progress": "⏳"}.get(s, "⬜")
        r = t.get("result", t.get("blocked_reason", ""))
        lines.append(f"{icon} {t['id']} ({t['agent']}) — {str(r)[:60] if r else s}")

    summary = "\n".join(lines)
    notify("Studio", f"📋 Dispatch 完了: {goal}\n\n{summary}")
    logger.info("Dispatch finished:\n%s", summary)


# ---------------------------------------------------------------------------
# Interface #1: QA Feedback Loop (ReAct at dispatch level)
# ---------------------------------------------------------------------------
# When implemented, call _handle_qa_feedback() after QA task completes in
# the dispatch_loop's future-completion block (line ~598).
# Insert between validate_result() and mark_status("done").

QA_GATE_THRESHOLD = 7.5
MAX_QA_RETRIES = 2


def _find_upstream_task(data: dict, qa_task: dict) -> Optional[dict]:
    """Find the engineering/art task that produced QA's input.

    Walk depends_on chain backward from qa_task to find the first
    non-QA task. Returns the task dict, or None.
    """
    # TODO: implement — traverse depends_on links in data["tasks"]
    raise NotImplementedError


def _extract_qa_score(result: str) -> Optional[float]:
    """Parse overall score from QA result JSON.

    QA results contain: {"sections": {...}, "overall": float, "issues": [...]}
    Returns the 'overall' score, or None if unparseable.
    """
    try:
        # QA result may be embedded in a larger string; find JSON block
        import re as _re
        match = _re.search(r'\{[^{}]*"overall"\s*:\s*([\d.]+)', result)
        if match:
            return float(match.group(1))
    except (ValueError, AttributeError):
        pass
    return None


def _handle_qa_feedback(yaml_path: Path, qa_task: dict, qa_result: str,
                        data: dict) -> bool:
    """Check QA score and retry upstream task if below threshold.

    Returns True if a retry was scheduled, False if passed or exhausted retries.

    Call site: dispatch_loop, after qa_task completes successfully.
    Insert at ~line 598, before mark_status("done") for qa tasks:

        if qa_task["agent"] == "qa" and qa_task["action"] == "review":
            score = _extract_qa_score(result)
            if score is not None and score < QA_GATE_THRESHOLD:
                retried = _handle_qa_feedback(yaml_path, qa_task, result, data)
                if retried:
                    continue  # don't mark qa as done, upstream will re-run
    """
    # TODO: implement
    # 1. _find_upstream_task(data, qa_task)
    # 2. Check upstream.retry_count < MAX_QA_RETRIES
    # 3. Call agent.on_qa_feedback(upstream, qa_result_parsed)
    # 4. If revised: reset upstream to "planned" with new input, return True
    # 5. If None or retries exhausted: escalate to human, return False
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Interface #2: Dynamic Replan (Plan-and-Execute)
# ---------------------------------------------------------------------------
# When implemented, call _check_replan_triggers() at the start of each
# dispatch_loop round (line ~554), before get_ready_tasks().

REPLAN_TRIGGERS = [
    {"condition": "any_blocked_over_30min", "action": "pjm.replan"},
    {"condition": "qa_failed_after_max_retries", "action": "pjm.escalate_and_replan"},
    {"condition": "all_art_plateaued", "action": "pjm.replan"},
]


def _check_replan_triggers(yaml_path: Path, data: dict) -> Optional[str]:
    """Evaluate replan trigger conditions against current dispatch state.

    Returns trigger reason string if any condition is met, None otherwise.

    Conditions to check:
    - any_blocked_over_30min: task status=blocked, age > 1800s
    - qa_failed_after_max_retries: QA task done with score < threshold
      AND upstream retry_count >= MAX_QA_RETRIES
    - all_art_plateaued: all art tasks done with plateau flag

    Call site: dispatch_loop, at start of each round (line ~554):

        trigger = _check_replan_triggers(yaml_path, data)
        if trigger:
            _apply_replan(yaml_path, data, trigger)
    """
    # TODO: implement — evaluate each REPLAN_TRIGGERS condition
    return None


def _apply_replan(yaml_path: Path, data: dict, trigger_reason: str):
    """Invoke PjM agent's replan() and apply the revised task DAG.

    1. Instantiate PjM agent
    2. Call pjm.replan(data, trigger_reason)
    3. If revised data returned, save_dispatch() with new tasks
    4. Log the replan event
    5. Notify Studio about the replan
    """
    # TODO: implement
    # from core.agent import StudioAgent  # or PjMAgent subclass
    # pjm = PjMAgent(...)
    # revised = pjm.replan(data, trigger_reason)
    # if revised: save_dispatch(yaml_path, revised)
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Task YAML Schema Extensions (for interfaces above)
# ---------------------------------------------------------------------------
# When implementing the interfaces, add these fields to task dicts:
#
#   retry_count: int      — incremented by _handle_qa_feedback()
#   qa_score: float       — written by QA handler on completion
#   plateau: bool         — set by art handler when AutoResearch plateaus
#   replan_history: list  — appended by _apply_replan() with timestamps
#
# Example task with new fields:
#   - id: gp_layout_fix
#     agent: engineering
#     action: code
#     input: "..."
#     status: done
#     retry_count: 1
#     qa_score: 7.8


def main():
    import argparse
    p = argparse.ArgumentParser(description="Run a task dispatch YAML")
    p.add_argument("yaml_file", type=Path)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--poll", type=int, default=15)
    args = p.parse_args()
    if not args.yaml_file.exists():
        sys.exit(f"File not found: {args.yaml_file}")
    dispatch_loop(args.yaml_file, poll_interval=args.poll, dry_run=args.dry)


if __name__ == "__main__":
    main()
