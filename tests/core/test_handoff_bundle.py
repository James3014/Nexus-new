from pathlib import Path
import pytest
import json
from unittest.mock import MagicMock, patch
from nexus.core.handoff_bundle import HandoffBundleWriter, HandoffRequest

@pytest.fixture
def writer(tmp_path):
    from nexus.core.handoff_bundle import HandoffRetentionPolicy
    # 關閉壓縮以利測試直接讀取 JSON
    policy = HandoffRetentionPolicy(compress=False)
    return HandoffBundleWriter(tmp_path, policy=policy)

def test_handoff_request_instantiation():
    """驗證 HandoffRequest 的資料結構。"""
    req = HandoffRequest(
        triggering_phase="repair",
        reason="test escalation",
        task_id="T123",
        state_variables={"foo": "bar"}
    )
    assert req.task_id == "T123"
    assert req.triggering_phase == "repair"

def test_handoff_bundle_create(writer, tmp_path):
    """驗證 Handoff Bundle 的寫入與內容。"""
    req = HandoffRequest(
        triggering_phase="diagnosis",
        reason="complex failure",
        task_id="T123",
        state_variables={"metadata": "test"}
    )
    
    with patch("subprocess.check_output") as mock_git:
        mock_git.return_value = "fake diff stat"
        bundle_path = writer.create(req)
    
    assert bundle_path.exists()
    assert bundle_path.suffix == ".json"
    
    # 讀取並驗證 JSON 內容
    data = json.loads(bundle_path.read_text())
    assert data["task_id"] == "T123"
    assert data.get("triggering_phase") == "diagnosis"
    assert data["workspace_diff"] == "fake diff stat"
    assert data["state_variables"]["metadata"] == "test"

def test_handoff_bundle_filename_format(writer):
    """驗證 Bundle 檔名格式。"""
    req = HandoffRequest(triggering_phase="...", reason="...", task_id="T999")
    bundle_path = writer.create(req)
    # 應包含 task_id 且以 handoff_ 開頭
    assert "handoff_T999" in bundle_path.name


def test_handoff_persists_lineage_and_fail_closed_resume_gate(writer):
    req = HandoffRequest(
        triggering_phase="assist",
        reason="disconnect",
        task_id="T-lineage",
        attempt_id="A1",
        action_id="ACT1",
        idempotency_key="ID1",
        last_successful_action="nexus_task_submit",
        uncertain_mutation=True,
    )
    data = json.loads(writer.create(req).read_text())
    assert data["attempt_id"] == "A1"
    assert data["action_id"] == "ACT1"
    assert data["last_successful_action"] == "nexus_task_submit"
    assert data["uncertain_mutation"] is True
    assert data["resume_gate"] == "RECONCILE_REQUIRED"
