from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_GEMINI_BIN = "/Users/jameschen/.npm-global/bin/gemini"
DEFAULT_NODE_CANDIDATES = (
    "/opt/homebrew/bin/node",
    "/usr/local/bin/node",
    "/usr/bin/node",
)
DEFAULT_GEMINI_CANDIDATES = (
    DEFAULT_GEMINI_BIN,
    "/opt/homebrew/bin/gemini",
    "/usr/local/bin/gemini",
)
DEFAULT_PATH_PREFIX = "/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


@dataclass(frozen=True)
class GeminiCliInvocation:
    command: list[str]
    command_with_node: list[str] | None
    env: dict[str, str]
    cwd: str
    prompt_stdin: str | None
    prompt_chars: int
    payload_chars: int
    transport: str


def build_gemini_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    env["HOME"] = env.get("HOME") or "/Users/jameschen"
    env["PATH"] = f"{DEFAULT_PATH_PREFIX}:{env.get('PATH', '')}"
    env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"
    return env


def resolve_binary(
    *,
    env: dict[str, str],
    env_key: str,
    candidates: tuple[str, ...],
    binary_name: str,
) -> str | None:
    env_override = env.get(env_key)
    if env_override and Path(env_override).exists():
        return env_override
    found = shutil.which(binary_name, path=env.get("PATH", ""))
    if found:
        return found
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def build_gemini_cli_invocation(
    *,
    prompt: str,
    payload: str = "",
    model_name: str,
    gemini_entry: str | None = None,
    node_bin: str | None = None,
    env: dict[str, str] | None = None,
    cwd: str = "/tmp",
    approval_mode: str | None = None,
    transport: str | None = None,
) -> GeminiCliInvocation:
    cli_env = build_gemini_env(env)
    approval = approval_mode or cli_env.get("NEXUS_GATEWAY_APPROVAL_MODE") or "plan"
    prompt_transport = (transport or cli_env.get("NEXUS_GATEWAY_PROMPT_TRANSPORT") or "stdin").strip().lower()
    if prompt_transport not in {"stdin", "inline"}:
        prompt_transport = "stdin"

    prompt_arg = prompt
    stdin_payload: str | None = None
    if payload:
        if prompt_transport == "inline":
            prompt_arg = f"{prompt}\n\n{payload}"
        else:
            stdin_payload = payload

    gemini_bin = gemini_entry or resolve_binary(
        env=cli_env,
        env_key="NEXUS_GEMINI_BIN",
        candidates=DEFAULT_GEMINI_CANDIDATES,
        binary_name="gemini",
    )
    node = node_bin
    if node is None:
        node = resolve_binary(
            env=cli_env,
            env_key="NEXUS_NODE_BIN",
            candidates=DEFAULT_NODE_CANDIDATES,
            binary_name="node",
        )

    command = [
        gemini_bin or DEFAULT_GEMINI_BIN,
        "--skip-trust",
        "--approval-mode",
        approval,
        "-m",
        model_name,
        "-p",
        prompt_arg,
        "--output-format",
        "json",
    ]
    command_with_node = None
    if node and gemini_bin:
        command_with_node = [node, *command]

    return GeminiCliInvocation(
        command=command,
        command_with_node=command_with_node,
        env=cli_env,
        cwd=cwd,
        prompt_stdin=stdin_payload,
        prompt_chars=len(prompt),
        payload_chars=len(payload),
        transport=prompt_transport,
    )


def extract_token_info(payload: dict[str, Any]) -> dict[str, Any]:
    total = 0
    stats_root = payload.get("stats")
    stats = stats_root.get("models", {}) if isinstance(stats_root, dict) else {}
    stats_present = isinstance(stats_root, dict)
    stats_tokens = 0
    if isinstance(stats, dict):
        for model_stats in stats.values():
            if isinstance(model_stats, dict):
                try:
                    stats_tokens += int((model_stats.get("tokens") or {}).get("total") or 0)
                except (TypeError, ValueError):
                    continue
    total += stats_tokens

    usage = payload.get("usageMetadata") or payload.get("usage_metadata") or payload.get("usage")
    usage_present = isinstance(usage, dict)
    usage_tokens = 0
    if isinstance(usage, dict):
        for key in ("totalTokenCount", "total_tokens", "totalTokens"):
            try:
                value = int(usage.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                usage_tokens = value
                break
    total += usage_tokens

    source = "missing"
    if stats_tokens > 0:
        source = "stats"
    elif usage_tokens > 0:
        source = "usage_metadata"
    return {
        "total_tokens": total,
        "gateway_stats_present": stats_present,
        "gateway_usage_metadata_present": usage_present,
        "gateway_token_source": source,
    }
