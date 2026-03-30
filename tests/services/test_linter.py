import pytest
import subprocess
import shutil
from unittest.mock import MagicMock, patch
from nexus.services.linter import Linter

def test_linter_scan_empty():
    """驗證當無檔案時掃描應回傳空列表。"""
    linter = Linter()
    assert linter.scan([]) == []

def test_linter_scan_success():
    """驗證 Ruff 掃描流程（Mock Subprocess）。"""
    linter = Linter()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="[{\"message\": \"error\"}]")
        res = linter.scan(["test.py"])
        assert res == "[{\"message\": \"error\"}]"
        assert mock_run.called
        # 檢查指令是否包含 check
        args = mock_run.call_args_list[0][0][0]
        assert "check" in args

def test_linter_heal():
    """驗證 Ruff 自癒流程。"""
    linter = Linter()
    with patch("subprocess.run") as mock_run:
        linter.heal(["test.py"])
        # 應分別呼叫 ruff check --fix 與 ruff format
        assert mock_run.call_count >= 2
        args1 = mock_run.call_args_list[0][0][0]
        assert "--fix" in args1
        args2 = mock_run.call_args_list[1][0][0]
        assert "format" in args2
