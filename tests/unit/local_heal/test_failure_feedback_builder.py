from __future__ import annotations

from nexus.services.local_heal.failure_feedback_builder import (
    build_failure_feedback,
    build_verifier_evidence_section,
    compute_verifier_evidence_hash,
)

def test_build_failure_feedback() -> None:
    feedback = build_failure_feedback(
        task_id="t1",
        failure_class="VERIFIER_FAIL",
        target_file="f.py",
        target_symbol="func",
        locked_search="print(1)",
        previous_block_reason="VERIFIER_FAIL",
        verifier_status="fail",
        stdout_tail="noise\nmore noise\nactual error",
        stderr_tail="stderr_error"
    )
    
    assert "Your previous unified diff failed verification." in feedback
    assert "Task ID: t1" in feedback
    assert "Failure Class: VERIFIER_FAIL" in feedback
    assert "Previous Block Reason: VERIFIER_FAIL" in feedback
    assert "Verifier Status: fail" in feedback
    assert "stderr_error" in feedback
    assert "print(1)" in feedback
    assert "Output Contract" in feedback


def test_failure_feedback_includes_fence_instruction_for_replacement_markdown_fence() -> None:
    feedback = build_failure_feedback(
        task_id="t_fence",
        failure_class="REPLACEMENT_MARKDOWN_FENCE",
        target_file="f.py",
        target_symbol="func",
        locked_search="print(1)",
        previous_block_reason="REPLACEMENT_MARKDOWN_FENCE",
        verifier_status="fail",
    )
    assert "Do NOT use markdown fences" in feedback
    assert "Do NOT output" in feedback
    assert "```python" in feedback or "```diff" in feedback
    assert "REPLACE" in feedback
    assert "<<<<<<< REPLACE" in feedback
    assert ">>>>>>> REPLACE" in feedback


def test_failure_feedback_other_classes_unchanged() -> None:
    feedback = build_failure_feedback(
        task_id="t_other",
        failure_class="VERIFIER_FAIL",
        target_file="f.py",
        target_symbol="func",
        locked_search="print(1)",
        previous_block_reason="VERIFIER_FAIL",
        verifier_status="fail",
    )
    assert "Your previous unified diff failed verification." in feedback
    assert "Do NOT use markdown fences" not in feedback


def test_failure_feedback_includes_replacement_only_instruction_for_prose_contamination() -> None:
    feedback = build_failure_feedback(
        task_id="t_prose",
        failure_class="REPLACEMENT_PROSE_CONTAMINATION",
        target_file="f.py",
        target_symbol="func",
        locked_search="print(1)",
        previous_block_reason="REPLACEMENT_PROSE_CONTAMINATION",
        verifier_status="fail",
    )
    assert "contained prose or commentary" in feedback
    assert "Do NOT include explanations" in feedback
    assert "Do NOT include markdown fences" in feedback
    assert "<<<<<<< REPLACE" in feedback
    assert ">>>>>>> REPLACE" in feedback


def test_failure_feedback_does_not_suggest_stripping_or_accepting_fences() -> None:
    feedback = build_failure_feedback(
        task_id="t_no_strip",
        failure_class="REPLACEMENT_MARKDOWN_FENCE",
        target_file="f.py",
        target_symbol="func",
        locked_search="print(1)",
        previous_block_reason="REPLACEMENT_MARKDOWN_FENCE",
        verifier_status="fail",
    )
    lines = [l for l in feedback.splitlines() if "task id" not in l.lower()]
    body = "\n".join(lines).lower()
    assert "strip the" not in body
    assert "stripping" not in body
    assert "accept fenced" not in body
    assert "remove the" not in body


def test_failure_feedback_preserves_locked_search_context() -> None:
    feedback = build_failure_feedback(
        task_id="t_locked",
        failure_class="REPLACEMENT_MARKDOWN_FENCE",
        target_file="f.py",
        target_symbol="func",
        locked_search="def foo():\n    return 42",
        previous_block_reason="REPLACEMENT_MARKDOWN_FENCE",
        verifier_status="fail",
    )
    assert "def foo():" in feedback
    assert "return 42" in feedback


# ---------------------------------------------------------------------------
# C15-3B: Verifier Evidence Prompt Injection Tests
# ---------------------------------------------------------------------------

def test_semantic_retry_prompt_includes_verifier_failure_kind():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="assertion_failure",
        verifier_stdout_excerpt="AssertionError: expected 42, got 0",
        verifier_stderr_excerpt="",
        verifier_exit_code=1,
        verifier_command_hash="abc123def456",
    )
    assert "assertion_failure" in prompt
    assert "VERIFIER FAILURE EVIDENCE" in prompt


def test_semantic_retry_prompt_includes_bounded_stdout_excerpt():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    stdout = "A" * 500
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="assertion_failure",
        verifier_stdout_excerpt=stdout,
        verifier_stderr_excerpt="",
        verifier_exit_code=1,
        verifier_command_hash="abc123",
    )
    assert stdout[:500] in prompt
    assert "Stdout excerpt (bounded)" in prompt


def test_semantic_retry_prompt_includes_bounded_stderr_excerpt():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    stderr = "B" * 500
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="exception",
        verifier_stdout_excerpt="",
        verifier_stderr_excerpt=stderr,
        verifier_exit_code=1,
        verifier_command_hash="abc123",
    )
    assert stderr[:500] in prompt
    assert "Stderr excerpt (bounded)" in prompt


def test_semantic_retry_prompt_includes_exit_code_and_command_hash():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="nonzero_exit",
        verifier_stdout_excerpt="",
        verifier_stderr_excerpt="",
        verifier_exit_code=42,
        verifier_command_hash="abc123def456",
    )
    assert "Exit code: 42" in prompt
    assert "Command hash: abc123def456" in prompt


def test_semantic_retry_prompt_does_not_include_raw_verifier_command():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="nonzero_exit",
        verifier_stdout_excerpt="",
        verifier_stderr_excerpt="",
        verifier_exit_code=1,
        verifier_command_hash="abc123",
    )
    # Raw command should not appear in the prompt
    assert "python3" not in prompt or "Command hash" in prompt
    # The evidence section should not contain raw command
    assert "python3 run_tests.sh" not in prompt


def test_semantic_retry_prompt_not_injected_when_evidence_not_ready():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="",
        verifier_stdout_excerpt="",
        verifier_stderr_excerpt="",
        verifier_exit_code="",
        verifier_command_hash="",
    )
    assert "VERIFIER FAILURE EVIDENCE" not in prompt


def test_semantic_retry_prompt_preserves_search_replace_contract():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="assertion_failure",
        verifier_stdout_excerpt="AssertionError",
        verifier_stderr_excerpt="",
        verifier_exit_code=1,
        verifier_command_hash="abc123",
    )
    assert "SEARCH/REPLACE" in prompt or "SEARCH" in prompt
    assert "<<<<<<< SEARCH" in prompt
    assert ">>>>>>> REPLACE" in prompt
    # Must not suggest prose or markdown fences
    assert "no prose" in prompt.lower() or "No prose" in prompt


def test_semantic_retry_prompt_does_not_change_route_or_verifier_claims():
    from nexus.services.local_heal.prompt_builder import PromptBuilder
    prompt = PromptBuilder.build_verification_guided_retry_prompt(
        original_user_prompt="fix the bug",
        verification_report="test failed",
        canonical_search_span="def foo():\n    pass",
        target_file="f.py",
        retry_count=1,
        verifier_failure_kind="assertion_failure",
        verifier_stdout_excerpt="AssertionError",
        verifier_stderr_excerpt="",
        verifier_exit_code=1,
        verifier_command_hash="abc123",
    )
    prompt_lower = prompt.lower()
    assert "bypass verifier" not in prompt_lower
    assert "mark solved" not in prompt_lower
    assert "solved=true" not in prompt_lower
    assert "verifier remains final authority" in prompt_lower


def test_semantic_retry_metadata_records_evidence_fields():
    from nexus.services.local_heal.local_model_executor import compute_verifier_failure_evidence
    evidence = compute_verifier_failure_evidence(
        verifier_result="fail",
        verifier_error="",
        exit_code=1,
        stdout_tail="AssertionError",
        stderr_tail="",
        verifier_command=("python3", "test.py"),
        failure_class="verification_failed",
        patch_lifecycle_state="isolation_applied_hash_match_verifier_failed",
    )
    assert "semantic_retry_verifier_evidence_injected" in evidence
    assert "semantic_retry_verifier_evidence_fields" in evidence
    assert "semantic_retry_prompt_evidence_hash" in evidence
    assert evidence["semantic_retry_verifier_evidence_injected"] is False


def test_m1_row_includes_semantic_retry_verifier_evidence_fields():
    from nexus.services.local_heal.local_model_executor import (
        LocalModelExecutor,
        LocalModelExecutorRequest,
    )
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
    from unittest.mock import patch
    req = LocalModelExecutorRequest(
        task_id="c15-3b-evidence-fields",
        problem_statement="test",
        repo_root="/workspace",
        target_file="file.py",
        selected_capabilities=(),
        evidence_refs=(),
        dry_run=False,
        route_context={
            "verifier_command": ["python3", "-c", "print(1)"],
            "signal_snapshot": {
                "execution_topology": "localheal_pipeline",
                "executor_model": "qwen2.5-coder:7b",
                "executor_provider": "ollama",
                "model_call_allowed": True,
                "selected_executor": "local_model",
                "protocol_mode": "anchored_edit",
                "mutation_allowed": True,
                "verifier_allowed": True,
            },
        },
    )
    with patch("nexus.services.local_heal.local_model_capability_executors.LocalHealPipelineCapabilityExecutor.execute") as mock_exec:
        from nexus.services.local_heal.local_model_capability_executors import CapabilityExecutionResult
        mock_exec.return_value = CapabilityExecutionResult(
            name="repair_loop", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False,
            evidence_present=True, failure_reason="NO_PATCH",
            telemetries={
                "pipeline_final_patch": "",
                "pipeline_solve_eligible": False,
                "pipeline_failure_reason": "NO_PATCH",
            }
        )
        resp = LocalModelExecutor.run(req, provider=InjectedLocalModelProvider(lambda _: ""))
    meta = resp.raw_model_metadata
    assert "semantic_retry_verifier_evidence_injected" in meta
    assert "semantic_retry_verifier_evidence_fields" in meta
    assert "semantic_retry_prompt_evidence_hash" in meta
