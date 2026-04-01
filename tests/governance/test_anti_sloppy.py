import pytest
from nexus.core.preflight_check import PreflightCheck
from nexus.core.access_control_list import AccessControlList
from nexus.health.scoring import HealthScorer
from nexus.core.state_contracts import NexusState

def test_preflight_blocking():
    # 模擬錯誤版本 (動態比對)
    specs = {"rustc": "1.99"} # 未發布版本，應攔截
    report = PreflightCheck.validate_environment(specs)
    assert report["status"] == "BLOCKED"
    
    # 模擬當前穩定版本 (按理應通過)
    specs_ok = {"rustc": "1.80"}
    report_ok = PreflightCheck.validate_environment(specs_ok)
    assert report_ok["status"] == "HEALTHY"

def test_acl_integrity_block():
    acl = AccessControlList()
    # 測試禁止 kill -9
    assert acl.check_permission("executor", "run_command", cmd="kill -9 1234") is False
    # 測試允許安全指令
    assert acl.check_permission("executor", "run_command", cmd="ls -la") is True

def test_scoring_governance_penalty():
    state = NexusState()
    # 模擬 1 次治理違規
    state.metadata["governance_violation_count"] = 1
    state.health_metrics.test_pass_rate = 1.0 # 滿分
    state.health_metrics.token_efficiency = 1.0 # 滿分
    
    # 即使基礎分是 100，偵測到違規後應強制限縮至 89.9 (WARNING)
    snapshot = HealthScorer.build_snapshot(state)
    assert snapshot.overall_score == 89.9
    assert snapshot.status == "WARNING"
