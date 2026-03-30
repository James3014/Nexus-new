import pytest
from nexus.core.outcome_schema import NexusOutcomeV1, NexusOutcomeV2, SchemaError

def test_outcome_v2_allowed_fields():
    """驗證 NexusOutcomeV2 在標準欄位下的初始化。"""
    out = NexusOutcomeV2(
        task_id="T123", 
        trace_id="tr-456",
        terminal_state="SUCCESS", 
        exit_code=0
    )
    assert out.task_id == "T123"
    assert out.outcome_version == "v2.1"

def test_outcome_v2_schema_safety():
    """驗證非法欄位注入時應拋出 SchemaError。"""
    # 建立物件後手動注入非法欄位並觸發校驗
    out = NexusOutcomeV2(task_id="T1")
    out.unauthorized_field = "malicious_data"
    
    with pytest.raises(SchemaError, match="unauthorized fields"):
        out.__post_init__()

def test_upgrade_from_v1():
    """驗證從舊版 V1 Schema 升級至 V2 的相容性。"""
    v1 = NexusOutcomeV1(
        task_id="T-OLD", 
        terminal_state="FAILED", 
        exit_code=1,
        commit_sha="abcd123"
    )
    v2 = NexusOutcomeV2.upgrade_from_v1(v1)
    
    assert v2.task_id == "T-OLD"
    assert v2.terminal_state == "FAILED"
    assert v2.commit_sha == "abcd123"
    assert v2.outcome_version == "v2.1"
    # 預設值檢查
    assert v2.trust_level == "production"
