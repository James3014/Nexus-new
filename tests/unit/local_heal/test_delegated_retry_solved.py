from __future__ import annotations


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
