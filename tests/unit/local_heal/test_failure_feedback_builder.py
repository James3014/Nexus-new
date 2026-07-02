from __future__ import annotations

from nexus.services.local_heal.failure_feedback_builder import build_failure_feedback

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
