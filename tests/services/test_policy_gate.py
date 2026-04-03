# tests/services/test_policy_gate.py

from pathlib import Path
import os
import shutil

from nexus.services.policy_gate import apply_policy_gate, GateSeverity


def test_policy_gate_blocks_low_health():
    """驗證健康度低於 0.3 時，觸發 BLOCK 並降分"""
    repo_root = Path("/tmp/mock_nexus_p3dy2")
    repo_root.mkdir(parents=True, exist_ok=True)
    
    health = {"health_score": 0.25, "phantom_fp_rate": 0.0}
    
    try:
        decision = apply_policy_gate(
            route_id="test-route",
            original_score=0.8,
            phase="R",
            health_metrics=health,
            repo_root=repo_root,
        )
        
        assert decision.decision == GateSeverity.BLOCK
        assert decision.gated_score < 0
        
        # 驗證持久化
        policy_file = repo_root / ".nexus" / "knowledge" / "policymemory.jsonl"
        assert policy_file.exists()
        print("\n✅ Policy Gate BLOCK Verified")
    finally:
        shutil.rmtree(repo_root)


def test_policy_gate_warns_high_phantom():
    """驗證高幻覺率時，觸發 WARN 並比例降權"""
    repo_root = Path("/tmp/mock_nexus_p3dy2_warn")
    repo_root.mkdir(parents=True, exist_ok=True)
    
    health = {"health_score": 0.8, "phantom_fp_rate": 0.25}
    
    try:
        decision = apply_policy_gate(
            route_id="test-route",
            original_score=0.85,
            phase="R",
            health_metrics=health,
            repo_root=repo_root,
        )
        
        assert decision.decision == GateSeverity.WARN
        assert decision.gated_score < 0.85
        print("✅ Policy Gate WARN Verified")
    finally:
        shutil.rmtree(repo_root)


def test_policy_gate_alerts_low_reuse():
    """驗證低 Pattern Reuse 時，觸發 ALERT 但不降分"""
    repo_root = Path("/tmp/mock_nexus_p3dy2_alert")
    repo_root.mkdir(parents=True, exist_ok=True)
    
    health = {
        "health_score": 0.7,
        "phantom_fp_rate": 0.0,
        "pattern_reuse": 0.4,
    }
    
    try:
        decision = apply_policy_gate(
            route_id="test-route",
            original_score=0.75,
            phase="R",
            health_metrics=health,
            repo_root=repo_root,
        )
        
        assert decision.decision == GateSeverity.ALERT
        assert decision.gated_score == 0.75
        print("✅ Policy Gate ALERT Verified")
    finally:
        shutil.rmtree(repo_root)
