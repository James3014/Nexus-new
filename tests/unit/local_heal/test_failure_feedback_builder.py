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
