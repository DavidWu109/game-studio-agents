"""Provider-agnostic tool execution loop.

Gives any LLM (DeepSeek, Claude SDK, future providers) the ability to
read files, write files, edit files, and run shell commands — with
safety enforcement from core/safety.py.

Pattern follows Codex and Claude Code CLI:
    send messages + tools → receive tool_calls → execute → append results → re-send

Usage:
    from core.tool_runner import run_with_tools
    result = run_with_tools(prompt, agent="engineering", cwd="/path/to/project")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from core.provider import (
    APIResponse, ProviderResult, call_openai_api,
    DEEPSEEK_MODEL, _calc_cost,
)
from core.safety import check_write_allowed, check_command_allowed

logger = logging.getLogger("tool_runner")

MAX_TOOL_ROUNDS = 15
BASH_TIMEOUT = 30
MAX_FILE_READ_CHARS = 50_000
MAX_OUTPUT_CHARS = 10_000


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function calling format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the filesystem. Returns file contents with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (0-based). Optional.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of lines to read. Optional, defaults to 200.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace an exact string in a file with a new string. The old_string must appear exactly once in the file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact text to find and replace (must be unique in the file)",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace it with",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command and return its output (stdout + stderr).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                },
                "required": ["command"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------

def _get_path_arg(args: dict) -> str:
    """Extract path from args, handling variant field names from different LLMs."""
    return args.get("path") or args.get("filePath") or args.get("file_path") or args.get("file", "")


def _resolve_path(path: str, cwd: str) -> Path:
    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def _exec_read_file(args: dict, cwd: str, agent: str) -> str:
    path = _resolve_path(_get_path_arg(args), cwd)
    if not path.exists():
        return f"ERROR: file not found: {path}"
    if not path.is_file():
        return f"ERROR: not a file: {path}"
    try:
        text = path.read_text(errors="replace")
    except Exception as e:
        return f"ERROR: cannot read {path}: {e}"

    lines = text.split("\n")
    offset = args.get("offset", 0)
    limit = args.get("limit", 200)
    selected = lines[offset:offset + limit]
    numbered = [f"{i + offset + 1}\t{line}" for i, line in enumerate(selected)]
    result = "\n".join(numbered)
    if len(result) > MAX_FILE_READ_CHARS:
        result = result[:MAX_FILE_READ_CHARS] + "\n... (truncated)"
    return result


def _exec_write_file(args: dict, cwd: str, agent: str) -> str:
    path = _resolve_path(_get_path_arg(args), cwd)
    if not check_write_allowed(agent, str(path)):
        return f"SAFETY_BLOCK: agent '{agent}' is not allowed to write to {path}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"])
        return f"OK: wrote {len(args['content'])} chars to {path}"
    except Exception as e:
        return f"ERROR: write failed: {e}"


def _exec_edit_file(args: dict, cwd: str, agent: str) -> str:
    path = _resolve_path(_get_path_arg(args), cwd)
    if not check_write_allowed(agent, str(path)):
        return f"SAFETY_BLOCK: agent '{agent}' is not allowed to write to {path}"
    if not path.exists():
        return f"ERROR: file not found: {path}"

    try:
        text = path.read_text()
    except Exception as e:
        return f"ERROR: cannot read {path}: {e}"

    old = args["old_string"]
    new = args["new_string"]
    count = text.count(old)
    if count == 0:
        return f"ERROR: old_string not found in {path}"
    if count > 1:
        return f"ERROR: old_string appears {count} times in {path}, must be unique"

    path.write_text(text.replace(old, new, 1))
    return f"OK: replaced {len(old)} chars with {len(new)} chars in {path}"


def _exec_bash(args: dict, cwd: str, agent: str) -> str:
    command = args["command"]
    allowed, reason = check_command_allowed(agent, command)
    if not allowed:
        return f"SAFETY_BLOCK: {reason}"

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=BASH_TIMEOUT, cwd=cwd,
        )
        output = result.stdout + result.stderr
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
        exit_info = f"[exit {result.returncode}]" if result.returncode != 0 else ""
        return f"{output}{exit_info}".strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {BASH_TIMEOUT}s"
    except Exception as e:
        return f"ERROR: {e}"


TOOL_EXECUTORS = {
    "read_file": _exec_read_file,
    "write_file": _exec_write_file,
    "edit_file": _exec_edit_file,
    "bash": _exec_bash,
}


# ---------------------------------------------------------------------------
# Tool execution loop
# ---------------------------------------------------------------------------

def run_with_tools(prompt: str, agent: str, cwd: str,
                   system: str = "",
                   provider_name: str = "deepseek",
                   model: str = DEEPSEEK_MODEL,
                   max_rounds: int = MAX_TOOL_ROUNDS,
                   temperature: float = 0.3,
                   max_tokens: int = 8192) -> ProviderResult:
    """Execute a prompt with tool use in a multi-turn loop.

    1. Send prompt + tool schemas to API
    2. If response contains tool_calls → execute each → append results → re-send
    3. If response is plain text → return it
    4. Repeat until no more tool_calls or max_rounds reached
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    total_in = 0
    total_out = 0
    total_latency = 0
    final_text = ""

    for round_n in range(max_rounds):
        try:
            resp = call_openai_api(
                messages, provider_name=provider_name, model=model,
                tools=TOOL_SCHEMAS, temperature=temperature,
                max_tokens=max_tokens,
            )
        except RuntimeError as e:
            return ProviderResult(text=f"ERROR: {e}", provider=provider_name,
                                 model=model, loop_count=round_n)

        total_in += resp.input_tokens
        total_out += resp.output_tokens
        total_latency += resp.latency_ms

        msg = resp.message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            final_text = msg.content or ""
            break

        # Append assistant message with tool calls to history
        messages.append(_msg_to_dict(msg))

        # Execute each tool call and append results
        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            executor = TOOL_EXECUTORS.get(fn_name)
            if executor:
                logger.info("Round %d: %s(%s)", round_n, fn_name,
                            _summarize_args(fn_args))
                tool_output = executor(fn_args, cwd, agent)
            else:
                tool_output = f"ERROR: unknown tool '{fn_name}'"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_output,
            })
    else:
        final_text = f"ERROR: max tool rounds ({max_rounds}) reached"

    pricing_key = provider_name if provider_name in ("deepseek",) else "sonnet"

    return ProviderResult(
        text=final_text,
        provider=provider_name,
        model=model,
        input_tokens=total_in,
        output_tokens=total_out,
        cost_usd=_calc_cost(pricing_key, total_in, total_out),
        latency_ms=total_latency,
        loop_count=round_n + 1,
    )


def _msg_to_dict(msg: Any) -> dict:
    """Convert an OpenAI ChatCompletionMessage to a dict for the messages list."""
    d: dict[str, Any] = {"role": "assistant"}
    if msg.content:
        d["content"] = msg.content
    # DeepSeek V4 Pro thinking mode: must pass reasoning_content back
    reasoning = getattr(msg, "reasoning_content", None)
    if reasoning:
        d["reasoning_content"] = reasoning
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def _summarize_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)
