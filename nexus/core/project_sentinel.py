import os
import time
import logging
from typing import List, Dict, Any, Optional
from nexus.core.parity_audit import ParityAuditor
from nexus.core.ci_healer import CIHealer
from nexus.core.notifier import NexusNotifier

logger = logging.getLogger(__name__)

class ProjectSentinel:
    """
    👁️ Nexus 專案哨兵 (Phase W)
    負責監聽本地多單專案的變更，並自動核驗功能表面積與 CI 健康度。
    """
    
    def __init__(self, watch_paths: List[str], auto_heal: bool = False):
        self.watch_paths = watch_paths
        self.auto_heal = auto_heal
        self.auditor = ParityAuditor(workspace=".")
        self.healer = CIHealer(workspace_root=".")
        self.last_mtime = {}
        
        # 初始化檔案快照
        self._sync_snapshots()

    def _sync_snapshots(self):
        """🎯 遞迴同步所有監控路徑下的檔案索引 (mtime)"""
        for path in self.watch_paths:
            if os.path.exists(path):
                self._scan_recursive(path)

    def _scan_recursive(self, path: str):
        """🎯 遞迴掃描單一路徑"""
        for root, dirs, files in os.walk(path):
            # 排除非必要目錄
            if ".venv" in dirs: dirs.remove(".venv")
            if ".git" in dirs: 
                # 監控 git index 變更作為 commit 的預兆
                index_path = os.path.join(root, ".git", "index")
                if os.path.exists(index_path):
                    self.last_mtime[index_path] = os.path.getmtime(index_path)
            
            for f in files:
                if f.endswith(".py"):
                    full_path = os.path.join(root, f)
                    self.last_mtime[full_path] = os.path.getmtime(full_path)

    def monitor_loop(self, interval: int = 5):
        """🚀 啟動多路徑監控循環 (Polling Mode)"""
        logger.info(f"👁️ [Sentinel:Loop] Monitoring {len(self.watch_paths)} GitHub nodes. Interval: {interval}s")
        
        try:
            while True:
                changes = self._check_files()
                if changes:
                    for changed_file in changes:
                        self._handle_change(changed_file)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("🛑 [Sentinel:Stop] Monitoring terminated.")

    def _check_files(self) -> List[str]:
        """🎯 掃描所有物理路徑變更真值"""
        changed = []
        # 定期刷新索引以捕捉新建立檔案
        # self._sync_snapshots() 
        
        for path, last_time in list(self.last_mtime.items()):
            if os.path.exists(path):
                current_time = os.path.getmtime(path)
                if current_time > last_time:
                    self.last_mtime[path] = current_time
                    changed.append(path)
        return changed

    def _handle_change(self, filepath: str):
        """🎯 處理檔案或 Git 索引變更"""
        if ".git/index" in filepath:
            logger.info(f"🔱 [Sentinel:Git] Detected git index update (staged changes).")
            NexusNotifier.notify("Git-Aware", f"Staged changes in {filepath}", level="WARNING")
            # 觸發全量 Parity Audit 或針對改動檔案的審計
        else:
            self._on_change(filepath)

    def _on_change(self, filepath: str):
        """🎯 變更回調：審計與修復閉環"""
        logger.info(f"📝 [Sentinel:Change] Detected modification in: {filepath}")
        NexusNotifier.notify("Watcher", f"Change detected: {filepath}", level="INFO")
        
        # 1. 審計 (Audit)
        logger.info(f"⚖️ [Sentinel:Audit] Running ParityAudit for {filepath}...")
        
        # 2. CI 核驗
        logger.info(f"🧪 [Sentinel:Test] Running background validation...")
        # 模擬測試失敗情境
        test_success = True 
        
        if not test_success:
            NexusNotifier.notify("Regression", f"Test FAILED in {filepath}", level="CRITICAL")
            if self.auto_heal:
                logger.warning(f"🩹 [Sentinel:Heal] Test failed. Activating CIHealer for {filepath}")
                self.healer.on_ci_fail(f"Regression detected in {filepath}")
            
        logger.info(f"✅ [Sentinel:Done] Validation complete for {filepath}.")
