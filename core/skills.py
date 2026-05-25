"""Skill layer — multi-step operations with pre-checks.

Sits between dispatch/planner (agent layer) and tool_runner (tool layer).
Skills encapsulate complex operations like Unity control, screenshot QA,
and Feishu reporting that would otherwise be hardcoded in dispatch handlers.

Usage:
    from core.skills import registry
    result = registry.run("unity_control.build_panel", {"panel_name": "GamePanel"})
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("skills")

GOPOO_CLIENT = Path(os.path.expanduser("~/Projects/go-poo-client"))
COMFYUI_DIR = Path(os.path.expanduser("~/Projects/comfyui_workflow"))
STUDIO_DIR = Path(__file__).parent.parent


@dataclass
class SkillResult:
    success: bool
    text: str
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Skill Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, dict] = {}

    def register(self, name: str, execute: Callable, pre_check: Optional[Callable] = None,
                 description: str = "", timeout: int = 60):
        self._skills[name] = {
            "execute": execute,
            "pre_check": pre_check,
            "description": description,
            "timeout": timeout,
        }

    def get(self, name: str) -> Optional[dict]:
        return self._skills.get(name)

    def list_all(self) -> List[str]:
        return list(self._skills.keys())

    def run(self, name: str, args: dict = None) -> SkillResult:
        skill = self._skills.get(name)
        if not skill:
            return SkillResult(False, f"ERROR: unknown skill '{name}'")

        if skill["pre_check"]:
            ok, msg = skill["pre_check"]()
            if not ok:
                logger.warning("Skill %s pre-check failed: %s", name, msg)
                _notify_skill_failure(name, msg)
                return SkillResult(False, f"ERROR: pre-check failed: {msg}")

        try:
            return skill["execute"](args or {})
        except Exception as e:
            logger.error("Skill %s failed: %s", name, e)
            return SkillResult(False, f"ERROR: {e}")


def _notify_skill_failure(skill_name: str, message: str):
    try:
        sys.path.insert(0, str(COMFYUI_DIR))
        from autoresearch.feishu_notify import send
        send("Skills", f"⚠️ Skill 前置检查失败: {skill_name}\n{message}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Unity Control Skill
# ---------------------------------------------------------------------------

UNITY_MCP_URL = os.environ.get("UNITY_MCP_URL", "http://localhost:25891")


def _unity_mcp_call(tool_name: str, input_data: dict, timeout: int = 30) -> Tuple[bool, str]:
    import urllib.request
    import urllib.error

    url = f"{UNITY_MCP_URL}/api/tools/{tool_name}"
    body = json.dumps(input_data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            status = data.get("status", "")
            if status == "success":
                result_text = json.dumps(data.get("structured", data), ensure_ascii=False)
                return True, result_text[:500]
            return False, f"MCP returned status={status}: {json.dumps(data)[:300]}"
    except urllib.error.URLError as e:
        return False, f"MCP connection failed: {e.reason}"
    except TimeoutError:
        return False, f"MCP call timed out after {timeout}s"
    except Exception as e:
        return False, f"MCP call error: {e}"


def _unity_pre_check() -> Tuple[bool, str]:
    ok, msg = _unity_mcp_call("gopoo-exec-menu",
                               {"menuPath": "Help/About Unity"}, timeout=10)
    if ok:
        return True, "Unity MCP reachable"
    return False, f"Unity Editor 未运行 — 请先启动 Unity Editor\n{msg}"


def _unity_refresh(args: dict) -> SkillResult:
    ok, msg = _unity_mcp_call("gopoo-exec-menu",
                               {"menuPath": "Assets/Refresh"}, timeout=30)
    if ok:
        return SkillResult(True, "Assets refreshed")
    return SkillResult(False, f"Refresh failed: {msg}")


def _unity_build_panel(args: dict) -> SkillResult:
    panel_name = args.get("panel_name", "GamePanel")
    menu_name = panel_name.replace("Panel", "").strip() + " Panel"

    ok, msg = _unity_mcp_call("gopoo-exec-menu",
                               {"menuPath": "Assets/Refresh"}, timeout=30)
    if not ok:
        return SkillResult(False, f"Refresh failed: {msg}")

    time.sleep(2)

    ok, msg = _unity_mcp_call("gopoo-exec-menu",
                               {"menuPath": f"GoPoo/Build Panels/{menu_name}"}, timeout=30)
    if not ok:
        return SkillResult(False, f"Build failed: {msg}")

    time.sleep(3)
    return SkillResult(True, f"Built {panel_name}", {"panel_name": panel_name})


def _unity_ensure_running(args: dict) -> SkillResult:
    ok, msg = _unity_pre_check()
    if ok:
        return SkillResult(True, "Unity already running")

    # Try to launch Unity/Tuanjie via macOS `open` command
    import glob
    editor_candidates = (
        glob.glob("/Applications/Tuanjie/Tuanjie.app") +
        glob.glob("/Applications/Unity/Hub/Editor/*/Unity.app") +
        glob.glob("/Applications/Unity*.app")
    )
    project = str(GOPOO_CLIENT)
    if editor_candidates:
        app = editor_candidates[0]
        subprocess.Popen(["open", "-a", app, "--args", "-projectPath", project],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Launched editor: %s with project %s", app, project)
    elif Path("/Applications/Unity Hub.app").exists():
        subprocess.Popen(["open", "-a", "Unity Hub"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Launched Unity Hub")
    else:
        return SkillResult(False, "Cannot find Unity/Tuanjie installation")

    # Wait for MCP to become reachable
    for attempt in range(12):
        time.sleep(10)
        ok, msg = _unity_pre_check()
        if ok:
            return SkillResult(True, f"Unity started after {(attempt+1)*10}s")

    return SkillResult(False, "Unity launched but MCP not reachable after 120s")


# ---------------------------------------------------------------------------
# Screenshot QA Skill
# ---------------------------------------------------------------------------

def _qa_pre_check() -> Tuple[bool, str]:
    return _unity_pre_check()


def _qa_capture(args: dict) -> SkillResult:
    panel_name = args.get("panel_name", "GamePanel")
    out_path = args.get("out_path")
    if not out_path:
        out_path = str(COMFYUI_DIR / "runs" / f"qa_{panel_name}_{int(time.time())}.png")

    # Ensure correct scene is loaded before capture
    _unity_mcp_call("gopoo-open-scene",
                     {"scenePath": "Assets/Scenes/GameScene.unity"}, timeout=15)
    time.sleep(2)

    ok, msg = _unity_mcp_call("gopoo-capture-panel",
                               {"panelName": panel_name,
                                "outPath": out_path,
                                "extraWait": 5}, timeout=60)
    if not ok:
        return SkillResult(False, f"Capture failed: {msg}")

    time.sleep(18)

    if not Path(out_path).exists():
        return SkillResult(False, f"Screenshot not generated at {out_path}")

    return SkillResult(True, f"Captured {panel_name}", {"path": out_path})


def _qa_evaluate(args: dict) -> SkillResult:
    screenshot_path = args.get("screenshot_path", "")
    if not screenshot_path or not Path(screenshot_path).exists():
        return SkillResult(False, f"Screenshot not found: {screenshot_path}")

    checklist_path = STUDIO_DIR / "base/qa/wiki/pages/page-review-checklist.md"
    checklist = checklist_path.read_text()[:3000] if checklist_path.exists() else "standard review"

    panel_name = args.get("panel_name", "GamePanel")
    prompt = f"""Read the screenshot at {screenshot_path}. This is the {panel_name}.

Evaluate against this checklist:
{checklist}

Score each section 0-10. Return ONLY this JSON:
{{"panel": "{panel_name}", "sections": {{"rendering": N, "text": N, "touch": N, "layout": N, "hierarchy": N, "players": N, "content": N, "consistency": N}}, "overall": N, "issues": ["..."], "recommendations": ["..."]}}
"""
    from core.provider import run_cli
    result = run_cli(prompt, timeout=300)
    return SkillResult(True, result.text[:800], {"raw": result.text})


def _qa_capture_and_score(args: dict) -> SkillResult:
    panel_name = args.get("panel_name", "GamePanel")

    build_result = _unity_build_panel({"panel_name": panel_name})
    if not build_result.success:
        return build_result

    capture_result = _qa_capture({"panel_name": panel_name})
    if not capture_result.success:
        return capture_result

    eval_result = _qa_evaluate({
        "screenshot_path": capture_result.data["path"],
        "panel_name": panel_name,
    })
    return eval_result


# ---------------------------------------------------------------------------
# Feishu Report Skill
# ---------------------------------------------------------------------------

def _feishu_send_text(args: dict) -> SkillResult:
    channel = args.get("channel", "Studio")
    message = args.get("message", "")
    try:
        sys.path.insert(0, str(COMFYUI_DIR))
        from autoresearch.feishu_notify import send
        send(channel, message)
        return SkillResult(True, f"Sent to {channel}")
    except Exception as e:
        return SkillResult(False, f"Feishu send failed: {e}")


def _feishu_send_image(args: dict) -> SkillResult:
    channel = args.get("channel", "Studio")
    title = args.get("title", "")
    image_path = args.get("image_path", "")
    if not image_path or not Path(image_path).exists():
        return SkillResult(False, f"Image not found: {image_path}")
    try:
        sys.path.insert(0, str(COMFYUI_DIR))
        from autoresearch.feishu_notify import send_image
        send_image(channel, title, image_path)
        return SkillResult(True, f"Image sent to {channel}")
    except Exception as e:
        return SkillResult(False, f"Feishu image send failed: {e}")


def _feishu_send_grid(args: dict) -> SkillResult:
    from PIL import Image, ImageDraw

    channel = args.get("channel", "Studio")
    title = args.get("title", "Report")
    screenshots = args.get("screenshots", {})

    if not screenshots:
        return SkillResult(False, "No screenshots to send")

    items = list(screenshots.items())[:8]
    cols = min(len(items), 2)
    rows = (len(items) + cols - 1) // cols
    tw, th = 640, 360
    grid = Image.new("RGB", (cols * tw, rows * th + 40), (30, 30, 30))
    draw = ImageDraw.Draw(grid)
    draw.text((10, 8), title, fill="white")

    for i, (name, path) in enumerate(items):
        try:
            img = Image.open(path).resize((tw, th), Image.LANCZOS)
        except Exception:
            img = Image.new("RGB", (tw, th), (60, 60, 60))
        x = (i % cols) * tw
        y = (i // cols) * th + 40
        grid.paste(img, (x, y))
        draw.text((x + 5, y + 3), name, fill="yellow")

    grid_path = COMFYUI_DIR / "runs" / f"report_{int(time.time())}.png"
    grid.save(grid_path)

    return _feishu_send_image({
        "channel": channel,
        "title": title,
        "image_path": str(grid_path),
    })


# ---------------------------------------------------------------------------
# Global Registry — register all built-in skills
# ---------------------------------------------------------------------------

registry = SkillRegistry()

# Unity Control
registry.register("unity_control.pre_check",
                   lambda args: SkillResult(*_unity_pre_check()),
                   description="Check if Unity Editor MCP is reachable")
registry.register("unity_control.ensure_running",
                   _unity_ensure_running, description="Start Unity if not running")
registry.register("unity_control.refresh",
                   _unity_refresh, pre_check=_unity_pre_check,
                   description="Refresh Unity assets")
registry.register("unity_control.build_panel",
                   _unity_build_panel, pre_check=_unity_pre_check,
                   description="Build a UI panel in Unity", timeout=60)

# Screenshot QA
registry.register("screenshot_qa.capture",
                   _qa_capture, pre_check=_qa_pre_check,
                   description="Capture a panel screenshot", timeout=90)
registry.register("screenshot_qa.evaluate",
                   _qa_evaluate, description="Evaluate a screenshot with QA checklist")
registry.register("screenshot_qa.capture_and_score",
                   _qa_capture_and_score, pre_check=_qa_pre_check,
                   description="Build + capture + score a panel", timeout=300)

# Feishu Report
registry.register("feishu_report.send_text",
                   _feishu_send_text, description="Send text message via Feishu")
registry.register("feishu_report.send_image",
                   _feishu_send_image, description="Send image via Feishu")
registry.register("feishu_report.send_grid",
                   _feishu_send_grid, description="Build screenshot grid and send via Feishu")
