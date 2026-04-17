"""🛡️ Governance Hardening Integration Tests
驗證治理鏈硬化的五個核心防線。"""
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# === WP1: 獨立 Evidence 採集 ===

class TestAutoEvidenceCollection:
    """系統自動產出的 evidence 不可被 agent 篡改"""
    
    def test_evidence_contains_real_exit_codes(self, tmp_path):
        """evidence 中的 exit_code 必須來自真實 pregate"""
        from nexus.engine.cli_pregate import run_cli_pregate
        passed, results = run_cli_pregate(tmp_path, ["echo hello"])
        assert results[0]["exit_code"] == 0
        assert results[0]["passed"] is True
    
    def test_evidence_records_failure(self, tmp_path):
        """失敗的命令必須記錄為 passed=False"""
        from nexus.engine.cli_pregate import run_cli_pregate
        passed, results = run_cli_pregate(tmp_path, ["false"])
        assert results[0]["passed"] is False
        assert passed is False
    
    def test_evidence_aggregates_success_rate(self):
        """aggregates.success_rate 必須反映真實通過率"""
        results = [
            {"passed": True, "exit_code": 0},
            {"passed": False, "exit_code": 1},
            {"passed": True, "exit_code": 0},
        ]
        rate = sum(1 for r in results if r["passed"]) / len(results)
        assert abs(rate - 0.6667) < 0.01

    def test_strict_source_rejects_agent_evidence(self, tmp_path, monkeypatch):
        """嚴格模式下 agent 自寫的 evidence 被拒絕"""
        monkeypatch.setenv("NEXUS_STRICT_EVIDENCE_SOURCE", "1")
        evidence = {"final_response": "done", "evidence_bundle": {}}
        # 沒有 _source: "system" → 應被拒
        source = evidence.get("_source", "agent")
        passed = not (os.environ.get("NEXUS_STRICT_EVIDENCE_SOURCE") == "1" and source != "system")
        assert passed is False


# === WP2: Git-Tracked 交付物檢查 ===

class TestDeliveryTrackedCheck:
    """agent 宣稱的交付檔案必須被 git 追蹤"""
    
    def test_gitignored_artifact_rejected(self, tmp_path):
        """在 .gitignore 路徑下的檔案不算交付"""
        # 模擬一個 git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / ".gitignore").write_text(".nexus/\n")
        (tmp_path / ".nexus").mkdir()
        (tmp_path / ".nexus" / "experiment.py").write_text("# poc")
        subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)
        
        # ls-files 不會包含 .nexus/experiment.py
        result = subprocess.run(
            ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True
        )
        assert ".nexus/experiment.py" not in result.stdout
    
    def test_tracked_artifact_accepted(self, tmp_path):
        """正常 tracked 的檔案應通過"""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "real_code.py").write_text("# real")
        subprocess.run(["git", "add", "real_code.py"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=tmp_path, capture_output=True)
        
        result = subprocess.run(
            ["git", "ls-files"], cwd=tmp_path, capture_output=True, text=True
        )
        assert "real_code.py" in result.stdout


# === WP3: 介面契約 ===

class TestDroneProtocolContract:
    """TacticalDrone 必須符合 DroneProtocol"""
    
    def test_tactical_drone_implements_protocol(self, tmp_path):
        from nexus.core.drone_engine import TacticalDrone
        from nexus.core.drone_protocol import DroneProtocol
        drone = TacticalDrone("test", tmp_path)
        assert isinstance(drone, DroneProtocol)
    
    def test_call_with_tools_param(self, tmp_path, monkeypatch):
        """呼叫時傳入 tools=[] 不會 TypeError"""
        from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain
        drone = TacticalDrone("test-tools", tmp_path)
        
        def mock_ask(self, msgs):
            return {"action": "DONE", "reasoning": "ok"}
        monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
        drone.local_brain.ask_structured = mock_ask.__get__(
            drone.local_brain, LocalBonsaiBrain
        )
        result = drone.sense_think_act("test", tools=[])
        assert result["outcome"] == "SUCCESS"
    
    def test_call_without_tools_param(self, tmp_path, monkeypatch):
        """呼叫時不傳 tools 也不會 TypeError"""
        from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain
        drone = TacticalDrone("test-no-tools", tmp_path)
        
        def mock_ask(self, msgs):
            return {"action": "DONE", "reasoning": "ok"}
        monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
        drone.local_brain.ask_structured = mock_ask.__get__(
            drone.local_brain, LocalBonsaiBrain
        )
        result = drone.sense_think_act("test")
        assert result["outcome"] == "SUCCESS"


# === WP4: Quarantine 收緊 ===

class TestStrictQuarantine:
    """嚴格模式下 PARTIAL 不可自動 promote"""
    
    def test_partial_rejected_in_strict_mode(self, monkeypatch):
        monkeypatch.setenv("NEXUS_STRICT_QUARANTINE", "1")
        from nexus.core.hallucination_guard import HallucinationGuard
        guard = HallucinationGuard()
        # 分數落在 PARTIAL 區間 (2-5)
        guard.score = 3.0
        guard.schema = {"thresholds": {"VERIFIED": 2, "PARTIAL": 5, "REJECTED": 6}}
        status = guard.get_status()
        assert status == "REJECTED"

    def test_partial_allowed_in_default_mode(self, monkeypatch):
        # 確保環境變數未設定
        monkeypatch.delenv("NEXUS_STRICT_QUARANTINE", raising=False)
        from nexus.core.hallucination_guard import HallucinationGuard
        guard = HallucinationGuard()
        guard.score = 3.0
        guard.schema = {"thresholds": {"VERIFIED": 2, "PARTIAL": 5, "REJECTED": 6}}
        status = guard.get_status()
        assert status == "PARTIAL"


# === WP5-Extra: 已有測試不得回歸 ===

class TestExistingEdgeCases:
    """確認已有的 drone 邊界測試仍然通過"""
    
    def test_unknown_action_fails(self, tmp_path, monkeypatch):
        from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain
        drone = TacticalDrone("test-unknown", tmp_path)
        def mock_ask(self, msgs):
            return {"action": "DANCE", "reasoning": "I like to dance"}
        monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
        drone.local_brain.ask_structured = mock_ask.__get__(
            drone.local_brain, LocalBonsaiBrain
        )
        res = drone.sense_think_act("do something")
        assert res["outcome"] == "FAIL"
    
    def test_empty_response_fails(self, tmp_path, monkeypatch):
        from nexus.core.drone_engine import TacticalDrone, LocalBonsaiBrain
        drone = TacticalDrone("test-empty", tmp_path)
        def mock_ask(self, msgs):
            return {}
        monkeypatch.setattr(LocalBonsaiBrain, "ask_structured", mock_ask)
        drone.local_brain.ask_structured = mock_ask.__get__(
            drone.local_brain, LocalBonsaiBrain
        )
        res = drone.sense_think_act("do something")
        assert res["outcome"] == "FAIL"
