import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from nexus.infrastructure.storage_interfaces import MemoryStorage, CacheStore, BeliefStore, ConfigStore
from nexus.infrastructure.storage_implementations import LanceDBStorage, LocalCacheStore, LanceBeliefStore, FileConfigStore

logger = logging.getLogger(__name__)

class MemPalace:
    """🏰 Nexus v26.0 L1 Memory Palace & Ethical Firewall. (Refactored)"""
    
    def __init__(self, project_root: str = str(__import__("pathlib").Path(__file__).resolve().parents[2]), 
                 storage: MemoryStorage = None, 
                 cache: CacheStore = None,
                 belief_store: BeliefStore = None,
                 config_store: ConfigStore = None):
        self.project_root = Path(project_root)
        self.storage = storage or LanceDBStorage(self.project_root)
        self.cache = cache or LocalCacheStore()
        self.belief_store = belief_store or LanceBeliefStore(self.project_root)
        self.config_store = config_store or FileConfigStore(self.project_root)

    def ingest_to_shards(self, tenant_id: str, artifact_type: str, data: Dict[str, Any]):
        """🏛️ v25.5 Physical Sharding & AAAK 30x Compression."""
        return self.storage.store(tenant_id, artifact_type, data)

    def retrieve_from_shards(
        self,
        tenant_id: str,
        query: str,
        artifact_type: str | None = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Read memory through a tenant-bound storage handle only."""
        tenant = str(tenant_id or "").strip()
        if not tenant:
            return []
        try:
            scoped = self.storage.scoped_access(tenant)
            return scoped.retrieve(query, artifact_type=artifact_type, limit=limit)
        except Exception as e:
            logger.warning("🏰 [MemPalace] retrieve_from_shards failed: %s", e)
            return []

    def trigger_arweave_distillation(self, data: Dict[str, Any]) -> str:
        """SIMULATED Arweave permanence: nothing is uploaded.

        The returned id is a random placeholder prefixed ``SIMULATED-`` so it can
        never be mistaken for a real transaction.
        """
        mock_tx_id = f"SIMULATED-ARW-{os.urandom(8).hex()}"
        logger.info(f"[Arweave] SIMULATED distillation (NOT uploaded). Placeholder id: {mock_tx_id}")
        return mock_tx_id

    def sync(self) -> Dict[str, Any]:
        """🔄 SYNC: Sync memory with Arweave/Registry and refresh blacklist."""
        blacklist_path = self.project_root / "nexus/config/ethical_blacklist.json"
        blacklist = []
        blacklist_source = "missing"
        if blacklist_path.exists():
            try:
                with open(blacklist_path, 'r') as f:
                    blacklist = json.load(f).get("patterns", [])
                blacklist_source = "file"
            except Exception as e:
                blacklist_source = "unreadable"
                logger.error(f"❌ [MemPalace] Failed to load blacklist: {e}")
        else:
            logger.warning("⚠️ [MemPalace] Ethical blacklist file missing: %s", blacklist_path)

        self.cache.delete("nexus:ethical_blacklist")
        if blacklist:
            self.cache.sadd("nexus:ethical_blacklist", *blacklist)
        self._blacklist_synced = True
        return {
            "status": "SUCCESS",
            "synced_patterns": len(blacklist),
            "blacklist_source": blacklist_source,
        }

    def _active_blacklist(self) -> set:
        """Blacklist patterns, loading them from disk on first use in this process.

        The cache is in-process only, so verifying without a prior sync() would
        otherwise check against an empty blacklist even when the file exists.
        """
        patterns = self.cache.smembers("nexus:ethical_blacklist")
        if not patterns and not getattr(self, "_blacklist_synced", False):
            self.sync()
            patterns = self.cache.smembers("nexus:ethical_blacklist")
        return patterns

    def verify(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """🛡️ VERIFY: Filter candidates against ethical blacklist."""
        if not candidates: return []
        blacklist = self._active_blacklist()
        clean_candidates = []
        for cand in candidates:
            content = str(cand)
            if not any(pattern in content for pattern in blacklist):
                clean_candidates.append(cand)
        return clean_candidates

    def verify_context(self, context: str) -> Dict[str, Any]:
        """[TD-2] Quick contextual check against blacklist."""
        blacklist = self._active_blacklist()
        for pattern in blacklist:
            if pattern in context:
                return {"status": "BLOCKED", "reason": pattern}
        return {"status": "SUCCESS"}

    def audit_action(self, phase: str, action: str) -> bool:
        """執行規約審計 (Merged from core/mem_palace.py)."""
        if phase == "D" and "evidence" not in action.lower():
            return False
        return True

    def get_skill_constraints(self) -> Dict[str, Any]:
        """🛡️ 從活躍且高信任度的信念中提取技能約束規則 (v24.0 Hardened)。"""
        beliefs = self.list_beliefs(status="ACTIVE")
        constraints: Dict[str, Any] = {"require": [], "forbid": [], "prefer": []}
        # Make a failed belief read visible: empty constraints != "no constraints".
        store_status = getattr(self.belief_store, "last_read_status", "ok")
        if getattr(self, "_belief_read_failed", False) or store_status == "unavailable":
            constraints["constraints_source"] = "unavailable"
            constraints["constraints_unavailable_reason"] = (
                getattr(self, "_belief_read_error", "") or getattr(self.belief_store, "last_read_error", "") or "belief_store_unavailable"
            )
        else:
            constraints["constraints_source"] = "ok"
        now = datetime.now(timezone.utc)
        
        for b in beliefs:
            # 🧪 [Round 20] Entropy Filtering: Skip UNTRUSTED beliefs
            if b.get("trust_level") == "UNTRUSTED":
                logger.info(f"🛡️ [MemPalace] Ignoring high-entropy belief: {b.get('id')}")
                continue

            # 檢查 7 天 TTL (Time-To-Live)
            created_at_str = b.get("updated_at") or b.get("created_at")
            if created_at_str:
                try:
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
        self._belief_read_failed = False
        self._belief_read_error = ""
        try:
            return self.belief_store.list_beliefs(status=status)
        except Exception as e:
            self._belief_read_failed = True
            self._belief_read_error = f"{type(e).__name__}: {e}"
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
        try:
            return self.config_store.get_router_bias()
        except Exception as e:
            logger.warning(f"🕍 [MemPalace] get_router_bias failed: {e}")
            return None
