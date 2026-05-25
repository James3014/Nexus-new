import json
import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from nexus.core.mission_contracts import NexusMission, MissionStatus
from scripts.engine.nexus_cli import nexus

def test_mission_model_serialization(tmp_path: Path) -> None:
    mission = NexusMission(
        mission_id="MSN-TEST",
        objective="Hardening SRE logic",
        status=MissionStatus.DRAFT,
        constraints=["use_wal"]
    )
    mission.persist(tmp_path)
    
    loaded = NexusMission.load(tmp_path)
    assert loaded is not None
    assert loaded.mission_id == "MSN-TEST"
    assert loaded.objective == "Hardening SRE logic"
    assert loaded.status == MissionStatus.DRAFT
    assert loaded.constraints == ["use_wal"]

def test_mission_budget_violation() -> None:
    mission = NexusMission(
        mission_id="MSN-TEST",
        objective="Run",
        budget={"max_tokens": 100.0, "max_wall_time_sec": 10.0, "max_retries": 3.0},
        accumulated_usage={"tokens": 10.0, "wall_time_sec": 2.0, "retries": 0.0}
    )
    # 預算內，應該 PASS
    assert mission.check_telemetry_budget() is True

    # 故意讓 tokens 累積超出預算
    mission.accumulated_usage["tokens"] = 120.0
    assert mission.check_telemetry_budget() is False

def test_mission_fingerprint_mismatch(tmp_path: Path) -> None:
    mission = NexusMission(
        mission_id="MSN-TEST",
        objective="Verify Git SHA alignment",
        git_fingerprint="A1B2C3D4"
    )
    
    # 模擬當前 Git HEAD SHA 為 "FFFFFFFF" (不匹配)
    with patch("subprocess.check_output", return_value=b"FFFFFFFF\n"):
        res = mission.run_fingerprint_preflight(tmp_path)
        assert res is False
        assert mission.status == MissionStatus.BLOCKED
        
        # 載入確認狀態已持久化為 BLOCKED
        loaded = NexusMission.load(tmp_path)
        assert loaded.status == MissionStatus.BLOCKED

def test_mission_cli_workflow(tmp_path: Path) -> None:
    runner = CliRunner()
    
    # 使用 patch 將 repo_root 與 REPO_ROOT 全域變數 mock 掉指向我們的 tmp_path 
    with patch("scripts.engine.nexus_cli.repo_root", tmp_path), \
         patch("scripts.engine.nexus_cli.REPO_ROOT", tmp_path):
        
        # 1. 建立戰役
        res = runner.invoke(nexus, ["nexus", "mission", "create", "Fixing memory leaks"])
        assert res.exit_code == 0
        assert "Successfully created mission" in res.output
        
        # 2. 檢視狀態
        res = runner.invoke(nexus, ["nexus", "mission", "status"])
        assert res.exit_code == 0
        assert "Fixing memory leaks" in res.output
        assert "draft" in res.output

        # 3. 暫停戰役
        res = runner.invoke(nexus, ["nexus", "mission", "pause"])
        assert res.exit_code == 0
        assert "paused" in res.output

        # 4. 恢復與執行
        # 模擬 _run_git 或是 Git HEAD SHA 獲取以順利通過 preflight，並 mock run 子進程
        with patch("subprocess.check_output", return_value=b"A1B2C3D4\n"), \
             patch("subprocess.run") as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0)
            res = runner.invoke(nexus, ["nexus", "mission", "resume"])
            assert res.exit_code == 0
            assert "Resuming mission" in res.output
