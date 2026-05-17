from __future__ import annotations

import os
import hashlib
import json
import shutil
import time
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
INVALID_SESSION_IDENTIFIER_MARKER = "invalid session identifier"


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


def has_invalid_session_identifier(text: str) -> bool:
    return INVALID_SESSION_IDENTIFIER_MARKER in str(text or "").lower()


def _split_forbidden_literals(raw: str) -> list[str]:
    literals: list[str] = []
    for line in str(raw or "").splitlines():
        for part in line.split("::"):
            value = part.strip()
            if value:
                literals.append(value)
    return literals


def record_outbound_prompt_ledger(
    *,
    provider: str,
    prompt: str,
    payload: str = "",
    model_name: str,
    cwd: str,
    env: dict[str, str],
) -> dict[str, Any]:
    ledger_path = str(env.get("NEXUS_OUTBOUND_PROMPT_LEDGER") or "").strip()
    strict = str(env.get("NEXUS_OUTBOUND_PROMPT_STRICT") or "").strip().lower() in {"1", "true", "yes"}
    text = f"{prompt}\n{payload}"
    forbidden_literals = _split_forbidden_literals(str(env.get("NEXUS_OUTBOUND_FORBIDDEN_LITERALS") or ""))
    leaks = [literal for literal in forbidden_literals if literal and literal in text]
    record = {
        "schema": "nexus_outbound_prompt_ledger_v1",
        "provider": provider,
        "model_name": model_name,
        "cwd": cwd,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest() if payload else "",
        "prompt_chars": len(prompt),
        "payload_chars": len(payload),
        "forbidden_literal_count": len(leaks),
        "forbidden_literal_hits": [hashlib.sha256(item.encode("utf-8")).hexdigest() for item in leaks[:10]],
        "strict": strict,
        "created_at_unix": time.time(),
    }
    if ledger_path:
        path = Path(ledger_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    if strict:
        if not ledger_path:
            raise ValueError("outbound_prompt_ledger_required")
        if leaks:
            raise ValueError("outbound_prompt_forbidden_literal")
    return record


def _redact_sanitized_temp_runner_paths(*, text: str, cwd: str, env: dict[str, str]) -> str:
    strict = str(env.get("NEXUS_OUTBOUND_PROMPT_STRICT") or "").strip().lower() in {"1", "true", "yes"}
    if not strict:
        return text
    redacted = text
    literals = sorted(
        _split_forbidden_literals(str(env.get("NEXUS_OUTBOUND_FORBIDDEN_LITERALS") or "")),
        key=len,
        reverse=True,
    )
    for literal in literals:
        if literal.startswith("/private/tmp/nexus-live-clean-runner-"):
            redacted = redacted.replace(literal, "$SANITIZED_RUNNER_ROOT")
        elif literal.startswith("/Users/") or literal.startswith("/private/") or literal.startswith("/tmp/"):
            redacted = redacted.replace(literal, "$SANITIZED_PATH")
    if cwd.startswith("/private/tmp/nexus-live-clean-runner-"):
        redacted = redacted.replace(cwd, "$SANITIZED_RUNNER_ROOT")
    return redacted


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
    approval = approval_mode or cli_env.get("NEXUS_GATEWAY_APPROVAL_MODE") or "auto_edit"
    prompt_transport = (transport or cli_env.get("NEXUS_GATEWAY_PROMPT_TRANSPORT") or "stdin").strip().lower()
    if prompt_transport not in {"stdin", "inline"}:
        prompt_transport = "stdin"

    prompt = _redact_sanitized_temp_runner_paths(text=prompt, cwd=cwd, env=cli_env)
    payload = _redact_sanitized_temp_runner_paths(text=payload, cwd=cwd, env=cli_env)

    prompt_arg = prompt
    stdin_payload: str | None = None
    if payload:
        if prompt_transport == "inline":
            prompt_arg = f"{prompt}\n\n{payload}"
        else:
            stdin_payload = payload

    record_outbound_prompt_ledger(
        provider="gemini",
        prompt=prompt,
        payload=payload,
        model_name=model_name,
        cwd=cwd,
        env=cli_env,
    )

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

    command = [gemini_bin or DEFAULT_GEMINI_BIN]
    skip_trust = str(cli_env.get("NEXUS_GEMINI_SKIP_TRUST", "1")).strip().lower() not in {"0", "false", "no"}
    if skip_trust:
        command.append("--skip-trust")
    command.extend(
        [
            "--approval-mode",
            approval,
            "-m",
            model_name,
            "-p",
            prompt_arg,
            "--output-format",
            "json",
        ]
    )
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
        if usage_tokens <= 0:
            additive_keys = (
                ("promptTokenCount", "candidatesTokenCount"),
                ("prompt_tokens", "completion_tokens"),
                ("input_tokens", "output_tokens"),
                ("inputTokens", "outputTokens"),
            )
            for input_key, output_key in additive_keys:
                try:
                    input_tokens = int(usage.get(input_key) or 0)
                    output_tokens = int(usage.get(output_key) or 0)
                except (TypeError, ValueError):
                    continue
                if input_tokens > 0 or output_tokens > 0:
                    usage_tokens = input_tokens + output_tokens
                    break

    source = "missing"
    if usage_tokens > 0:
        source = "usage_metadata"
        total = usage_tokens
    elif stats_tokens > 0:
        source = "stats"
        total = stats_tokens
    else:
        total = 0
    return {
        "total_tokens": total,
        "gateway_stats_present": stats_present,
        "gateway_usage_metadata_present": usage_present,
        "gateway_token_source": source,
    }
