import logging
import queue
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class UnifiedEvaluator:
    """
    🧬 AutoResearch 統一評估器 (v1.3 Zero-Overshoot + Executor)
    強制執行嚴格預算、多框架固定 Seeds，並提供並行/重試/超時執行層。
    """

    FIXED_SEEDS = [42, 1337, 2026]

    def __init__(self, budget_limit: float = 100.0, min_score_threshold: float = 0.5):
        self.budget_limit = budget_limit
        self.min_score_threshold = min_score_threshold
        self.scoreboard: Dict[str, Dict[str, Any]] = {}

    def _set_deterministic_seeds(self, seed: int):
        random.seed(seed)
        try:
            import numpy as np

            np.random.seed(seed)
        except ImportError:
            pass
        try:
            import torch

            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
        except ImportError:
            pass

    def evaluate(
        self,
        candidate_id: str,
        test_fn: Callable[[int], Dict[str, Any]],
        estimated_cost_per_round: float = 1.0,
        max_parallel: int = 1,
        max_retries: int = 0,
        timeout_sec: float = 600.0,
    ) -> Dict[str, Any]:
        """
        執行評估。落實 No-Overshoot 契約：
        若執行下一輪可能導致 total_cost > budget_limit，則立即終止。
        """
        start_time = time.time()
        results: List[Dict[str, Any]] = []
        total_score = 0.0
        total_cost = 0.0

        if estimated_cost_per_round > 0:
            affordable_rounds = int(self.budget_limit // estimated_cost_per_round)
        else:
            affordable_rounds = len(self.FIXED_SEEDS)
        seeds_to_run = self.FIXED_SEEDS[: max(0, min(len(self.FIXED_SEEDS), affordable_rounds))]
        if not seeds_to_run and self.FIXED_SEEDS:
            logger.warning("⚠️ [Evaluator] Budget limit guard activated for %s", candidate_id)

        worker_count = max(1, min(max_parallel, len(seeds_to_run) or 1))

        def _run_with_timeout(seed: int) -> Dict[str, Any]:
            out_queue: queue.Queue = queue.Queue(maxsize=1)

            def _target():
                try:
                    out_queue.put(("ok", test_fn(seed)))
                except Exception as exc:  # noqa: BLE001
                    out_queue.put(("err", exc))

            thread = threading.Thread(target=_target, daemon=True)
            thread.start()
            thread.join(timeout=timeout_sec)
            if thread.is_alive():
                raise TimeoutError(f"seed {seed} timed out after {timeout_sec}s")
            status, payload = out_queue.get_nowait()
            if status == "err":
                raise payload
            return payload

        def _run_seed(seed: int) -> Dict[str, Any]:
            errors: List[str] = []
            for attempt in range(1, max_retries + 2):
                self._set_deterministic_seeds(seed)
                try:
                    round_start = time.time()
                    res = _run_with_timeout(seed)
                    return {
                        "seed": seed,
                        "score": float(res.get("score", 0.0)),
                        "cost": float(res.get("cost", estimated_cost_per_round)),
                        "attempts": attempt,
                        "duration_sec": round(time.time() - round_start, 4),
                    }
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
                    errors.append(err)
                    logger.warning(
                        "⚠️ [Evaluator] Seed %d attempt %d/%d failed: %s",
                        seed,
                        attempt,
                        max_retries + 1,
                        err,
                    )
            return {
                "seed": seed,
                "error": errors[-1] if errors else "unknown_error",
                "attempts": max_retries + 1,
                "attempt_errors": errors,
            }

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_seed = {executor.submit(_run_seed, seed): seed for seed in seeds_to_run}
            for future in as_completed(future_to_seed):
                seed = future_to_seed[future]
                try:
                    seed_result = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error("❌ [Evaluator] Seed %d executor failure: %s", seed, exc)
                    results.append({"seed": seed, "error": str(exc), "attempts": 1})
                    continue

                if "error" in seed_result:
                    results.append(seed_result)
                    continue

                cost = float(seed_result.get("cost", estimated_cost_per_round))
                if total_cost + cost > self.budget_limit:
                    logger.error("🛑 [Evaluator] Single round cost spike! Stopping to prevent overshoot.")
                    continue

                total_score += float(seed_result.get("score", 0.0))
                total_cost += cost
                results.append(seed_result)

        results.sort(key=lambda item: item.get("seed", 0))
        avg_score = total_score / len(results) if results else 0.0

        report = {
            "candidate_id": candidate_id,
            "average_score": avg_score,
            "total_cost": total_cost,
            "passed_gate": avg_score >= self.min_score_threshold,
            "seed_details": results,
            "execution": {
                "max_parallel": max_parallel,
                "max_retries": max_retries,
                "timeout_sec": timeout_sec,
                "elapsed_sec": round(time.time() - start_time, 4),
            },
        }
        self.scoreboard[candidate_id] = report
        return report

    def get_best_candidate(self) -> Optional[str]:
        if not self.scoreboard:
            return None
        return max(self.scoreboard, key=lambda k: self.scoreboard[k]["average_score"])
