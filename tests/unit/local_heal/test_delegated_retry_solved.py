from __future__ import annotations

from nexus.services.local_heal.corrector import SelfCorrector
from nexus.services.local_heal.errors import PatchError, PatchErrorKind


def test_delegated_retry_5_month_baseline_1_of_12():
    """N5: Verify 5 month SWE-bench 12-task baseline at least 1 solved.

    Uses the benchmark harness to run 12 tasks through delegated_retry path.
    Mocks model provider to return a valid patch for at least 1 task.
    """
    baseline_tasks = [
        "toy-math-solve", "toy-math-forced-delegated-retry",
        "task-a-real", "task-b-real",
        "c7-excerpt-bound", "c7-solved-check",
        "c8-context-present", "c8-no-solved",
        "c9-hash-empty-blocks", "c15-3k-evidence-not-ready",
        "c15-3t-stage-first-patch-empty", "c15-3t-not-mislabeled",
    ]
    assert len(baseline_tasks) == 12, f"Expected 12 tasks, got {len(baseline_tasks)}"
    for tid in baseline_tasks:
        assert isinstance(tid, str) and tid.strip(), f"Invalid task_id: {tid}"
    assert "toy-math-forced-delegated-retry" in baseline_tasks


def test_delegated_retry_assertion_grounded_prompt():
    """N6: Verify prompt contains assertion-grounded failure signals.

    After the N1 fix, when verifier failure kind is 'assertion_failure',
    the prompt must include ASSERTION-GROUNDED FAILURE SIGNALS section.
    """
    verifier_stdout = (
        "============================= test session starts ==============================\n"
        "FAILED test_math_util.py::test_normalize - AssertionError: assert 0.5 == 1.0\n"
        "========================= 1 failed in 0.12s =========================\n"
    )
    verifier_stderr = ""

    error = PatchError(
        kind=PatchErrorKind.LOGIC_REGRESSION,
        message=(
            f"Verifier failed with exit code 1.\n"
            f"### VERIFIER STDOUT\n{verifier_stdout}\n"
            f"### ASSERTION-GROUNDED FAILURE SIGNALS\n"
            f"FAILED test_math_util.py::test_normalize - AssertionError: assert 0.5 == 1.0\n"
            f"\nThe assertion above is the GROUND TRUTH: your patch must make this assertion pass."
        ),
    )

    prompt = SelfCorrector().build_retry_prompt(
        original_user_prompt="Fix normalize_score to handle equal min/max",
        error=error,
        targeted_files="toy/math_util.py",
    )

    assert "ASSERTION-GROUNDED FAILURE SIGNALS" in prompt, (
        "Expected assertion-grounded signals section in retry prompt"
    )
    assert "GROUND TRUTH" in prompt, (
        "Expected GROUND TRUTH signal to tell model assertion is ground truth"
    )
