from __future__ import annotations

from contextlib import contextmanager
import hashlib
import subprocess

from scripts.bench.with_nexus_runner import build_with_nexus_codex_prompt, run_with_nexus_codex_attempts


class TaskView:
    id = "nexus-task"
    trial_index = 2


def test_build_with_nexus_codex_prompt_contains_all_context_sections():
    result = build_with_nexus_codex_prompt(
        task=TaskView(),
        task_with_context="Fix the bug with CodeIntel context",
        route_prompt='{"recommended_flow":"hyper"}',
        codeintel_prompt='{"signals":["impact"]}',
        profile_prompt='{"candidate_count":3}',
        executor_flags_prompt='{"llm":true}',
        hidden_guidance="Patch source even when visible tests pass.",
        source="def target(): pass",
        visible_tests="def test_target(): pass",
    )

    assert result.reset_boundary_hash == hashlib.sha256(result.reset_boundary.encode("utf-8")).hexdigest()
    assert "NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id=nexus-task trial_index=2" in result.prompt
    assert "You are Codex wearing Nexus." in result.prompt
    assert "[TASK]\nFix the bug with CodeIntel context" in result.prompt
    assert "[NEXUS ROUTE SUMMARY]\n{\"recommended_flow\":\"hyper\"}" in result.prompt
    assert "[NEXUS CODEINTEL SUMMARY]\n{\"signals\":[\"impact\"]}" in result.prompt
    assert "[NEXUS EXECUTION PROFILE]\n{\"candidate_count\":3}" in result.prompt
    assert "[NEXUS EXECUTOR FLAGS]\n{\"llm\":true}" in result.prompt
    assert "[NEXUS HIDDEN-VERIFIER GUIDANCE]\nPatch source even when visible tests pass." in result.prompt
    assert "[CURRENT SOURCE]\ndef target(): pass" in result.prompt
    assert "[VISIBLE TESTS]\ndef test_target(): pass" in result.prompt


def test_build_with_nexus_codex_prompt_counts_nexus_control_chars():
    result = build_with_nexus_codex_prompt(
        task=TaskView(),
        task_with_context="task",
        route_prompt="route",
        codeintel_prompt="codeintel",
        profile_prompt="profile",
        executor_flags_prompt="flags",
        hidden_guidance="guidance",
        source="source",
        visible_tests="tests",
    )

    assert result.nexus_control_chars == len("route") + len("codeintel") + len("profile") + len("flags") + len("guidance")


def test_run_with_nexus_codex_attempts_verifies_first_patch_without_retry():
    writes: list[str] = []
    prompts: list[str] = []
    guard_entries = 0

    @contextmanager
    def socket_guard():
        nonlocal guard_entries
        guard_entries += 1
        yield

    def ask_patch(*, prompt: str, timeout_sec: int):
        prompts.append(f"{prompt}:{timeout_sec}")
        return {"patch": "new source"}, "raw response"

    result = run_with_nexus_codex_attempts(
        prompt="PROMPT",
        original="old source",
        ask_patch=ask_patch,
        apply_patch=writes.append,
        verify_patch=lambda: subprocess.CompletedProcess(["pytest"], 0, stdout="ok", stderr=""),
        remaining_timeout=lambda: 7,
        socket_guard=socket_guard,
    )

    assert prompts == ["PROMPT:7"]
    assert guard_entries == 1
    assert writes == ["new source"]
    assert result.status == "SUCCESS"
    assert result.err == ""
    assert result.patch == "new source"
    assert result.patch_changed is True
    assert result.self_heal_used is False
    assert result.self_heal_status == "not_needed"
    assert result.pytest_stdout_tail == "ok"
    assert result.raw_tail == "raw response"


def test_run_with_nexus_codex_attempts_recovers_with_bounded_retry():
    writes: list[str] = []
    prompts: list[str] = []
    verifier_results = [
        subprocess.CompletedProcess(["pytest"], 1, stdout="fail stdout", stderr="fail stderr"),
        subprocess.CompletedProcess(["pytest"], 0, stdout="retry ok", stderr=""),
    ]

    def ask_patch(*, prompt: str, timeout_sec: int):
        prompts.append(prompt)
        if len(prompts) == 1:
            return {"patch": "bad patch"}, "first raw"
        return {"patch": "fixed patch"}, "retry raw"

    result = run_with_nexus_codex_attempts(
        prompt="FIRST",
        original="old source",
        ask_patch=ask_patch,
        apply_patch=writes.append,
        verify_patch=lambda: verifier_results.pop(0),
        remaining_timeout=lambda: 5,
        retry_prompt_factory=lambda attempted_patch, pytest_stdout_tail, pytest_stderr_tail: (
            f"RETRY::{attempted_patch}::{pytest_stdout_tail}::{pytest_stderr_tail}"
        ),
    )

    assert prompts == ["FIRST", "RETRY::bad patch::fail stdout::fail stderr"]
    assert writes == ["bad patch", "fixed patch"]
    assert result.status == "SUCCESS"
    assert result.err == ""
    assert result.patch == "fixed patch"
    assert result.self_heal_used is True
    assert result.self_heal_status == "recovered"
    assert result.pytest_stdout_tail == "retry ok"


def test_run_with_nexus_codex_attempts_records_retry_noop_without_second_verify():
    verify_count = 0

    def verify_patch():
        nonlocal verify_count
        verify_count += 1
        return subprocess.CompletedProcess(["pytest"], 1, stdout="fail", stderr="")

    def ask_patch(*, prompt: str, timeout_sec: int):
        if prompt == "FIRST":
            return {"patch": "bad patch"}, ""
        return {"patch": "bad patch"}, ""

    result = run_with_nexus_codex_attempts(
        prompt="FIRST",
        original="old source",
        ask_patch=ask_patch,
        apply_patch=lambda _patch: None,
        verify_patch=verify_patch,
        remaining_timeout=lambda: 5,
        retry_prompt_factory=lambda attempted_patch, pytest_stdout_tail, pytest_stderr_tail: "RETRY",
    )

    assert verify_count == 1
    assert result.status == "FAILED"
    assert result.err == "pytest_failed"
    assert result.failure_reasons == ["pytest_failed"]
    assert result.self_heal_used is True
    assert result.self_heal_status == "retry_noop"
