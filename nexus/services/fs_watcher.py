import os
import sys

# 🧬 Optional Dependency: watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    # Mock for initialization
    class FileSystemEventHandler: pass

class NexusFSWatcher(FileSystemEventHandler):
    """
    👁️ Nexus FS Watcher (v22 Swarm Services)
    功能：監控工作空間變動，識別 Dirty 檔案。
    受控啟動：選配依賴，支援無故障降級。
    """
    def __init__(self, path: str):
        self.path = path
        self.is_dirty = False
        self.dirty_files = set()
        self.observer = None
        
        if HAS_WATCHDOG:
            self.observer = Observer()

    def is_available(self) -> bool:
        """檢查 watchdog 是否可用"""
        return HAS_WATCHDOG

    def start(self):
        """啟動監聽"""
        if self.observer:
            self.observer.schedule(self, self.path, recursive=True)
            self.observer.start()
            print(f"👁️ [FSWatcher] Monitoring workspace: {self.path}")
        else:
            print("⚠️ [FSWatcher] watchdog not installed. Manual sync mode active.")

    def on_modified(self, event):
        """處理變動事件"""
        if not event.is_directory:
            filename = os.path.basename(event.src_path)
            # 排除隱藏檔案與 .git
            if not filename.startswith(".") and ".git" not in event.src_path:
                self.is_dirty = True
                self.dirty_files.add(filename)
                # print(f"📝 [FSWatcher] File modified: {filename}")

    def evict(self):
        """清除 Dirty 狀態 (Eviction)"""
        self.is_dirty = False
        self.dirty_files.clear()

    def stop(self):
        """停止監聽"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
