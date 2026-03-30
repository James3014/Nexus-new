import pytest
from nexus.core.state_migrator import StateMigrator

def test_state_migrator_token_mapping():
    """驗證舊版 Token 欄位是否正確映射到新版結構。"""
    legacy_data = {
        "total_token_usage": 1000,
        "token_raw_model": 800,
        "other": "value"
    }
    migrated = StateMigrator.migrate(legacy_data)
    assert migrated["tokens"]["total_usage"] == 1000
    assert migrated["tokens"]["raw_model"] == 800
    assert migrated["other"] == "value"
    assert "total_token_usage" not in migrated

def test_state_migrator_observability_mapping():
    """驗證觀測性欄位 (Trace/Span) 的映射。"""
    legacy_data = {
        "trace_id": "tr-123",
        "span_id": "sp-456"
    }
    migrated = StateMigrator.migrate(legacy_data)
    assert migrated["observability"]["trace_id"] == "tr-123"
    assert migrated["observability"]["span_id"] == "sp-456"

def test_state_migrator_audit_and_health_mapping():
    """驗證審計與健康指標的映射過程。"""
    legacy_data = {
        "audit_pass_count": 5,
        "retry_count": 2,
        "health_score": 0.85,
        "learning_velocity": 0.7
    }
    migrated = StateMigrator.migrate(legacy_data)
    
    assert migrated["audit"]["audit_pass_count"] == 5
    assert migrated["audit"]["retry_count"] == 2
    assert migrated["phase_health"]["health_score"] == 0.85
    assert migrated["phase_health"]["learning_velocity"] == 0.7

def test_state_migrator_non_dict_input():
    """驗證輸入非字典時應原樣回傳。"""
    assert StateMigrator.migrate("not a dict") == "not a dict"
    assert StateMigrator.migrate(None) is None
