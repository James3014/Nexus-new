import pytest
import os
from pathlib import Path
from nexus.research.experiment_scheduler import ExperimentScheduler
from nexus.research.selector_rollback import SelectorRollback

def test_scheduler_strict_semantic_containment(tmp_path):
    # 建立一個具有誘導性名稱的目錄
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    attack_dir = tmp_path / "workspace_attack"
    attack_dir.mkdir()
    
    scheduler = ExperimentScheduler(workspace)
    scheduler.create_candidate("v1", "test", ["src/"])
    
    # 1. 正常路徑
    assert scheduler.validate_write("v1", "src/logic.py") is True
    
    # 2. 前綴繞過攻擊 (字串 startswith 會失效，is_relative_to 應成功阻斷)
    # 模擬試圖寫入 workspace_attack 目錄
    attack_path = str(attack_dir / "payload.py")
    assert scheduler.validate_write("v1", attack_path) is False

def test_rollback_prefix_attack(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    attack_ws = tmp_path / "ws_attack"
    attack_ws.mkdir()
    
    selector = SelectorRollback(workspace)
    
    # 試圖備份外部誘導路徑
    # 核驗 _safe_resolve 是否能看穿前綴相似性
    assert selector._safe_resolve("../ws_attack/conf.py") is None
    assert selector._safe_resolve("src/../../ws_attack/conf.py") is None

def test_real_promotion_semantic_safety(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    
    candidate_root = tmp_path / "candidate"
    candidate_root.mkdir()
    
    selector = SelectorRollback(workspace)
    # 惡意路徑試圖在 promote 時寫入外部
    # 即使 scope 裡面寫了誘導路徑
    success = selector.promote_candidate("c1", candidate_root, ["../outside.txt"])
    assert success is False
