import pytest
import os
from pathlib import Path
from nexus.core.subagent_armor import SubAgentArmor, NakedRunError

def test_armor_naked_run_blocked():
    """核驗執行期：若無環境變數，分身必須死"""
    os.environ.pop("NEXUS_ENFORCED", None)
    armor = SubAgentArmor()
    with pytest.raises(NakedRunError, match="裸跑被攔截"):
        armor.activate("/tmp/fake_root")

def test_armor_worktree_isolation_failure(tmp_path):
    """核驗執行期：分身禁止在主工作空間運行"""
    main_root = tmp_path / "main"
    main_root.mkdir()
    
    os.environ["NEXUS_ENFORCED"] = "true"
    os.environ["NEXUS_WORKTREE"] = str(main_root)
    os.environ["NEXUS_SCOPE"] = '["test.py"]'
    
    armor = SubAgentArmor()
    with pytest.raises(PermissionError, match="物理隔離失敗"):
        armor.activate(str(main_root))

def test_armor_commit_blocked(tmp_path):
    """核驗執行期：分身禁止直接 commit"""
    main_root = tmp_path / "main"
    work_root = tmp_path / "work"
    main_root.mkdir()
    work_root.mkdir()
    
    os.environ["NEXUS_ENFORCED"] = "true"
    os.environ["NEXUS_WORKTREE"] = str(work_root)
    os.environ["NEXUS_SCOPE"] = '["test.py"]'
    
    armor = SubAgentArmor()
    armor.activate(str(main_root))
    
    with pytest.raises(PermissionError, match="分身禁止直接 Commit"):
        armor.commit_blocked()

def test_armor_scope_check(tmp_path):
    """核驗執行期：分身只能改白名單內容"""
    main_root = tmp_path / "main"
    work_root = tmp_path / "work"
    main_root.mkdir()
    work_root.mkdir()
    
    os.environ["NEXUS_ENFORCED"] = "true"
    os.environ["NEXUS_WORKTREE"] = str(work_root)
    os.environ["NEXUS_SCOPE"] = '["nexus/core/utils.py"]'
    
    armor = SubAgentArmor()
    armor.activate(str(main_root))
    
    assert armor.can_write("nexus/core/utils.py") == True
    assert armor.can_write("nexus/engine/coordinator.py") == False
