from __future__ import annotations

from typing import Any


class DDTreeAdapter:
    """Deterministic pruning layer for candidate-heavy Nexus runs."""

    def plan(
        self,
        candidates: list[dict[str, Any]],
        *,
        task_desc: str = "",
        enabled: bool = False,
        max_candidates: int = 2,
    ) -> dict[str, Any]:
        normalized = [
            {
                "candidate_id": str(item.get("candidate_id") or item.get("id") or f"candidate-{index + 1}"),
                "score": float(item.get("score", 0.0) or 0.0),
                "evidence_count": len(item.get("evidence_refs", []) or []),
            }
            for index, item in enumerate(candidates)
        ]
        eligible = len(normalized) > max(1, max_candidates)
        if not enabled or not eligible:
            return {
                "schema": "nexus_ddtree_plan_v2",
                "enabled": bool(enabled),
                "eligible": eligible,
                "task_desc": task_desc,
                "selected_candidate_ids": [item["candidate_id"] for item in normalized],
                "estimated_saved_steps": 0,
                "actual_saved_steps": 0,
                "reason": "disabled" if not enabled else "candidate_count_within_budget",
                "pruning_mode": "tree",
                "root_node_id": "root",
                "tree_stats": {
                    "max_depth": 0,
                    "branch_count": len(normalized),
                    "leaf_count": len(normalized),
                    "pruned_count": 0,
                },
                "prune_events": [],
            }
        ranked = sorted(normalized, key=lambda item: (item["score"], item["evidence_count"], item["candidate_id"]), reverse=True)
        selected = ranked[: max(1, max_candidates)]
        selected_ids = [item["candidate_id"] for item in selected]
        input_ids = [item["candidate_id"] for item in normalized]
        pruned_ids = [item["candidate_id"] for item in ranked if item["candidate_id"] not in set(selected_ids)]
        saved = max(0, len(normalized) - len(selected))
        return {
            "schema": "nexus_ddtree_plan_v2",
            "enabled": True,
            "eligible": True,
            "task_desc": task_desc,
            "selected_candidate_ids": selected_ids,
            "estimated_saved_steps": saved,
            "actual_saved_steps": saved,
            "reason": "deterministic_score_pruning",
            "pruning_mode": "tree",
            "root_node_id": "root",
            "tree_stats": {
                "max_depth": 1,
                "branch_count": len(normalized),
                "leaf_count": len(normalized),
                "pruned_count": saved,
            },
            "prune_events": [
                {
                    "node_id": "root",
                    "depth": 0,
                    "input_candidate_ids": input_ids,
                    "kept_candidate_ids": selected_ids,
                    "pruned_candidate_ids": pruned_ids,
                    "criterion": "score_then_evidence",
                }
            ],
        }
