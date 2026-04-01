import pytest
from unittest.mock import MagicMock, patch
from nexus.services.fs_watcher import NexusFSWatcher

def test_watcher_optional_dependency_graceful_fail():
    # 模擬 watchdog 未安裝的情境
    with patch.dict("sys.modules", {"watchdog": None, "watchdog.observers": None, "watchdog.events": None}):
        watcher = NexusFSWatcher(path=".")
        # 不應拋出異常，但應標記為不可用
        assert watcher.is_available() is False
        watcher.start() # 不應崩潰

def test_watcher_dirty_signal():
    # 模擬 watchdog 已安裝
    mock_observer = MagicMock()
    with patch("nexus.services.fs_watcher.Observer", return_value=mock_observer):
        watcher = NexusFSWatcher(path=".")
        assert watcher.is_dirty is False
        
        # 模擬檔案變動事件
        watcher.on_modified(MagicMock(src_path="test.py", is_directory=False))
        
        assert watcher.is_dirty is True
        assert "test.py" in watcher.dirty_files

def test_watcher_eviction():
    watcher = NexusFSWatcher(path=".")
    watcher.is_dirty = True
    watcher.dirty_files.add("old.py")
    
    # 執行 Eviction (清除 Dirty 標記)
    watcher.evict()
    
    assert watcher.is_dirty is False
    assert len(watcher.dirty_files) == 0
