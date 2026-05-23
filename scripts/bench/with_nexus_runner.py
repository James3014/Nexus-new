from __future__ import annotations

import hashlib
from contextlib import nullcontext
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ContextManager


@dataclass(frozen=True)
class WithNexusCodexPrompt:
    prompt: str
    reset_boundary: str
    reset_boundary_hash: str
    nexus_control_chars: int


@dataclass(frozen=True)
class WithNexusCodexAttemptResult:
    status: str
    err: str
    out: Any
    raw: str
    raw_tail: str
    patch: str
    patch_changed: bool
    pytest_stdout_tail: str
    pytest_stderr_tail: str
    self_heal_used: bool
    self_heal_status: str
    failure_reasons: list[str]


def build_with_nexus_codex_prompt(
    *,
    task: Any,
    task_with_context: str,
    route_prompt: str,
    codeintel_prompt: str,
    profile_prompt: str,
    executor_flags_prompt: str,
    hidden_guidance: str,
    source: str,
    visible_tests: str,
) -> WithNexusCodexPrompt:
    reset_boundary = (
        f"NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id={task.id} trial_index={task.trial_index} "
        "Treat this as an isolated task. Do not use facts, filenames, code, tests, or conclusions from any previous benchmark turn."
    )
    prompt = (
        "You are Codex wearing Nexus. Return ONLY valid JSON with keys status and patch. No markdown. "
        "Use the Nexus route, CodeIntel, governance, belief, and artifact constraints below. "
        "The patch value must be the full updated target file content.\n\n"
        f"{reset_boundary}\n\n"
        f"[TASK]\n{task_with_context}\n\n"
        f"[NEXUS ROUTE SUMMARY]\n{route_prompt}\n\n"
        f"[NEXUS CODEINTEL SUMMARY]\n{codeintel_prompt}\n\n"
        f"[NEXUS EXECUTION PROFILE]\n{profile_prompt}\n\n"
        f"[NEXUS EXECUTOR FLAGS]\n{executor_flags_prompt}\n\n"
        f"[NEXUS HIDDEN-VERIFIER GUIDANCE]\n{hidden_guidance}\n\n"
        f"[CURRENT SOURCE]\n{source}\n\n"
        f"[VISIBLE TESTS]\n{visible_tests}\n\n"
        "Return the full updated file content in the patch field."
    )
    return WithNexusCodexPrompt(
        prompt=prompt,
        reset_boundary=reset_boundary,
        reset_boundary_hash=hashlib.sha256(reset_boundary.encode("utf-8")).hexdigest(),
        nexus_control_chars=(
            len(route_prompt)
            + len(codeintel_prompt)
            + len(profile_prompt)
            + len(executor_flags_prompt)
            + len(hidden_guidance)
        ),
    )


def _tail_text(value: Any, *, max_chars: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text[-max_chars:]


def _response_patch(out: Any, raw: str) -> str:
    if isinstance(out, dict):
        return str(out.get("patch") or raw or "")
    return str(raw or "")


def _returncode(result: Any) -> int:
    return int(getattr(result, "returncode", 1))


def run_with_nexus_codex_attempts(
    *,
    prompt: str,
    original: str,
    ask_patch: Callable[..., tuple[Any, str]],
    apply_patch: Callable[[str], None],
    verify_patch: Callable[[], Any],
    remaining_timeout: Callable[[], int],
    retry_prompt_factory: Callable[[str, str, str], str] | None = None,
    socket_guard: Callable[[], ContextManager[Any]] | None = None,
) -> WithNexusCodexAttemptResult:
    guard = socket_guard or nullcontext
    status = "FAILED"
    err = ""
    failure_reasons: list[str] = []
    pytest_stdout_tail = ""
    pytest_stderr_tail = ""
    self_heal_used = False
    self_heal_status = "not_needed"

    with guard():
        out, raw = ask_patch(prompt=prompt, timeout_sec=remaining_timeout())
    raw_tail = _tail_text(raw, max_chars=1000)
    patch = _response_patch(out, raw)
    patch_changed = bool(patch and patch != original)
    if not patch_changed:
        return WithNexusCodexAttemptResult(
            status="FAILED",
            err="no_mutation_generated",
            out=out,
            raw=raw,
            raw_tail=raw_tail,
            patch=patch,
            patch_changed=False,
            pytest_stdout_tail="",
            pytest_stderr_tail="",
            self_heal_used=False,
            self_heal_status="not_needed",
            failure_reasons=["no_mutation_generated"],
        )

    apply_patch(patch)
    res = verify_patch()
    pytest_stdout_tail = _tail_text(getattr(res, "stdout", ""), max_chars=1000)
    pytest_stderr_tail = _tail_text(getattr(res, "stderr", ""), max_chars=1000)
    status = "SUCCESS" if _returncode(res) == 0 else "FAILED"
    if status == "SUCCESS":
        return WithNexusCodexAttemptResult(
            status=status,
            err="",
            out=out,
            raw=raw,
            raw_tail=raw_tail,
            patch=patch,
            patch_changed=True,
            pytest_stdout_tail=pytest_stdout_tail,
            pytest_stderr_tail=pytest_stderr_tail,
            self_heal_used=False,
            self_heal_status="not_needed",
            failure_reasons=[],
        )

    err = "pytest_failed"
    failure_reasons.append("pytest_failed")
    if retry_prompt_factory is None:
        return WithNexusCodexAttemptResult(
            status=status,
            err=err,
            out=out,
            raw=raw,
            raw_tail=raw_tail,
            patch=patch,
            patch_changed=True,
            pytest_stdout_tail=pytest_stdout_tail,
            pytest_stderr_tail=pytest_stderr_tail,
            self_heal_used=False,
            self_heal_status="not_needed",
            failure_reasons=failure_reasons,
        )

    self_heal_used = True
    self_heal_status = "retrying"
    retry_prompt = retry_prompt_factory(patch, pytest_stdout_tail, pytest_stderr_tail)
    with guard():
        retry_out, retry_raw = ask_patch(prompt=retry_prompt, timeout_sec=remaining_timeout())
    retry_patch = _response_patch(retry_out, retry_raw)
    if retry_patch and retry_patch != original and retry_patch != patch:
        apply_patch(retry_patch)
        retry_res = verify_patch()
        pytest_stdout_tail = _tail_text(getattr(retry_res, "stdout", ""), max_chars=1000)
        pytest_stderr_tail = _tail_text(getattr(retry_res, "stderr", ""), max_chars=1000)
        if _returncode(retry_res) == 0:
            patch = retry_patch
            patch_changed = True
            status = "SUCCESS"
            err = ""
            self_heal_status = "recovered"
        else:
            self_heal_status = "retry_failed"
    else:
        self_heal_status = "retry_noop"

    return WithNexusCodexAttemptResult(
        status=status,
        err=err,
        out=out,
        raw=raw,
        raw_tail=raw_tail,
        patch=patch,
        patch_changed=patch_changed,
        pytest_stdout_tail=pytest_stdout_tail,
        pytest_stderr_tail=pytest_stderr_tail,
        self_heal_used=self_heal_used,
        self_heal_status=self_heal_status,
        failure_reasons=failure_reasons,
    )
