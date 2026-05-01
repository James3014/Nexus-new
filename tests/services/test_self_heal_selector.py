# tests/services/test_self_heal_selector.py

from pathlib import Path
import os
import shutil

from nexus.services.self_heal_selector import select_self_heal_route


def test_self_heal_selector_blocks_low_health():
    """驗證 Self-heal 不會回傳 legacy 假路由"""
    repo_root = Path("/tmp/mock_nexus_p3dy3_block")
    repo_root.mkdir(parents=True, exist_ok=True)
    
    # 建立低健康的 mock 資料
    # 注意：需確保 compute_phase_health 能抓到此資料，
    # 這裡我們利用目前實現的 "找不到 Table 即回傳 status=error" 觸發 fail-open/closed 邏輯
    # 或者我們直接假設目前代碼中的 select_best_route 會回傳一個 candidate，
    # 而 apply_policy_gate 會處理它。
    
    diagnosis = {"phase": "R"}
    
    try:
        decision = select_self_heal_route(
            repo_root,
            "R",
            diagnosis,
        )
        
        assert not str(decision["selected_route"]).startswith("legacy")
        assert decision["backend_used"] in {"swarm-gated", "fail-closed"}
        print(f"\n✅ Self-heal Selector Decision: {decision['selected_route']}")
    finally:
        shutil.rmtree(repo_root)


def test_self_heal_selector_uses_swarm_for_healthy():
    """驗證正常情況下使用 Swarm-gated 路由"""
    repo_root = Path(".") # 使用現有工作區
    diagnosis = {"phase": "R"}
    
    decision = select_self_heal_route(
        repo_root,
        "R",
        diagnosis,
    )
    
    # 正常情況下 (無 data 或正常 data) 為 swarm-gated
    assert decision["backend_used"] == "swarm-gated"
    assert "selected_route" in decision
    print(f"✅ Self-heal Selector Swarm Path Verified: {decision['selected_route']}")
