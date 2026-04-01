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
        logger.info("🛡️ [Sentinel] Initiating daemon persistence audit (Pulse Mode)...")
        lock_path = self.repo_root / ".nexus" / "maintenance.lock"
        
        while True:
            # 🧪 [Hardening] 維護鎖檢查：若開發者正在操作，暫停自癒檢查以釋放 IO
            if lock_path.exists():
                logger.info("🛡️ [Sentinel] Maintenance lock DETECTED. Pausing audit...")
                time.sleep(15)
                continue
                
            for name, path in self.daemons:
                if not self._is_running(name):
                    logger.warning(f"🛡️ [Sentinel] ALERT: {name} is DEAD. Respawning...")
                    self._respawn(path)
                else:
                    logger.info(f"🛡️ [Sentinel] {name} is ALIVE. 🟢")
            
            # 🧪 [Pulse Mode] 降低更新頻率至 60s (原 30s)
            time.sleep(60)

    def _is_running(self, name: str) -> bool:
        # 🚀 行動 20: 檢測進程 (使用 pgrep 簡化檢查)
        try:
            # 排除 grep 與 sentinel 本身指令內容內容及性能分析內容
            output = subprocess.check_output(["pgrep", "-f", name])
            pids = output.decode().strip().split("\n")
            # 排除當前進程 PID
            my_pid = str(os.getpid())
            active_pids = [p for p in pids if p != my_pid]
            return len(active_pids) > 0
        except subprocess.CalledProcessError:
            return False

    def _respawn(self, path: str):
        full_path = self.repo_root / path
        logger.info(f"🛡️ [Sentinel] Attempting respawn: {full_path}")
        if full_path.exists():
            subprocess.Popen([sys.executable, str(full_path)], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
            logger.info(f"🛡️ [Sentinel] Successfully respawned {path}.")
        else:
            logger.error(f"🛡️ [Sentinel] FILE NOT FOUND: {full_path}")

if __name__ == "__main__":
    # 使用絕對路徑
    root = Path(__file__).resolve().parents[2]
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(root / ".nexus/metrics/sentinel.log"),
            logging.StreamHandler()
        ]
    )
    sentinel = SentinelReboot(root)
    sentinel.monitor_and_respawn()
