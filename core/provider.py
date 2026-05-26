"""Multi-provider LLM execution with config-driven routing.

Providers:
    sdk       — Claude API via Anthropic SDK (plan/replan/classify)
    cli       — Claude Code CLI via subprocess (step execution, QA)
    deepseek  — DeepSeek via OpenAI-compatible API (T2 tasks)

Routing:
    Pipeline phases (classify/plan/execute/replan/qa) use config.yaml phases.
    Task YAML `provider:` field overrides tier_routing for dispatch-level tasks.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger("provider")

STUDIO_DIR = Path(__file__).parent.parent
GOPOO_CLIENT = Path(os.path.expanduser("~/Projects/go-poo-client"))

# Compat aliases used by tool_runner
DEEPSEEK_MODEL = "deepseek-v4-pro"
CLAUDE_SONNET = "claude-sonnet-4-6-20250514"
CLAUDE_OPUS = "claude-opus-4-7-20250415"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_config: Optional[dict] = None


def _load_config() -> dict:
    global _config
    if _config is not None:
        return _config
    config_path = STUDIO_DIR / "config.yaml"
    if config_path.exists():
        _config = yaml.safe_load(config_path.read_text())
    else:
        logger.warning("config.yaml not found, using defaults")
        _config = {}
    return _config


def get_phase_config(phase: str) -> dict:
    """Get provider/model/max_tokens for a pipeline phase."""
    cfg = _load_config()
    phases = cfg.get("phases", {})
    return phases.get(phase, {"provider": "cli", "max_tokens": 4096})


def get_model(provider: str, model_key: str) -> str:
    """Resolve model key (opus/sonnet/haiku) to full model ID."""
    cfg = _load_config()
    providers = cfg.get("providers", {})
    if provider == "sdk":
        models = providers.get("sdk", {}).get("models", {})
        return models.get(model_key, model_key)
    if provider == "deepseek":
        return providers.get("deepseek", {}).get("model", "deepseek-v4-pro")
    return model_key


def get_pricing() -> dict:
    cfg = _load_config()
    return cfg.get("pricing", {})


# ---------------------------------------------------------------------------
# Provider result
# ---------------------------------------------------------------------------

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
# Tier routing (dispatch-level, outside planner pipeline)
# ---------------------------------------------------------------------------

def _build_tier_routing() -> dict:
    cfg = _load_config()
    raw = cfg.get("tier_routing", {})
    result = {}
    for key, provider in raw.items():
        parts = key.split(".")
        if len(parts) == 2:
            result[(parts[0], parts[1])] = provider
    return result


def get_provider(task: Optional[dict] = None) -> str:
    if task is None:
        return "cli"
    explicit = task.get("provider")
    if explicit:
        return explicit
    routing = _build_tier_routing()
    return routing.get((task.get("agent", ""), task.get("action", "")), "cli")


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

def _calc_cost(pricing_key: str, input_tokens: int, output_tokens: int) -> float:
    pricing = get_pricing()
    p = pricing.get(pricing_key, pricing.get("deepseek", {"input": 0.435, "output": 0.87}))
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

def _get_anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _get_deepseek_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "")


# ---------------------------------------------------------------------------
# SDK provider (Anthropic API)
# ---------------------------------------------------------------------------

def run_sdk(prompt: str, system: str = "",
            model_key: str = "sonnet",
            max_tokens: Optional[int] = None,
            phase: Optional[str] = None) -> ProviderResult:
    """Call Claude API via Anthropic SDK.

    Args:
        model_key: one of opus/sonnet/haiku, resolved via config
        max_tokens: override; if None, uses phase config or 4096
        phase: pipeline phase name for config lookup
    """
    api_key = _get_anthropic_key()
    if not api_key:
        return ProviderResult(text="ERROR: ANTHROPIC_API_KEY not set",
                              provider="sdk", model=model_key)

    try:
        import anthropic
    except ImportError:
        return ProviderResult(text="ERROR: pip install anthropic",
                              provider="sdk", model=model_key)

    model_id = get_model("sdk", model_key)

    if max_tokens is None:
        if phase:
            max_tokens = get_phase_config(phase).get("max_tokens", 4096)
        else:
            max_tokens = 4096

    cfg = _load_config()
    base_url = cfg.get("providers", {}).get("sdk", {}).get("base_url")
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**client_kwargs)

    t0 = time.time()
    try:
        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
    except Exception as e:
        return ProviderResult(text=f"ERROR: SDK call failed: {e}",
                              provider="sdk", model=model_id)

    latency = int((time.time() - t0) * 1000)
    text = resp.content[0].text if resp.content else ""
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens

    pricing_key = model_key
    if model_key not in get_pricing():
        pricing_key = "sonnet"

    return ProviderResult(
        text=text,
        provider="sdk",
        model=model_id,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=_calc_cost(pricing_key, in_tok, out_tok),
        latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# CLI provider (claude -p, Max subscription)
# ---------------------------------------------------------------------------

def _get_cli_flags() -> list:
    cfg = _load_config()
    env_flags = os.environ.get("CLAUDE_CLI_FLAGS", "")
    if env_flags:
        return env_flags.split()
    return cfg.get("providers", {}).get("cli", {}).get(
        "flags", ["claude", "--dangerously-skip-permissions", "-p"])


def _get_cli_timeout() -> int:
    cfg = _load_config()
    return cfg.get("providers", {}).get("cli", {}).get("timeout", 600)


def run_cli(prompt: str, cwd: Optional[str] = None,
            timeout: Optional[int] = None,
            task_id: Optional[str] = None,
            step_id: Optional[str] = None) -> ProviderResult:
    cwd = cwd or str(GOPOO_CLIENT)
    timeout = timeout or _get_cli_timeout()
    cli_flags = _get_cli_flags()

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cli_flags + [prompt, "--output-format", "stream-json", "--verbose"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=cwd)
    except FileNotFoundError:
        return ProviderResult(text="ERROR: claude CLI not found",
                              provider="cli", model="opus")

    result_text = ""
    in_tok, out_tok = 0, 0
    cost_usd = 0.0
    model = "opus"
    tool_calls = []

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            ev_type = ev.get("type", "")

            if ev_type == "assistant":
                msg = ev.get("message", {})
                for block in msg.get("content", []):
                    if block.get("type") == "tool_use":
                        tool_info = {"tool": block.get("name", ""), "input": _summarize_tool_input(block.get("input", {}))}
                        tool_calls.append(tool_info)
                        _emit_cli_event("tool_call", task_id, step_id, tool_info)
                    elif block.get("type") == "text" and block.get("text"):
                        _emit_cli_event("assistant_text", task_id, step_id, {"text": block["text"][:300]})

            elif ev_type == "result":
                result_text = ev.get("result", "")
                usage = ev.get("usage", {})
                in_tok = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                cost_usd = ev.get("total_cost_usd", 0.0)

        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return ProviderResult(text="ERROR: CLI timeout",
                              provider="cli", model=model)

    latency = int((time.time() - t0) * 1000)

    if proc.returncode != 0 and not result_text:
        stderr = proc.stderr.read() if proc.stderr else ""
        return ProviderResult(
            text=f"ERROR: claude exit {proc.returncode}: {stderr[:300]}",
            provider="cli", model=model, latency_ms=latency)

    return ProviderResult(
        text=result_text,
        provider="cli",
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost_usd,
        latency_ms=latency,
    )


def _summarize_tool_input(inp: Any) -> str:
    if isinstance(inp, dict):
        if "command" in inp:
            return inp["command"][:150]
        if "file_path" in inp:
            return inp["file_path"]
        if "query" in inp:
            return inp["query"][:150]
    return str(inp)[:100]


def _emit_cli_event(event_type: str, task_id: Optional[str],
                    step_id: Optional[str], data: dict):
    try:
        from core.db import emit_event
        emit_event(f"cli_{event_type}", task_id=task_id, step_id=step_id,
                   phase="execute", data=data)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# DeepSeek provider (OpenAI-compatible API)
# ---------------------------------------------------------------------------

@dataclass
class APIResponse:
    message: Any
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    provider: str = ""
    model: str = ""


def call_openai_api(messages: list, provider_name: str = "deepseek",
                    model: Optional[str] = None, tools: Optional[list] = None,
                    temperature: float = 0.3, max_tokens: int = 8192) -> APIResponse:
    api_key = _get_deepseek_key()
    cfg = _load_config()
    ds_cfg = cfg.get("providers", {}).get("deepseek", {})
    base_url = ds_cfg.get("base_url", "https://api.deepseek.com")
    if model is None:
        model = ds_cfg.get("model", "deepseek-v4-pro")

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


def run_deepseek(prompt: str, system: str = "", model: Optional[str] = None,
                 temperature: float = 0.3, max_tokens: int = 8192) -> ProviderResult:
    cfg = _load_config()
    if model is None:
        model = cfg.get("providers", {}).get("deepseek", {}).get("model", "deepseek-v4-pro")

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
# Phase-based routing (used by planner pipeline)
# ---------------------------------------------------------------------------

def run_phase(phase: str, prompt: str, system: str = "",
              cwd: Optional[str] = None,
              task_id: Optional[str] = None,
              step_id: Optional[str] = None) -> ProviderResult:
    """Route a prompt to the correct provider based on pipeline phase config."""
    pc = get_phase_config(phase)
    provider = pc.get("provider", "cli")
    model_key = pc.get("model", "sonnet")
    max_tokens = pc.get("max_tokens", 4096)

    if provider == "sdk":
        result = run_sdk(prompt, system=system, model_key=model_key,
                         max_tokens=max_tokens, phase=phase)
    elif provider == "cli":
        result = run_cli(prompt, cwd=cwd, task_id=task_id, step_id=step_id)
    elif provider == "deepseek":
        result = run_deepseek(prompt, system=system, max_tokens=max_tokens)
    else:
        result = ProviderResult(text=f"ERROR: unknown provider '{provider}'",
                                provider=provider, model="")

    try:
        from core.db import emit_event
        emit_event("provider_call", phase=phase, data={
            "provider": result.provider, "model": result.model,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd, "latency_ms": result.latency_ms,
        })
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Unified entry point with fallback escalation (dispatch-level)
# ---------------------------------------------------------------------------

def run_prompt(prompt: str, task: dict, system: str = "",
               cwd: Optional[str] = None,
               max_self_loops: int = 2,
               evaluator: Any = None) -> ProviderResult:
    provider = get_provider(task)

    if provider == "cli":
        return run_cli(prompt, cwd=cwd)

    if provider == "sdk":
        model_key = "sonnet"
        if "opus" in task.get("model", ""):
            model_key = "opus"
        return run_sdk(prompt, system=system, model_key=model_key)

    # DeepSeek with fallback escalation
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

    logger.warning("Escalating %s to CLI after %d DeepSeek attempts",
                   task.get("id", "?"), max_self_loops)
    cli_result = run_cli(prompt, cwd=cwd)
    cli_result.escalated = True
    cli_result.loop_count = max_self_loops

    if last_result:
        _log_escalation(task, last_result, cli_result)

    return cli_result


# ---------------------------------------------------------------------------
# Escalation logging
# ---------------------------------------------------------------------------

_ESCALATION_LOG = STUDIO_DIR / "base" / "studio" / "wiki" / "pages" / "provider-escalation-log.md"


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
"""

    if not _ESCALATION_LOG.exists():
        _ESCALATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        header = """---
title: Provider Escalation Log
created: 2026-05-25
type: summary
tags: [provider, escalation, learning]
---

# Provider Escalation Log
"""
        _ESCALATION_LOG.write_text(header)

    with open(_ESCALATION_LOG, "a") as f:
        f.write(entry)

    logger.info("Escalation logged: %s", task_id)
