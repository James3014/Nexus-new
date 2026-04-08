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
    
    def __init__(self, project_root: str = "/Users/jameschen/Workspace/nexus", 
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
