import pytest
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch
from nexus.services.patcher import SafePatcher

@pytest.fixture
def patcher(tmp_path):
    """準備測試用的 SafePatcher 環境。"""
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()
    return SafePatcher(lock_dir, project_root)

def test_patcher_apply_incorrect_target(patcher):
    """驗證當補丁目標檔案不匹配時應跳過。"""
    violations = [{"file": "main.py", "patch": "+++ b/wrong.py\n+new line"}]
    assert patcher.apply(violations) is False

def test_patcher_apply_git_success(patcher):
    """驗證 Git Apply 成功套用補丁的流程。"""
    violations = [{"file": "main.py", "patch": "+++ b/main.py\n+new line"}]
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert patcher.apply(violations) is True
        assert mock_run.called
        # 檢查指令
        args = mock_run.call_args_list[0][0][0]
        assert "git" in args
        assert "apply" in args

def test_patcher_apply_direct_fallback(patcher, tmp_path):
    """驗證當 Git Apply 失敗時，應回退到直接文件寫入。"""
    project_root = patcher.project_root
    file_path = project_root / "main.py"
    file_path.write_text("old line")
    
    violations = [{"file": "main.py", "patch": "+++ b/main.py\n+new line"}]
    with patch("subprocess.run") as mock_run:
        # 模擬 git apply 失敗
        mock_run.return_value = MagicMock(returncode=1)
        assert patcher.apply(violations) is True
        # 檢查是否直接寫入檔案
        content = file_path.read_text()
        assert "old line" in content
        assert "new line" in content
