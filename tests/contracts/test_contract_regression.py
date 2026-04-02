from pathlib import Path
import json
from dataclasses import fields

from nexus.core.outcome_schema import NexusOutcomeV2, _ALLOWED_FIELDS_V2, OUTCOME_SCHEMA_VERSION
from nexus.core.skill_outcomes import OutcomePayload
from nexus.engine.pipeline_outcome import PipelineTerminalState

GOLDEN_DIR = Path(__file__).parent / "golden"

def test_outcome_v2_schema_contract():
    """驗證 NexusOutcomeV2 的 schema 不可漂移"""
    golden_path = GOLDEN_DIR / "outcome_v2_fields.json"
    golden_data = json.loads(golden_path.read_text())
    
    # 1. 驗證欄位名單
    expected_fields = set(golden_data["allowed_fields"])
    actual_fields = _ALLOWED_FIELDS_V2
    assert actual_fields == expected_fields, f"Schema 欄位漂移！預期: {expected_fields}, 實際: {actual_fields}"
    
    # 2. 驗證版本號
    assert OUTCOME_SCHEMA_VERSION == golden_data["schema_version"], "Schema 版本號與快照不符！若更新欄位請同步更新 golden 快照與版本號。"

def test_outcome_payload_contract():
    """驗證 OutcomePayload 參數物件不可漂移"""
    golden_path = GOLDEN_DIR / "outcome_payload_fields.json"
    golden_data = json.loads(golden_path.read_text())
    
    expected_fields = set(golden_data["fields"])
    actual_fields = {f.name for f in fields(OutcomePayload)}
    assert actual_fields == expected_fields, f"OutcomePayload 欄位漂移！預期: {expected_fields}, 實際: {actual_fields}"

def test_exit_code_registry_contract():
    """驗證 PipelineTerminalState 四態映射不可漂移"""
    golden_path = GOLDEN_DIR / "exit_code_registry.json"
    golden_data = json.loads(golden_path.read_text())
    
    expected_states = golden_data["terminal_states"]
    
    assert PipelineTerminalState.SUCCESS.value == expected_states["SUCCESS"]
    assert PipelineTerminalState.FAILED.value == expected_states["FAILED"]
    assert PipelineTerminalState.ESCALATED.value == expected_states["ESCALATED"]
    assert PipelineTerminalState.HUMAN_REVIEW.value == expected_states["HUMAN_REVIEW"]
