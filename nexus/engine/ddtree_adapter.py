"""🧬 Nexus v4.1: 雙軌一票否決與剪枝自癒適配器

職責：實作主客觀雙軌共識。客觀的測試證據（Pytest PASS）擁有一票否決主觀 AI 剪枝的權力。
"""
from __future__ import annotations


def check_veto_state(pruned_state: bool, test_result_pass: bool) -> bool:
    """雙軌測試一票否決演算法
    Veto = True 若且唯若 AI 主觀下達剪枝 (pruned_state=True) 且客觀測試 PASS (test_result_pass=True)。
    """
    return bool(pruned_state and test_result_pass)


class DDTreeAdapter:
    """🧬 Nexus v4.1: 樹狀決策剪枝與一票否決適配器"""

    def plan(
        self,
        candidates: list[dict],
        enabled: bool = True,
        max_candidates: int = 2,
    ) -> dict:
        if not enabled:
            return {
                "enabled": False,
                "eligible": True,
                "selected_candidate_ids": [c["candidate_id"] for c in candidates],
                "reason": "disabled",
            }

        # 優先依照 score 從大到小排序
        sorted_candidates = sorted(
            candidates, key=lambda x: x.get("score", 0.0), reverse=True
        )

        kept = []
        pruned = []

        for idx, c in enumerate(sorted_candidates):
            cid = c["candidate_id"]
            # 判斷是否原本屬於會被剪枝的區間（超出 max_candidates 額度）
            is_initially_pruned = idx >= max_candidates

            # 客觀證據判定：是否有 pytest.log 或含 pass 標記之測試證據
            has_pass_evidence = any(
                "pytest" in str(ref) or "pass" in str(ref).lower()
                for ref in c.get("evidence_refs", [])
            )

            # 應用 check_veto_state 雙軌自癒共識
            is_vetoed = check_veto_state(
                pruned_state=is_initially_pruned,
                test_result_pass=has_pass_evidence
            )

            if not is_initially_pruned or is_vetoed:
                kept.append(c)
            else:
                pruned.append(c)

        selected_ids = [c["candidate_id"] for c in kept]
        pruned_ids = [c["candidate_id"] for c in pruned]

        # 保持與原始輸入順序一致地回傳 selected 列表
        ordered_selected_ids = [
            c["candidate_id"] for c in candidates if c["candidate_id"] in selected_ids
        ]
        ordered_pruned_ids = [
            c["candidate_id"] for c in candidates if c["candidate_id"] in pruned_ids
        ]

        actual_saved = len(candidates) - len(ordered_selected_ids)

        return {
            "schema": "nexus_ddtree_plan_v2",
            "eligible": True,
            "selected_candidate_ids": ordered_selected_ids,
            "actual_saved_steps": actual_saved,
            "pruning_mode": "tree",
            "root_node_id": "root",
            "tree_stats": {
                "max_depth": 1,
                "branch_count": len(candidates),
                "leaf_count": len(candidates),
                "pruned_count": len(pruned),
            },
            "prune_events": [
                {
                    "node_id": "root",
                    "depth": 0,
                    "input_candidate_ids": [c["candidate_id"] for c in candidates],
                    "kept_candidate_ids": ordered_selected_ids,
                    "pruned_candidate_ids": ordered_pruned_ids,
                    "criterion": "score_then_evidence",
                }
            ],
        }
