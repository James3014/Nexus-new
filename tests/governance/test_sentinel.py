import pytest
import os
import time
from nexus.core.project_sentinel import ProjectSentinel

def test_sentinel_initial_snapshot(tmp_path):
    # 建立測試檔案
    p1 = tmp_path / "test1.py"
    p1.write_text("print('hello')")
    
    sentinel = ProjectSentinel(watch_paths=[str(tmp_path)], auto_heal=False)
    assert str(p1) in sentinel.last_mtime

def test_sentinel_detect_change(tmp_path):
    p1 = tmp_path / "test2.py"
    p1.write_text("v1")
    
    sentinel = ProjectSentinel(watch_paths=[str(tmp_path)], auto_heal=False)
    
    # 物理修改檔案
    time.sleep(0.1) # 確保 mtime 改變
    p1.write_text("v2")
    
    changes = sentinel._check_files()
    assert str(p1) in changes

def test_sentinel_no_change(tmp_path):
    p1 = tmp_path / "test3.py"
    p1.write_text("v1")
    
    sentinel = ProjectSentinel(watch_paths=[str(tmp_path)], auto_heal=False)
    
    changes = sentinel._check_files()
    assert len(changes) == 0
