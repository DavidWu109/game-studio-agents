"""Safety guardrails for automated agent execution.

All agent handlers go through these checks before and after execution.
This is the single enforcement point — handler prompts are advisory,
this module is mandatory.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger("safety")

# ---------------------------------------------------------------------------
# Allowed boundaries per agent
# ---------------------------------------------------------------------------

AGENT_BOUNDARIES = {
    "art": {
        "writable_dirs": [
            "~/Projects/comfyui_workflow/runs/",
            "~/Projects/comfyui_workflow/autoresearch/tasks/",
            "~/Projects/comfyui_workflow/LESSONS.md",
            "~/Projects/go-poo-client/Assets/Art/",
            "~/Projects/go-poo-client/Assets/Resources/Art/",
            "~/Projects/go-poo-client/Assets/Resources/Backgrounds/",
            "~/Projects/gopoo-studio-project/art/",
        ],
        "readable_dirs": ["*"],  # art can read anything
        "forbidden_actions": [
            "git push",
            "git reset --hard",
            "rm -rf",
            "DROP TABLE",
            "curl.*POST.*api",  # no external API calls except ComfyUI
        ],
    },
    "engineering": {
        "writable_dirs": [
            "~/Projects/go-poo-client/Assets/Editor/",
            "~/Projects/go-poo-client/Assets/Scripts/",
            "~/Projects/go-poo-client/Assets/Resources/",
            "~/Projects/gopoo-studio-project/engineering/",
        ],
        "readable_dirs": ["*"],
        "forbidden_actions": [
            "git push",
            "git reset --hard",
            "rm -rf",
            "DELETE FROM",
            "PlayerPrefs.DeleteAll",
        ],
    },
    "qa": {
        "writable_dirs": [
            "~/Projects/comfyui_workflow/runs/",  # screenshots only
            "~/Projects/gopoo-studio-project/qa/",
        ],
        "readable_dirs": ["*"],
        "forbidden_actions": [
            "git push",
            "rm -rf",
            r"Edit\s*\(",  # QA should not edit code
            r"Write\s*\(",
        ],
    },
    "studio": {
        "writable_dirs": [
            "~/Projects/gopoo-studio-project/studio/",
            "~/Projects/game-studio-agents/base/studio/",
        ],
        "readable_dirs": ["*"],
        "forbidden_actions": [
            "git push",
            "rm -rf",
        ],
    },
    "design": {
        "writable_dirs": [
            "~/Projects/gopoo-studio-project/design/",
            "~/Projects/comfyui_workflow/mockups/",
        ],
        "readable_dirs": ["*"],
        "forbidden_actions": [
            "git push",
            "rm -rf",
        ],
    },
    "go-dev": {
        "writable_dirs": [
            "~/Projects/go-poo-server/",
            "~/Projects/gopoo-studio-project/go-dev/",
        ],
        "readable_dirs": ["*"],
        "forbidden_actions": [
            "git push",
            "git reset --hard",
            "rm -rf",
            "DROP TABLE",
        ],
    },
}

# Global forbidden — no agent can do these regardless of boundaries
GLOBAL_FORBIDDEN = [
    r"rm -rf /",
    r"rm -rf ~",
    r"sudo ",
    r"chmod 777",
    r"curl .+\|.+sh",   # pipe-to-shell
    r"eval\s*\(",        # dynamic code execution
    r"> /dev/sd",        # write to block devices
    r"mkfs",
    r"dd if=",
    r"push --force",
    r"reset --hard origin",
    r"npm publish",
    r"pip upload",
    r"docker push",
]


def expand_path(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def check_write_allowed(agent: str, target_path: str) -> bool:
    """Check if agent is allowed to write to this path."""
    target = expand_path(target_path)
    boundaries = AGENT_BOUNDARIES.get(agent)
    if not boundaries:
        logger.warning("Unknown agent '%s' — write denied", agent)
        return False

    for allowed in boundaries["writable_dirs"]:
        allowed_path = expand_path(allowed)
        try:
            target.relative_to(allowed_path)
            return True
        except ValueError:
            continue

    logger.warning("[SAFETY] %s blocked from writing to %s", agent, target)
    return False


def check_command_allowed(agent: str, command: str) -> tuple[bool, str]:
    """Check if a command is safe for this agent to execute.

    Returns (allowed, reason).
    """
    import re

    # Global forbidden checks
    for pattern in GLOBAL_FORBIDDEN:
        if re.search(pattern, command, re.IGNORECASE):
            reason = f"globally forbidden pattern: {pattern}"
            logger.warning("[SAFETY] %s blocked: %s (command: %s)", agent, reason, command[:100])
            return False, reason

    # Agent-specific forbidden
    boundaries = AGENT_BOUNDARIES.get(agent, {})
    for pattern in boundaries.get("forbidden_actions", []):
        if re.search(pattern, command, re.IGNORECASE):
            reason = f"agent '{agent}' forbidden: {pattern}"
            logger.warning("[SAFETY] %s blocked: %s", agent, reason)
            return False, reason

    return True, "ok"


def build_safety_prompt(agent: str) -> str:
    """Generate safety instructions to embed in agent prompts."""
    boundaries = AGENT_BOUNDARIES.get(agent, {})
    writable = boundaries.get("writable_dirs", [])
    forbidden = boundaries.get("forbidden_actions", [])

    lines = [
        "SAFETY RULES (enforced — violations will be blocked):",
        "",
        "You may ONLY write to these directories:",
    ]
    for d in writable:
        lines.append(f"  - {d}")
    lines.append("")
    lines.append("You must NEVER execute:")
    for f in forbidden:
        lines.append(f"  - {f}")
    lines.append("")
    lines.append("These are also globally forbidden:")
    lines.append("  - git push/force, rm -rf, sudo, pipe-to-shell, docker push")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pre/post execution hooks for dispatch
# ---------------------------------------------------------------------------

def pre_execute_check(agent: str, task: dict) -> tuple[bool, str]:
    """Run before executing a task. Returns (ok, reason)."""
    task_input = task.get("input", "")

    # Check for obviously dangerous patterns in task input
    allowed, reason = check_command_allowed(agent, task_input)
    if not allowed:
        return False, f"task input blocked: {reason}"

    return True, "ok"


def post_execute_check(agent: str, task: dict, result: str) -> List[str]:
    """Run after executing a task. Returns list of warnings."""
    warnings = []

    # Check if result mentions unexpected file modifications
    suspicious = ["deleted", "removed", "force push", "reset --hard", "DROP"]
    for s in suspicious:
        if s.lower() in result.lower():
            warnings.append(f"result mentions '{s}' — verify this was intended")

    return warnings
