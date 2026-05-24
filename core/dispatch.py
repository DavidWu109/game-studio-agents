"""Dispatch runner — execute a task YAML with dependency resolution.

Usage:
    python3 -m core.dispatch projects/gopoo/studio/tasks/gamepanel-fixes.yaml

The runner:
1. Reads the YAML
2. Finds tasks whose dependencies are satisfied
3. Launches them via agent-specific handlers
4. Updates task status in the YAML
5. Repeats until all done or all blocked
6. Sends Feishu notifications at each step
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
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

def load_dispatch(yaml_path: Path) -> dict:
    with yaml_path.open() as f:
        return yaml.safe_load(f)


def save_dispatch(yaml_path: Path, data: dict):
    with yaml_path.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def mark_status(yaml_path: Path, task_id: str, status: str,
                result: str = "", error: str = ""):
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
# Phase 3: Agent Launcher (handler per task type)
# ---------------------------------------------------------------------------

def run_art_iterate(task: dict) -> str:
    """Run autoresearch loop for an art asset task."""
    task_input = task.get("input", "")

    # Check if there's a matching task YAML in autoresearch/tasks/
    task_id = task["id"]
    candidates = list(COMFYUI_DIR.glob(f"autoresearch/tasks/{task_id}*.yaml"))
    if not candidates:
        candidates = list(COMFYUI_DIR.glob("autoresearch/tasks/*.yaml"))
        # Try to match by keywords in task input
        for c in candidates:
            if any(kw in c.name for kw in task_id.split("_")):
                candidates = [c]
                break

    if candidates:
        task_yaml = candidates[0]
        logger.info("Art iterate: using %s", task_yaml)
        result = subprocess.run(
            [sys.executable, "-m", "autoresearch.loop", str(task_yaml)],
            cwd=str(COMFYUI_DIR), capture_output=True, text=True, timeout=3600)
        # Check for final.png
        lines = result.stdout.strip().split("\n")
        for line in reversed(lines):
            if "best_score=" in line:
                return line.strip()
        if result.returncode == 0:
            return f"completed (exit 0), output: {lines[-1] if lines else 'none'}"
        return f"failed (exit {result.returncode}): {result.stderr[-200:]}"
    else:
        return "no task YAML found — create one in autoresearch/tasks/"


def run_engineering_code(task: dict) -> str:
    """Delegate code changes to Claude Code CLI."""
    from core.safety import build_safety_prompt
    task_input = task.get("input", "")
    knowledge = _gather_knowledge("engineering")
    safety = build_safety_prompt("engineering")

    prompt = f"""{knowledge}

{safety}

Task: {task_input}

After making changes:
1. Verify no compile errors
2. Report what you changed
"""
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json",
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=600,
        cwd=str(GOPOO_CLIENT))
    if result.returncode != 0:
        return f"claude -p failed: {result.stderr[:300]}"
    try:
        wrapper = json.loads(result.stdout)
        return wrapper.get("result", "")[:500]
    except json.JSONDecodeError:
        return result.stdout[:500]


def run_qa_review(task: dict) -> str:
    """Capture screenshot and evaluate against checklist."""
    task_input = task.get("input", "")

    # Capture screenshot
    out_path = COMFYUI_DIR / "runs" / f"qa_review_{int(time.time())}.png"
    capture_result = subprocess.run(
        ["npx", "--yes", "unity-mcp-cli", "run-tool", "gopoo-capture-panel",
         "--input", json.dumps({"panelName": "GamePanel",
                                "outPath": str(out_path), "extraWait": 5})],
        capture_output=True, text=True, timeout=60,
        cwd=str(GOPOO_CLIENT))
    time.sleep(18)

    if not out_path.exists():
        return "capture failed — screenshot not generated"

    # Evaluate with Claude vision
    checklist_path = STUDIO_DIR / "base/qa/wiki/pages/page-review-checklist.md"
    checklist = checklist_path.read_text() if checklist_path.exists() else "standard review"

    prompt = f"""You are a QA reviewer. Read the screenshot at {out_path}.

Evaluate against this checklist:
{checklist}

SAFETY: This is a read-only review. Do NOT modify any files.

Score each section 0-10. Return JSON:
{{"sections": {{"rendering": N, "text": N, "touch": N, "layout": N, "hierarchy": N, "players": N, "content": N, "consistency": N}}, "overall": N, "issues": ["..."], "recommendations": ["..."]}}
"""
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json",
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=300)
    try:
        wrapper = json.loads(result.stdout)
        return wrapper.get("result", "")[:800]
    except (json.JSONDecodeError, KeyError):
        return f"QA eval output: {result.stdout[:500]}"


def run_studio_report(task: dict) -> str:
    """Collect all task results and send Feishu summary."""
    return "report"  # handled by dispatch_loop epilogue


# Handler registry
HANDLERS: Dict[tuple, Callable] = {
    ("art", "iterate"): run_art_iterate,
    ("art", "generate"): run_art_iterate,
    ("engineering", "code"): run_engineering_code,
    ("qa", "review"): run_qa_review,
    ("studio", "report"): run_studio_report,
}


def _gather_knowledge(dept: str) -> str:
    """Load AGENTS.md + wiki index for a department."""
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
    """Simple lock-based resource manager."""

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
# Phase 5: Dispatch Runner Loop
# ---------------------------------------------------------------------------

def notify(agent: str, message: str):
    """Send notification via Feishu."""
    try:
        notify_module = COMFYUI_DIR / "autoresearch" / "feishu_notify.py"
        if notify_module.exists():
            sys.path.insert(0, str(COMFYUI_DIR))
            from autoresearch.feishu_notify import send
            send(agent, message)
        else:
            logger.info("[%s] %s", agent, message)
    except Exception as e:
        logger.warning("Feishu notify failed: %s", e)


def dispatch_loop(yaml_path: Path, poll_interval: int = 30, dry_run: bool = False):
    """Main dispatch loop."""
    yaml_path = Path(yaml_path).resolve()
    data = load_dispatch(yaml_path)
    goal = data.get("goal", "unknown")
    total = len(data["tasks"])

    logger.info("Dispatch: %s (%d tasks)", goal, total)
    notify("Studio", f"🚀 Dispatch 开始: {goal}\n{get_status_summary(data)}")

    if dry_run:
        ready = get_ready_tasks(data)
        logger.info("Dry run — ready tasks: %s", [t["id"] for t in ready])
        for t in ready:
            logger.info("  %s → %s.%s", t["id"], t["agent"], t["action"])
        return

    resources = ResourceManager()
    max_iterations = total * 3  # safety limit
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        data = load_dispatch(yaml_path)

        if all_done(data):
            logger.info("All tasks done!")
            notify("Studio", f"✅ Dispatch 完成: {goal}\n{get_status_summary(data)}")
            break

        ready = get_ready_tasks(data)

        if not ready:
            if any_blocked(data):
                blocked = [t["id"] for t in data["tasks"] if t.get("status") == "blocked"]
                logger.warning("Blocked tasks: %s", blocked)
                notify("Studio", f"❌ Dispatch 阻塞: {blocked}\n需要人工介入")
                break
            # Nothing ready but not done — tasks still in_progress
            in_progress = [t["id"] for t in data["tasks"] if t.get("status") == "in_progress"]
            if in_progress:
                logger.info("Waiting for: %s", in_progress)
                time.sleep(poll_interval)
                continue
            # Stuck — all planned but deps not met (shouldn't happen)
            logger.error("Stuck — no ready tasks, no in_progress, not all done")
            notify("Studio", f"⚠️ Dispatch 卡住了\n{get_status_summary(data)}")
            break

        # Launch ready tasks
        for task in ready:
            agent, action = task["agent"], task["action"]
            handler = HANDLERS.get((agent, action))
            if not handler:
                logger.warning("No handler for %s.%s — skipping %s", agent, action, task["id"])
                mark_status(yaml_path, task["id"], "blocked", error=f"no handler for {agent}.{action}")
                notify(agent, f"❌ {task['id']}: 没有执行器")
                continue

            if not resources.acquire(agent, action):
                logger.info("Resource busy for %s.%s — will retry", agent, action)
                continue

            # Safety pre-check
            from core.safety import pre_execute_check, post_execute_check
            ok, reason = pre_execute_check(agent, task)
            if not ok:
                mark_status(yaml_path, task["id"], "blocked", error=f"SAFETY: {reason}")
                notify(agent, f"🛑 安全拦截: {task['id']}\n{reason}")
                logger.warning("Safety blocked: %s → %s", task["id"], reason)
                resources.release(agent, action)
                continue

            mark_status(yaml_path, task["id"], "in_progress")
            notify(agent, f"⚙️ 开始: {task['id']}")
            logger.info("Starting: %s (%s.%s)", task["id"], agent, action)

            try:
                result = handler(task)

                # Safety post-check
                warnings = post_execute_check(agent, task, str(result))
                if warnings:
                    for w in warnings:
                        notify(agent, f"⚠️ 安全警告: {w}")
                        logger.warning("Safety warning for %s: %s", task["id"], w)

                mark_status(yaml_path, task["id"], "done", result=str(result)[:500])
                notify(agent, f"✅ 完成: {task['id']}\n{str(result)[:200]}")
                logger.info("Done: %s → %s", task["id"], str(result)[:100])
            except Exception as e:
                mark_status(yaml_path, task["id"], "blocked", error=str(e)[:300])
                notify(agent, f"❌ 失败: {task['id']}\n{str(e)[:200]}")
                logger.error("Failed: %s → %s", task["id"], e)
            finally:
                resources.release(agent, action)

    # Final summary
    data = load_dispatch(yaml_path)
    summary_lines = []
    for t in data["tasks"]:
        status = t.get("status", "planned")
        icon = {"done": "✅", "blocked": "❌", "in_progress": "⏳"}.get(status, "⬜")
        result = t.get("result", t.get("blocked_reason", ""))[:80]
        summary_lines.append(f"{icon} {t['id']} ({t['agent']}) — {result or status}")

    summary = "\n".join(summary_lines)
    notify("Studio", f"📋 Dispatch 报告: {goal}\n\n{summary}")
    logger.info("Dispatch finished:\n%s", summary)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    p = argparse.ArgumentParser(description="Run a task dispatch YAML")
    p.add_argument("yaml_file", type=Path, help="Path to dispatch YAML")
    p.add_argument("--dry", action="store_true", help="Show plan without executing")
    p.add_argument("--poll", type=int, default=30, help="Poll interval in seconds")
    args = p.parse_args()

    if not args.yaml_file.exists():
        print(f"File not found: {args.yaml_file}", file=sys.stderr)
        sys.exit(1)

    dispatch_loop(args.yaml_file, poll_interval=args.poll, dry_run=args.dry)


if __name__ == "__main__":
    main()
