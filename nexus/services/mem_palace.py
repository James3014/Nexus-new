import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from nexus.infrastructure.storage_interfaces import MemoryStorage, CacheStore
from nexus.infrastructure.storage_implementations import LanceDBStorage, LocalCacheStore

logger = logging.getLogger(__name__)

class MemPalace:
    """🏰 Nexus v26.0 L1 Memory Palace & Ethical Firewall. (Refactored)"""
    
    def __init__(self, project_root: str = str(__import__("pathlib").Path(__file__).resolve().parents[2]), 
                 storage: MemoryStorage = None, 
                 cache: CacheStore = None):
        self.project_root = Path(project_root)
        self.storage = storage or LanceDBStorage(self.project_root)
        self.cache = cache or LocalCacheStore()

    def ingest_to_shards(self, tenant_id: str, artifact_type: str, data: Dict[str, Any]):
        """🏛️ v25.5 Physical Sharding & AAAK 30x Compression."""
        return self.storage.store(tenant_id, artifact_type, data)

    def trigger_arweave_distillation(self, data: Dict[str, Any]) -> str:
        """🔄 v25.5 Infinite Context Loop: 模擬 Arweave 永久化。"""
        mock_tx_id = f"ARW-{os.urandom(8).hex()}"
        logger.info(f"🌐 [Arweave] Distillation Complete. TX: {mock_tx_id}")
        return mock_tx_id

    def sync(self) -> Dict[str, Any]:
        """🔄 SYNC: Sync memory with Arweave/Registry and refresh blacklist."""
        blacklist_path = self.project_root / "nexus/config/ethical_blacklist.json"
        blacklist = []
        if blacklist_path.exists():
            try:
                with open(blacklist_path, 'r') as f:
                    blacklist = json.load(f).get("patterns", [])
            except Exception as e:
                logger.error(f"❌ [MemPalace] Failed to load blacklist: {e}")

        self.cache.delete("nexus:ethical_blacklist")
        if blacklist:
            self.cache.sadd("nexus:ethical_blacklist", *blacklist)
        return {"status": "SUCCESS", "synced_patterns": len(blacklist)}

    def verify(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """🛡️ VERIFY: Filter candidates against ethical blacklist."""
        if not candidates: return []
        blacklist = self.cache.smembers("nexus:ethical_blacklist")
        clean_candidates = []
        for cand in candidates:
            content = str(cand)
            if not any(pattern in content for pattern in blacklist):
                clean_candidates.append(cand)
        return clean_candidates

    def get_skill_constraints(self) -> Dict[str, Any]:
        """🛡️ 從活躍信念中提取技能約束規則（包含 7 天 TTL 控制）。"""
        beliefs = self.list_beliefs(status="ACTIVE")
        constraints = {"require": [], "forbid": [], "prefer": []}
        now = datetime.now(timezone.utc)
        for b in beliefs:
            # 檢查 7 天 TTL (Time-To-Live)
            created_at_str = b.get("updated_at") or b.get("created_at")
            if created_at_str:
                try:
                    # Parse timestamp, default to skipping if older than 7 days
                    created_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if (now - created_time).days > 7:
                        continue
                except (ValueError, TypeError):
                    pass
                    
            content = str(b.get("content", "")).lower()
            if "禁止" in content or "forbid" in content:
                constraints["forbid"].append(content)
            if "優先" in content or "prefer" in content:
                constraints["prefer"].append(content)
            if "必須" in content or "require" in content:
                constraints["require"].append(content)
        return constraints

    def list_beliefs(self, status: str = "ACTIVE") -> List[Dict[str, Any]]:
        """🕍 列出指定狀態的所有信念節點。"""
        try:
            import lancedb
            db_path = self.project_root / ".nexus" / "vector_db"
            if not db_path.exists(): return []
            db = lancedb.connect(str(db_path))
            res = db.list_tables()
            tables = res if isinstance(res, list) else (res.tables if hasattr(res, "tables") else res)
            if "nexus_soul_palace" not in tables:
                return []
            table = db.open_table("nexus_soul_palace")
            df = table.to_pandas()
            if status != "ALL" and "status" in df.columns:
                df = df[df["status"].str.upper() == status.upper()]
            return df.to_dict("records")
        except Exception as e:
            logger.warning(f"🕍 [MemPalace] list_beliefs failed: {e}")
            return []

    def get_belief(self, belief_id: str) -> Optional[Dict[str, Any]]:
        """🕍 取得單一信念的完整記錄。"""
        # ID 精確匹配或關鍵字模糊匹配
        beliefs = self.list_beliefs(status="ALL")
        for b in beliefs:
            if b.get("id") == belief_id or belief_id in str(b.get("content", "")):
                return b
        return None

    def get_router_bias(self) -> Optional[List[float]]:
        """🕍 取得最新的 v0.9 FedAvg global_router_bias。"""
        dna_path = self.project_root / "configs" / "federated_dna.yaml"
        if not dna_path.exists():
            return None
        try:
            import yaml
            with open(dna_path, "r") as f:
                dna = yaml.safe_load(f)
            return dna.get("global_router_bias")
        except Exception as e:
            logger.warning(f"🕍 [MemPalace] get_router_bias failed: {e}")
            return None
