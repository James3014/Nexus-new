import pytest
import subprocess
from pathlib import Path
from nexus.core.session_persistence import SessionPersistence

def test_tmux_session_creation_and_check():
    """核驗 tmux 會話之物理具現化與隔離路徑"""
    sp = SessionPersistence(Path("/tmp/nexus-test"))
    shard_id = "test-shard-999"
    worktree_path = "/tmp/nexus-shard-999"
    Path(worktree_path).mkdir(parents=True, exist_ok=True)
    
    session_name = sp.create_persistent_session(shard_id, worktree_path)
    assert session_name == f"nexus-{shard_id}"
    
    # 核驗 tmux 系統中是否存在該 session
    res = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)
    assert res.returncode == 0
    
    # 測試後清理
    subprocess.run(["tmux", "kill-session", "-t", session_name])

def test_session_restore_command_generation():
    """核驗還原指令生成邏輯"""
    sp = SessionPersistence(Path("."))
    restore_cmd = sp.restore_session("nexus-shard-001")
    assert "tmux attach-session -t nexus-shard-001" in restore_cmd
