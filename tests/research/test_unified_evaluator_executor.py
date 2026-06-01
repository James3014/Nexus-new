import threading
import time

from nexus.research.unified_evaluator import UnifiedEvaluator


def test_unified_evaluator_parallel_executor_reaches_concurrency():
    evaluator = UnifiedEvaluator(budget_limit=10.0, min_score_threshold=0.0)
    evaluator.FIXED_SEEDS = [1, 2, 3]
    lock = threading.Lock()
    active = {"count": 0, "peak": 0}

    def test_fn(_seed: int):
        with lock:
            active["count"] += 1
            active["peak"] = max(active["peak"], active["count"])
        time.sleep(0.05)
        with lock:
            active["count"] -= 1
        return {"score": 1.0, "cost": 1.0}

    report = evaluator.evaluate(
        candidate_id="c-parallel",
        test_fn=test_fn,
        estimated_cost_per_round=1.0,
        max_parallel=3,
        max_retries=0,
        timeout_sec=1.0,
    )

    assert report["passed_gate"] is True
    assert len(report["seed_details"]) == 3
    assert active["peak"] >= 2


def test_unified_evaluator_timeout_and_retry():
    evaluator = UnifiedEvaluator(budget_limit=10.0, min_score_threshold=0.0)
    evaluator.FIXED_SEEDS = [7]
    attempts = {"n": 0}

    def test_fn(_seed: int):
        attempts["n"] += 1
        time.sleep(0.05)
        return {"score": 1.0, "cost": 1.0}

    report = evaluator.evaluate(
        candidate_id="c-timeout",
        test_fn=test_fn,
        estimated_cost_per_round=1.0,
        max_parallel=1,
        max_retries=1,
        timeout_sec=0.01,
    )

    assert attempts["n"] >= 2
    assert len(report["seed_details"]) == 1
    assert "error" in report["seed_details"][0]
    assert report["seed_details"][0]["attempts"] == 2
