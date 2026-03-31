import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("nexus.federation")

class FederationLayer:
    """
    🛰️ Nexus 聯邦層 (v0.2)
    職責: 節點管理、Quorum 演算與負載分發。
    對齊 Phase 3 Swarm Expansion 100-Point Spec。
    """

    def __init__(self, project_root: str | Path, registry_path: str = ".nexus/federation/node_registry.json"):
        self.project_root = Path(project_root)
        self.registry_file = self.project_root / registry_path
        self.nodes: List[Dict] = []
        self.last_sync = 0
        self.load_registry()

    def load_registry(self) -> bool:
        """從物理存儲加載節點註冊表。"""
        if not self.registry_file.exists():
            logger.warning(f"⚠️ Registry not found at {self.registry_file}. Initializing empty.")
            self.nodes = []
            return False
        
        try:
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                self.nodes = json.load(f)
            self.last_sync = time.time()
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"❌ Failed to load registry: {e}")
            self.nodes = []
            return False

    def quorum_check(self, threshold: float = 2/3) -> bool:
        """
        ⚖️ Quorum 2/3 演算法。
        若存活節點少於 2/3，視為「裂腦 (Split-Brain)」風險，建議 Fail-closed。
        """
        if not self.nodes:
            return False
            
        alive_nodes = [n for n in self.nodes if n.get("status") == "ONLINE"]
        ratio = len(alive_nodes) / len(self.nodes)
        
        is_stable = ratio >= threshold
        if not is_stable:
            logger.critical(f"🛑 Quorum Fail: {len(alive_nodes)}/{len(self.nodes)} alive (Ratio: {ratio:.2f} < {threshold:.2f})")
        return is_stable

    def select_node(self, capability: str = "rust-reflex") -> Optional[str]:
        """
        🎯 負載分發選擇。
        目前採 Round Robin 或最少負載 (需 Manager 數據分享)。
        """
        candidates = [
            n for n in self.nodes 
            if n.get("status") == "ONLINE" and capability in n.get("capabilities", [])
        ]
        
        if not candidates:
            return None
            
        # 簡單選擇第一個可用節點 (後續可優化為加權隨機或負載均衡)
        return candidates[0]["node_id"]

    def register_node(self, node_id: str, capabilities: List[str], region: str = "unknown"):
        """手動註冊節點 (通常由 Manager 寫入，此處保留 API)。"""
        new_node = {
            "node_id": node_id,
            "status": "ONLINE",
            "capabilities": capabilities,
            "region": region,
            "last_heartbeat": int(time.time())
        }
        
        # Upsert logic
        existing = next((n for n in self.nodes if n["node_id"] == node_id), None)
        if existing:
            existing.update(new_node)
        else:
            self.nodes.append(new_node)
        
        self.save_registry()

    def save_registry(self):
        """將節點狀態持久化。"""
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, 'w', encoding='utf-8') as f:
            json.dump(self.nodes, f, indent=2)

if __name__ == "__main__":
    # Sandbox Test
    fed = FederationLayer(".")
    fed.register_node("node-1", ["rust-reflex", "gpu-eval"])
    print(f"Quorum 1/1: {fed.quorum_check()}")
