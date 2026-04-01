import os
import time
import subprocess
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

class SentinelReboot:
    """🛡️ [Wave 3] Sentinel Reboot: Persistence & Auto-Respawn"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.daemons = [
            ("hudson_daemon.py", "scripts/ops/hudson_daemon.py"),
            ("paperclip.py", "scripts/ops/paperclip.py"),
            ("daemon.py", "scripts/ops/daemon.py")
        ]

    def monitor_and_respawn(self):
        """監控守護進程並自動重啟崩潰節點內容內容及性能"""
        logger.info("🛡️ [Sentinel] Initiating daemon persistence audit...")
        
        while True:
            for name, path in self.daemons:
                if not self._is_running(name):
                    logger.warning(f"🛡️ [Sentinel] ALERT: {name} is DEAD. Respawning...")
                    self._respawn(path)
                else:
                    logger.info(f"🛡️ [Sentinel] {name} is ALIVE. 🟢")
            
            time.sleep(30)

    def _is_running(self, name: str) -> bool:
        # 🚀 行動 20: 檢測進程 (使用 pgrep 簡化檢查)
        try:
            output = subprocess.check_output(["pgrep", "-f", name])
            return len(output) > 0
        except subprocess.CalledProcessError:
            return False

    def _respawn(self, path: str):
        full_path = self.repo_root / path
        if full_path.exists():
            subprocess.Popen([sys.executable, str(full_path)])
            logger.info(f"🛡️ [Sentinel] Successfully respawned {path}.")

if __name__ == "__main__":
    sentinel = SentinelReboot(Path("."))
    sentinel.monitor_and_respawn()
