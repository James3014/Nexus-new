# tests/services/test_self_heal_selector.py

from pathlib import Path
import os
import shutil

from nexus.services import self_heal_selector
from nexus.services.self_heal_selector import select_self_heal_route
from nexus.services.swarm_router import RouteCandidate


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


def test_self_heal_selector_uses_swarm_for_healthy(monkeypatch):
    """驗證有健康候選時使用 Swarm-gated 路由 (candidates injected; #2637)."""
    repo_root = Path(".") # 使用現有工作區
    diagnosis = {"phase": "R"}
    monkeypatch.setattr(
        self_heal_selector,
        "load_self_heal_candidates",
        lambda _root, phase, n: [
            RouteCandidate(
                route_id="injected-healthy",
                provider="local",
                armor_id="local",
                phase=phase,
                base_weight=0.8,
                success_rate=0.9,
                regression_pass_rate=0.95,
            )
        ][:n],
    )

    decision = select_self_heal_route(
        repo_root,
        "R",
        diagnosis,
    )
    
    # 正常情況下 (無 data 或正常 data) 為 swarm-gated
    assert decision["backend_used"] == "swarm-gated"
    assert "selected_route" in decision
    print(f"✅ Self-heal Selector Swarm Path Verified: {decision['selected_route']}")


def test_self_heal_selector_missing_candidate_source_fails_closed(tmp_path, caplog):
    """#2637: no candidate source must fail closed, never route to a fake "rust-v16"."""
    with caplog.at_level("WARNING", logger="nexus.services.self_heal_selector"):
        decision = select_self_heal_route(tmp_path, "R", {"phase": "R"})

    assert decision["backend_used"] == "fail-closed"
    assert decision["reason"] == self_heal_selector.SELF_HEAL_CANDIDATE_SOURCE_MISSING
    assert decision["selected_route"] != "rust-v16"
    assert "candidate source missing" in caplog.text


def test_self_heal_candidates_have_no_hardcoded_fallback(tmp_path):
    """#2637: the loader returns nothing rather than a hard-coded legacy route."""
    assert self_heal_selector.load_self_heal_candidates(tmp_path, "R", 8) == []
    source = Path(self_heal_selector.__file__).read_text(encoding="utf-8")
    assert "nexus.core.learning.compute_route_weights" not in source
    assert '"rust-v16"' not in source
