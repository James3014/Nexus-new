import time
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

class NexusDaemon:
    """🛡️ [Wave 2] Nexus Daemon: 7x24 Self-Healing & Baseline Lock"""
    
    def __init__(self, project_root: Path, aos_target: float = 155.0):
        self.project_root = project_root
        self.aos_target = aos_target
        self.state_file = project_root / ".nexus" / "metrics" / "latest_state.json"

    def run_forever(self):
        """啟動自癒循環內容內容內容及性能內容內容內容"""
        logger.info(f"🛡️ [Daemon] 7x24 Monitor active. (Target AOS: {self.aos_target})")
        
        while True:
            current_aos = self._get_current_aos()
            if current_aos < self.aos_target:
                logger.warning(f"🛡️ [Daemon] AOS Alert: {current_aos} < {self.aos_target}. Initiating SELF-HEAL...")
                self._self_heal()
            
            time.sleep(60)

    def _get_current_aos(self) -> float:
        if not self.state_file.exists(): return 0.0
        try:
            with open(self.state_file, "r") as f:
                return json.load(f).get("aos_score", 0.0)
        except: return 0.0

    def _self_heal(self):
        # 🚀 行動 13: 自動觸發驗收與修復序列
        subprocess.run([sys.executable, "scripts/engine/nexus_cli.py", "nexus:acceptance-check"])
        logger.info("🛡️ [Daemon] Self-healing sequence triggered.")

if __name__ == "__main__":
    daemon = NexusDaemon(Path("."))
    daemon.run_forever()
