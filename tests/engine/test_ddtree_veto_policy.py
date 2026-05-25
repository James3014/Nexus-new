from __future__ import annotations

import pytest
from nexus.engine.ddtree_adapter import check_veto_state, DDTreeAdapter


def test_ddtree_veto_policy_consensus_decision():
    # 1. 雙軌一票否決觸發：主觀剪枝 + 客觀測試 PASS -> Veto 成功 (True)
    assert check_veto_state(pruned_state=True, test_result_pass=True) is True

    # 2. 客觀測試 FAIL -> 不可 Veto (False)
    assert check_veto_state(pruned_state=True, test_result_pass=False) is False

    # 3. 未被主觀剪枝 -> 不可 Veto (False)
    assert check_veto_state(pruned_state=False, test_result_pass=True) is False
    assert check_veto_state(pruned_state=False, test_result_pass=False) is False


def test_ddtree_adapter_veto_keeps_provenance_candidate():
    # 測試 DDTreeAdapter.plan 中 Test Veto 撈回邏輯的實體整合
    candidates = [
        {"candidate_id": "a", "score": 0.1, "evidence_refs": ["pytest.log"]},  # 低分但有測試綠燈證據 -> 應被 Veto 撈回
        {"candidate_id": "b", "score": 0.9},                                  # 高分但無證據 -> 保留
        {"candidate_id": "c", "score": 0.4},                                  # 中分無證據 -> 剪枝
    ]

    out = DDTreeAdapter().plan(
        candidates,
        enabled=True,
        max_candidates=1,  # 額度僅 1 個
    )

    # 斷言 schema 與基礎資料正確
    assert out["schema"] == "nexus_ddtree_plan_v2"
    assert out["eligible"] is True

    # 斷言 selected_candidate_ids 中：
    # "b" 因 score 高保留 (0.9 >= 1st)
    # "a" 因 score 低 (0.1, 屬於 idx >= 1 剪枝區)，但觸發了 Test Veto 被強制撈回！
    # "c" 因 score 低且無證據，維持剪枝！
    assert "b" in out["selected_candidate_ids"]
    assert "a" in out["selected_candidate_ids"]
    assert "c" not in out["selected_candidate_ids"]

    # 斷言原始輸入順序得以維持
    assert out["selected_candidate_ids"] == ["a", "b"]
    assert out["tree_stats"]["pruned_count"] == 1
    assert "c" in out["prune_events"][0]["pruned_candidate_ids"]
    assert "a" not in out["prune_events"][0]["pruned_candidate_ids"]
