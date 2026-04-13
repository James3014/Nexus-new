import uuid
from pathlib import Path
import pytest
import subprocess
import shutil
from nexus.core.session_persistence import SessionPersistence

def test_tmux_session_creation_and_check():
    """核驗 tmux 會話之物理具現化與隔離路徑"""
    # 建立唯一 ID 避免與既存 session 衝突
    unique_id = str(uuid.uuid4())[:8]
    shard_id = f"test-shard-{unique_id}"
    session_name = f"nexus-{shard_id}"
    
    # 預防性清理（如果先前測試崩潰留下的殘餘）
    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)
    
    sp = SessionPersistence(Path("/tmp/nexus-test"))
    worktree_path = f"/tmp/nexus-shard-{unique_id}"
    Path(worktree_path).mkdir(parents=True, exist_ok=True)
    
    try:
        created_name = sp.create_persistent_session(shard_id, worktree_path)
        assert created_name == session_name
        
        # 核驗 tmux 系統中是否存在該 session
        res = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)
        assert res.returncode == 0
    finally:
        # 確保無論測試成功或失敗都會清理
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)
        if Path(worktree_path).exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

def test_session_restore_command_generation():
    """核驗還原指令生成邏輯"""
    sp = SessionPersistence(Path("."))
    restore_cmd = sp.restore_session("nexus-shard-001")
    assert "tmux attach-session -t nexus-shard-001" in restore_cmd
