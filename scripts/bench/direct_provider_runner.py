from __future__ import annotations

import hashlib
import os
import time
from contextlib import nullcontext
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ContextManager, Mapping


@dataclass(frozen=True)
class DirectProviderPrompt:
    provider: str
    model_label: str
    prompt_actor: str
    reset_boundary: str
    reset_boundary_hash: str
    prompt_tests: str
    prompt: str
    prompt_sha256: str


@dataclass(frozen=True)
class DirectProviderResponseTelemetry:
    model_calls: int
    patch: str
    gateway_error_category: str
    model_name: str
    model_patch_generated: bool
    total_tokens: int
    token_capture_status: str


@dataclass(frozen=True)
class DirectProviderAttemptResult:
    out: Any
    raw: str
    retry_count: int
    retry_wall_sec: float
    retry_reasons: list[str]
    retry_raw_tails: list[str]


def direct_provider_for_mode(mode: str) -> str:
    if mode in {"codex", "gemini"}:
        return mode
    raise ValueError(f"mode must be a direct provider mode, got {mode!r}")


def direct_provider_model_label(provider: str, env: Mapping[str, str] | None = None) -> str:
    values = env if env is not None else os.environ
    if provider == "codex":
        return values.get("NEXUS_DIRECT_CODEX_MODEL") or values.get("NEXUS_CODEX_MODEL_NAME") or "Codex"
    if provider == "gemini":
        return values.get("NEXUS_DIRECT_GEMINI_MODEL") or values.get("NEXUS_GEMINI_MODEL_NAME") or "Gemini"
    raise ValueError(f"unknown direct provider: {provider!r}")


def build_direct_provider_prompt(
    *,
    task: Any,
    provider: str,
    source: str,
    tests: str,
    env: Mapping[str, str] | None = None,
) -> DirectProviderPrompt:
    provider = direct_provider_for_mode(provider)
    model_label = direct_provider_model_label(provider, env)
    prompt_actor = f"{model_label} running without Nexus orchestration"
    reset_boundary = (
        f"NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id={task.id} trial_index={task.trial_index} "
        "Treat this as an isolated task. Do not use facts, filenames, code, tests, or conclusions from any previous benchmark turn."
    )
    reset_boundary_hash = hashlib.sha256(reset_boundary.encode("utf-8")).hexdigest()
    prompt = (
        f"You are {prompt_actor}. "
        "Return ONLY valid JSON with keys status and patch. No markdown. No tool use. "
        "The patch value must be the full updated target file content.\n"
        f"{reset_boundary}\n\n"
        f"Task: {task.task_desc}\n\n"
        f"[CURRENT SOURCE]\n{source}\n\n"
        f"[CURRENT TESTS]\n{tests}\n\n"
        "Return the full updated file content in the patch field."
    )
    return DirectProviderPrompt(
        provider=provider,
        model_label=model_label,
        prompt_actor=prompt_actor,
        reset_boundary=reset_boundary,
        reset_boundary_hash=reset_boundary_hash,
        prompt_tests=tests,
        prompt=prompt,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )


def _count_fragment(prompt: str, fragment: str) -> int:
    if not fragment:
        return 0
    return len(fragment) if fragment in prompt else 0


def direct_prompt_attribution(
    *,
    prompt: str,
    task_desc: str,
    source: str,
    tests: str,
    patch: str = "",
    nexus_control_chars: int = 0,
    governance_contract_chars: int = 0,
) -> dict[str, int]:
    """Break prompt payload into stable semantic buckets for ROI reporting."""

    task_constraint_chars = _count_fragment(prompt, task_desc)
    source_payload_chars = _count_fragment(prompt, source)
    test_payload_chars = _count_fragment(prompt, tests)
    candidate_payload_chars = len(str(patch or ""))
    known = (
        task_constraint_chars
        + source_payload_chars
        + test_payload_chars
        + candidate_payload_chars
        + nexus_control_chars
        + governance_contract_chars
    )
    system_instruction_chars = max(0, len(prompt) - known)
    return {
        "prompt_system_instruction_chars": system_instruction_chars,
        "prompt_task_constraint_chars": task_constraint_chars,
        "prompt_source_payload_chars": source_payload_chars,
        "prompt_test_payload_chars": test_payload_chars,
        "prompt_candidate_payload_chars": candidate_payload_chars,
        "prompt_nexus_control_chars": max(0, int(nexus_control_chars or 0)),
        "prompt_governance_contract_chars": max(0, int(governance_contract_chars or 0)),
    }


def normalize_direct_provider_response(
    *,
    out: Any,
    raw: str,
    prompt: str,
) -> DirectProviderResponseTelemetry:
    model_calls = 1
    patch = raw
    gateway_error_category = ""
    model_name = ""
    model_patch_generated = False
    total_tokens = 0
    token_capture_status = "unknown"

    if isinstance(out, dict):
        if str(out.get("error_category", "") or "") == "binary_missing":
            model_calls = 0
        patch = str(out.get("patch") or "")
        gateway_error_category = str(out.get("error_category", "") or "")
        if gateway_error_category == "timeout":
            model_calls = 0
        model_name = str(out.get("model_name", "") or "")
        model_patch_generated = bool(out.get("model_patch_generated", False))
        try:
            total_tokens = int(out.get("tokens_used", 0) or 0)
        except (TypeError, ValueError):
            total_tokens = 0
        token_capture_status = str(out.get("token_capture_status", "unknown") or "unknown")

    if total_tokens <= 0 and not gateway_error_category:
        total_tokens = max(1, (len(prompt) + len(str(patch))) // 4)
        token_capture_status = "estimated"

    return DirectProviderResponseTelemetry(
        model_calls=model_calls,
        patch=patch,
        gateway_error_category=gateway_error_category,
        model_name=model_name,
        model_patch_generated=model_patch_generated,
        total_tokens=total_tokens,
        token_capture_status=token_capture_status,
    )


def _tail_text(value: Any, *, max_chars: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text[-max_chars:]


def run_direct_provider_attempts(
    *,
    provider: str,
    prompt: str,
    direct_ask: Callable[..., tuple[Any, str]],
    remaining_timeout: Callable[[], int],
    retry_limit: int,
    retryable_failure: Callable[[dict[str, Any], str], tuple[bool, str]],
    reset_gemini_session: Callable[[str], None] | None = None,
    socket_guard: Callable[[], ContextManager[Any]] | None = None,
    clock: Callable[[], float] | None = None,
) -> DirectProviderAttemptResult:
    guard = socket_guard or nullcontext
    now = clock or time.monotonic

    attempt_start = now()
    with guard():
        out, raw = direct_ask(prompt=prompt, timeout_sec=remaining_timeout())
    attempt_wall_sec = round(now() - attempt_start, 4)

    retry_count = 0
    retry_wall_sec = 0.0
    retry_reasons: list[str] = []
    retry_raw_tails: list[str] = []
    retryable, retry_reason = retryable_failure(out if isinstance(out, dict) else {}, raw)
    while retryable and retry_count < retry_limit:
        retry_count += 1
        retry_wall_sec = round(retry_wall_sec + attempt_wall_sec, 4)
        retry_reasons.append(retry_reason)
        retry_raw_tails.append(_tail_text(raw, max_chars=500))
        if (
            provider == "gemini"
            and retry_reason == "gemini_invalid_session_identifier"
            and isinstance(out, dict)
            and reset_gemini_session is not None
        ):
            reset_gemini_session(str(out.get("gemini_session_id") or ""))

        attempt_start = now()
        with guard():
            out, raw = direct_ask(prompt=prompt, timeout_sec=remaining_timeout())
        attempt_wall_sec = round(now() - attempt_start, 4)
        retryable, retry_reason = retryable_failure(out if isinstance(out, dict) else {}, raw)

    return DirectProviderAttemptResult(
        out=out,
        raw=raw,
        retry_count=retry_count,
        retry_wall_sec=retry_wall_sec,
        retry_reasons=retry_reasons,
        retry_raw_tails=retry_raw_tails,
    )
