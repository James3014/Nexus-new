import json
import time
import os
import logging
from pathlib import Path

# 🛡️ Nexus 治理與合約
PROJECT_ROOT = Path("/Users/jameschen/Workspace/nexus")
REGISTRY_PATH = PROJECT_ROOT / ".nexus/federation/node_registry.json"
FAILSAFE_PATH = PROJECT_ROOT / ".nexus/federation/failsafe_mode.txt"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [DrClaw] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class DrClaw:
    """
    🦖 DrClaw: Split-Brain Detector & MTTR Guardian
    負責聯邦層的穩定性監控與自動降級邏輯 (Fail-closed)。
    """
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.quorum_threshold = 2/3
        self.max_latency_s = 30

    def check_health(self) -> bool:
        """執行 Quorum 與節點存活檢查"""
        if not REGISTRY_PATH.exists():
            logger.error("❌ Registry not found at %s", REGISTRY_PATH)
            return False

        try:
            with open(REGISTRY_PATH, "r") as f:
                nodes = json.load(f)
            
            total_nodes = len(nodes)
            online_nodes = [n for n in nodes if n.get("status") == "ONLINE"]
            online_count = len(online_nodes)
            
            # Quorum 演算法
            if total_nodes == 0:
                return False
                
            ratio = online_count / total_nodes
            logger.info("📊 Quorum Check: %d/%d (%.2f%%)", online_count, total_nodes, ratio * 100)
            
            if ratio < self.quorum_threshold:
                logger.warning("🚨 [DrClaw] QUORUM BREACH! %.2f < %.2f", ratio, self.quorum_threshold)
                return False
            
            # 檢查 Heartbeat Latency (Mock Check)
            now = int(time.time())
            for n in online_nodes:
                last = n.get("last_heartbeat", 0)
                if now - last > self.max_latency_s:
                     logger.warning("⚠️ Node %s is stalling (latency: %ds)", n['node_id'], now - last)
                     # 暫不視為斷線，待 P3.3 強化
            
            return True

        except Exception as e:
            logger.error("❌ Error reading registry: %s", e)
            return False

    def enforce_policy(self, healthy: bool):
        """根據健康度強制降級或恢復"""
        if not healthy:
            if not FAILSAFE_PATH.exists():
                logger.critical("🚨 [DrClaw] INITIATING FAIL-CLOSED TO LOCAL HARDENED MODE")
                with open(FAILSAFE_PATH, "w") as f:
                    f.write("FALLBACK_LOCAL")
        else:
            if FAILSAFE_PATH.exists():
                logger.info("✅ [DrClaw] System recovered. Removing failsafe lock.")
                FAILSAFE_PATH.unlink()

    def run_forever(self):
        """主循環"""
        logger.info("🦖 DrClaw MTTR Guardian v0.2 Activated. Monitoring Swarm consensus...")
        try:
            while True:
                healthy = self.check_health()
                self.enforce_policy(healthy)
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("🛑 DrClaw shutting down.")

if __name__ == "__main__":
    detector = DrClaw()
    detector.run_forever()
