"""Multi-provider LLM execution with fallback escalation.

Providers:
    deepseek  — DeepSeek V4 Pro via OpenAI-compatible API (default for T2 tasks)
    cli       — Claude Code CLI via subprocess (Max subscription, for T1 tasks)
    sdk       — Claude API via Anthropic SDK (when SDK credits available, post 6/15)

Routing:
    Task YAML can specify `provider: deepseek | cli | sdk`
    If omitted, uses TIER_ROUTING based on (agent, action)

Fallback:
    DeepSeek first → loop > max_self_loops → escalate to CLI Opus → still fails → report human
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
from typing import Any, Optional

logger = logging.getLogger("provider")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

GOPOO_CLIENT = Path(os.path.expanduser("~/Projects/go-poo-client"))


# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"

CLAUDE_SONNET = "claude-sonnet-4-6-20250514"
CLAUDE_OPUS = "claude-opus-4-7-20250415"

# CLI flags — mirrors dispatch.py line 181; override via CLAUDE_CLI_FLAGS env var
_default_cli_flags = ["claude", "--dangerously-skip-permissions", "-p"]
_env_flags = os.environ.get("CLAUDE_CLI_FLAGS", "")
CLI_FLAGS = _env_flags.split() if _env_flags else _default_cli_flags


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    escalated: bool = False
    loop_count: int = 0


# ---------------------------------------------------------------------------
# Tier routing — which (agent, action) goes to which provider by default
# ---------------------------------------------------------------------------

TIER_ROUTING = {
    # T1: must use Claude Opus (architecture, creative, QA scoring)
    ("qa", "review"): "cli",
    ("creative", "decide"): "cli",
    ("creative", "review"): "cli",
    # T2: default to DeepSeek (code gen, wiki, mockup)
    ("engineering", "code"): "deepseek",
    ("design", "code"): "deepseek",
    ("art", "iterate"): "deepseek",
    ("art", "generate"): "deepseek",
    # Studio report doesn't need LLM routing
    ("studio", "report"): "cli",
}


def get_provider(task: dict) -> str:
    explicit = task.get("provider")
    if explicit:
        return explicit
    return TIER_ROUTING.get((task["agent"], task["action"]), "deepseek")


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

PRICING = {
    "deepseek": {"input": 0.435, "output": 0.87},       # per M tokens
    "sonnet": {"input": 3.0, "output": 15.0},
    "opus": {"input": 5.0, "output": 25.0},
}


def _calc_cost(provider_key: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICING.get(provider_key, PRICING["deepseek"])
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# Generic API call (OpenAI-compatible: DeepSeek, future providers)
# ---------------------------------------------------------------------------

@dataclass
class APIResponse:
    """Raw API response — used by tool_runner for the multi-turn loop."""
    message: Any  # OpenAI ChatCompletionMessage or similar
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider: str = ""
    model: str = ""


def call_openai_api(messages: list, provider_name: str = "deepseek",
                    model: str = DEEPSEEK_MODEL, tools: Optional[list] = None,
                    temperature: float = 0.3, max_tokens: int = 8192) -> APIResponse:
    """Single API call to any OpenAI-compatible endpoint. Returns raw response."""
    api_key = DEEPSEEK_API_KEY
    base_url = DEEPSEEK_BASE_URL
    if not api_key:
        raise RuntimeError(f"{provider_name}: API key not set")

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("pip install openai")

    client = OpenAI(api_key=api_key, base_url=base_url)

    t0 = time.time()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    resp = client.chat.completions.create(**kwargs)

    latency = int((time.time() - t0) * 1000)
    usage = resp.usage
    return APIResponse(
        message=resp.choices[0].message,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
        latency_ms=latency,
        provider=provider_name,
        model=model,
    )


def run_deepseek(prompt: str, system: str = "", model: str = DEEPSEEK_MODEL,
                 temperature: float = 0.3, max_tokens: int = 8192) -> ProviderResult:
    """Simple single-turn call (no tools). For backward compat."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = call_openai_api(messages, "deepseek", model, temperature=temperature,
                               max_tokens=max_tokens)
    except RuntimeError as e:
        return ProviderResult(text=f"ERROR: {e}", provider="deepseek", model=model)

    return ProviderResult(
        text=resp.message.content or "",
        provider="deepseek",
        model=model,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        cost_usd=_calc_cost("deepseek", resp.input_tokens, resp.output_tokens),
        latency_ms=resp.latency_ms,
    )


# ---------------------------------------------------------------------------
# Claude CLI provider (Max subscription)
# ---------------------------------------------------------------------------

def run_cli(prompt: str, cwd: Optional[str] = None,
            timeout: int = 600) -> ProviderResult:
    cwd = cwd or str(GOPOO_CLIENT)
    t0 = time.time()
    try:
        result = subprocess.run(
            CLI_FLAGS + [prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd)
    except subprocess.TimeoutExpired:
        return ProviderResult(text="ERROR: CLI timeout",
                              provider="cli", model="opus")
    except FileNotFoundError:
        return ProviderResult(text="ERROR: claude CLI not found",
                              provider="cli", model="opus")

    latency = int((time.time() - t0) * 1000)

    if result.returncode != 0:
        return ProviderResult(
            text=f"ERROR: claude exit {result.returncode}: {result.stderr[:300]}",
            provider="cli", model="opus", latency_ms=latency)

    try:
        wrapper = json.loads(result.stdout)
        text = wrapper.get("result", "")
        in_tok = wrapper.get("usage", {}).get("input_tokens", 0)
        out_tok = wrapper.get("usage", {}).get("output_tokens", 0)
    except json.JSONDecodeError:
        text = result.stdout[:2000]
        in_tok, out_tok = 0, 0

    return ProviderResult(
        text=text,
        provider="cli",
        model="opus",
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=0.0,  # covered by subscription
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# Claude SDK provider (for when SDK credits are available)
# ---------------------------------------------------------------------------

def run_sdk(prompt: str, system: str = "", model: str = CLAUDE_SONNET,
            max_tokens: int = 4096) -> ProviderResult:
    if not ANTHROPIC_API_KEY:
        return ProviderResult(text="ERROR: ANTHROPIC_API_KEY not set",
                              provider="sdk", model=model)
    try:
        import anthropic
    except ImportError:
        return ProviderResult(text="ERROR: pip install anthropic",
                              provider="sdk", model=model)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    t0 = time.time()
    try:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
    except Exception as e:
        return ProviderResult(text=f"ERROR: Anthropic SDK call failed: {e}",
                              provider="sdk", model=model)

    latency = int((time.time() - t0) * 1000)
    text = resp.content[0].text if resp.content else ""
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens
    pricing_key = "opus" if "opus" in model else "sonnet"

    return ProviderResult(
        text=text,
        provider="sdk",
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=_calc_cost(pricing_key, in_tok, out_tok),
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# Unified entry point with fallback escalation
# ---------------------------------------------------------------------------

def run_prompt(prompt: str, task: dict, system: str = "",
               cwd: Optional[str] = None,
               max_self_loops: int = 2,
               evaluator: Any = None) -> ProviderResult:
    """Run prompt with tier routing and fallback escalation.

    Flow:
        1. Route to provider based on task config or TIER_ROUTING
        2. If provider is 'deepseek', run and evaluate
        3. If evaluation fails after max_self_loops, escalate to CLI
        4. Return result with escalation metadata

    Args:
        prompt: the full prompt text
        task: task dict from dispatch YAML
        system: optional system prompt (DeepSeek/SDK only)
        cwd: working directory for CLI provider
        max_self_loops: how many DeepSeek attempts before escalating
        evaluator: callable(result_text, task) -> (bool, str) for quality gate
    """
    provider = get_provider(task)

    # T1 tasks go straight to CLI
    if provider == "cli":
        return run_cli(prompt, cwd=cwd)

    # SDK path (when available)
    if provider == "sdk":
        return run_sdk(prompt, system=system)

    # T2 path: DeepSeek with fallback
    last_result = None
    for attempt in range(1, max_self_loops + 1):
        result = run_deepseek(prompt, system=system)
        result.loop_count = attempt
        last_result = result

        if result.text.startswith("ERROR:"):
            logger.warning("DeepSeek attempt %d failed: %s", attempt, result.text[:100])
            continue

        if evaluator is None:
            return result

        passed, reason = evaluator(result.text, task)
        if passed:
            return result

        logger.info("DeepSeek attempt %d/%d didn't pass evaluation: %s",
                    attempt, max_self_loops, reason)

    # Escalate to CLI
    logger.warning("Escalating %s to CLI after %d DeepSeek attempts",
                   task.get("id", "?"), max_self_loops)
    cli_result = run_cli(prompt, cwd=cwd)
    cli_result.escalated = True
    cli_result.loop_count = max_self_loops

    # Log escalation for learning
    if last_result:
        _log_escalation(task, last_result, cli_result)

    return cli_result


# ---------------------------------------------------------------------------
# Escalation logging — feeds back into wiki lessons
# ---------------------------------------------------------------------------

_ESCALATION_LOG = Path(os.path.expanduser(
    "~/Projects/game-studio-agents/base/studio/wiki/pages/provider-escalation-log.md"
))


def _log_escalation(task: dict, ds_result: ProviderResult, cli_result: ProviderResult):
    task_id = task.get("id", "unknown")
    agent = task.get("agent", "?")
    action = task.get("action", "?")
    ts = time.strftime("%Y-%m-%d %H:%M")

    entry = f"""
### {ts} | {task_id} ({agent}.{action})
- **DeepSeek**: {ds_result.loop_count} attempts, {ds_result.input_tokens}+{ds_result.output_tokens} tokens, ${ds_result.cost_usd:.4f}
- **CLI fallback**: {cli_result.input_tokens}+{cli_result.output_tokens} tokens
- **DeepSeek output (last 200 chars)**: `{ds_result.text[-200:]}`
- **CLI output (last 200 chars)**: `{cli_result.text[-200:]}`
- **TODO**: analyze what CLI did differently
"""

    if not _ESCALATION_LOG.exists():
        header = """---
title: Provider Escalation Log
created: 2026-05-25
updated: 2026-05-25
type: summary
tags: [provider, escalation, deepseek, claude, learning]
sources: [automated by core/provider.py]
confidence: high
---

# Provider Escalation Log

Records every time DeepSeek failed and CLI had to take over.
Use these to improve prompts and reduce escalation rate.
"""
        _ESCALATION_LOG.write_text(header)

    with open(_ESCALATION_LOG, "a") as f:
        f.write(entry)

    logger.info("Escalation logged: %s", task_id)
