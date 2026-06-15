import os
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from nexus.gate.experimental_gate import ExperimentalArchitectureGate, OptionalGatekeeper15B, EVIDENCE_LOG_PATH
from nexus.replay.replay_artifact import ReplayArtifact
from nexus.telemetry.telemetry_models import TelemetryBundle

@pytest.fixture(autouse=True)
def clean_env_and_log():
    # 測試前清理環境變數與證據日誌
    if "NEXUS_SHADOW_ADVISOR_ENABLED" in os.environ:
        del os.environ["NEXUS_SHADOW_ADVISOR_ENABLED"]
    if "NEXUS_GATEKEEPER_15B_ENABLED" in os.environ:
        del os.environ["NEXUS_GATEKEEPER_15B_ENABLED"]
    if EVIDENCE_LOG_PATH.exists():
        try:
            EVIDENCE_LOG_PATH.unlink()
        except OSError:
            pass
    yield
    if EVIDENCE_LOG_PATH.exists():
        try:
            EVIDENCE_LOG_PATH.unlink()
        except OSError:
            pass

def _mock_telemetry():
    t = MagicMock(spec=TelemetryBundle)
    t.complete = True
    return t

def _mock_replay(status="SUCCESS"):
    r = MagicMock(spec=ReplayArtifact)
    r.status = status
    return r

# --- Phase 3: Optional 1.5B Gatekeeper Tests ---

def test_gatekeeper_15b_screening_logic():
    gatekeeper = OptionalGatekeeper15B()
    
    # 1. Short low-value task: need_deliberation=False
    short_task = {"task_type": "bugfix", "value_tier": 20.0}
    res = gatekeeper.screen(short_task)
    assert res["need_3b"] is True
    assert res["need_deliberation"] is False
    assert res["risk_tier"] == "low"
    
    # 2. High-value/complex task: need_deliberation=True
    complex_task = {"task_type": "repair-review", "value_tier": 150.0}
    res2 = gatekeeper.screen(complex_task)
    assert res2["need_deliberation"] is True
    assert res2["risk_tier"] == "high"

def test_gatekeeper_15b_disabled_behavior():
    os.environ["NEXUS_GATEKEEPER_15B_ENABLED"] = "0"
    gatekeeper = OptionalGatekeeper15B()
    
    # Even a complex task should return low-risk default hints when disabled
    complex_task = {"task_type": "repair-review", "value_tier": 150.0}
    res = gatekeeper.screen(complex_task)
    assert res["need_deliberation"] is False
    assert res["risk_tier"] == "low"

# --- Phase 5: Experimental Architecture Gate & Maturity Tests ---

def test_check_maturity_validation():
    # 1. Missing keys should fail
    bad_specs = {"rollback_path": "path/to/revert"}
    assert ExperimentalArchitectureGate.check_maturity("test-m1", bad_specs) is False
    
    # 2. Over-budget should fail
    overbudget_specs = {
        "rollback_path": "path/to/revert",
        "token_budget": 2000000.0,
        "runtime_fitness_report": "report.md"
    }
    assert ExperimentalArchitectureGate.check_maturity("test-m2", overbudget_specs) is False
    
    # 3. Valid specs should pass
    good_specs = {
        "rollback_path": "path/to/revert",
        "token_budget": 50000.0,
        "runtime_fitness_report": "report.md"
    }
    assert ExperimentalArchitectureGate.check_maturity("test-m3", good_specs) is True

def test_shadow_decide_maturity_logging():
    os.environ["NEXUS_SHADOW_ADVISOR_ENABLED"] = "True"
    r = _mock_replay(status="SUCCESS")
    t = _mock_telemetry()
    
    good_specs = {
        "rollback_path": "path/to/revert",
        "token_budget": 50000.0,
        "runtime_fitness_report": "report.md"
    }
    
    result = ExperimentalArchitectureGate.shadow_decide(
        ticket_id="test-ticket-maturity-1",
        replay=r,
        telemetry=t,
        experimental_advisor_decision={"allowed": False},
        model_id="qwen-3b-lora",
        model_specs=good_specs
    )
    
    assert result["is_mature_for_main_path"] is True
    assert EVIDENCE_LOG_PATH.exists()
    logs = [json.loads(line) for line in EVIDENCE_LOG_PATH.read_text().splitlines() if line.strip()]
    assert len(logs) == 1
    assert logs[0]["is_mature"] is True

def test_shadow_disabled_returns_baseline_directly():
    r = _mock_replay(status="SUCCESS")
    t = _mock_telemetry()
    
    result = ExperimentalArchitectureGate.shadow_decide(
        ticket_id="test-ticket-1",
        replay=r,
        telemetry=t,
        experimental_advisor_decision={"allowed": False}
    )
    
    assert result["allowed"] is True
    assert not EVIDENCE_LOG_PATH.exists()

def test_shadow_enabled_records_log_and_retains_baseline():
    os.environ["NEXUS_SHADOW_ADVISOR_ENABLED"] = "True"
    r = _mock_replay(status="SUCCESS")
    t = _mock_telemetry()
    
    result = ExperimentalArchitectureGate.shadow_decide(
        ticket_id="test-ticket-2",
        replay=r,
        telemetry=t,
        experimental_advisor_decision={"allowed": False}
    )
    
    assert result["allowed"] is True
    assert result["shadow_observation_only"] is True
    assert result["trust_mismatch_detected"] is True
    assert result["fallback_triggered"] is False
    
    assert EVIDENCE_LOG_PATH.exists()
    logs = [json.loads(line) for line in EVIDENCE_LOG_PATH.read_text().splitlines() if line.strip()]
    assert len(logs) == 1
    assert logs[0]["ticket_id"] == "test-ticket-2"
    assert logs[0]["is_mismatch"] is True
    assert logs[0]["fallback_triggered"] is False

def test_shadow_enabled_exception_fallback():
    os.environ["NEXUS_SHADOW_ADVISOR_ENABLED"] = "True"
    r = _mock_replay(status="SUCCESS")
    t = _mock_telemetry()
    
    bad_decision = MagicMock()
    bad_decision.get.side_effect = ValueError("Advisory crash")
    
    result = ExperimentalArchitectureGate.shadow_decide(
        ticket_id="test-ticket-3",
        replay=r,
        telemetry=t,
        experimental_advisor_decision=bad_decision
    )
    
    assert result["allowed"] is True
    assert result["fallback_triggered"] is True
    
    assert EVIDENCE_LOG_PATH.exists()
    logs = [json.loads(line) for line in EVIDENCE_LOG_PATH.read_text().splitlines() if line.strip()]
    assert len(logs) == 1
    assert logs[0]["ticket_id"] == "test-ticket-3"
    assert logs[0]["fallback_triggered"] is True
