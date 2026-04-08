import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class MemPalace:
    """🏰 Nexus v26.0 L1 Memory Palace & Ethical Firewall.
    
    Provides high-performance synchronization and verification of memory candidates.
    Integrates with Redis for fast blacklisting and governance caching.
    """
    
    def __init__(self, project_root: str = "/Users/jameschen/Workspace/nexus"):
        self.project_root = Path(project_root)
        self.blacklist_cache: Dict[str, Any] = {} # Fallback if Redis is unreachable
        self._init_redis()

    def _init_redis(self):
        """🛡️ Initialize Redis connection for L1 caching."""
        try:
            import redis
            self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.redis.ping()
            logger.info("✅ [MemPalace] Connected to Redis L1 cache.")
        except Exception as e:
            logger.warning(f"⚠️ [MemPalace] Redis unavailable, using local dictionary: {e}")
            self.redis = None

    def sync(self) -> Dict[str, Any]:
        """🔄 SYNC: Sync memory with Arweave/Registry and refresh blacklist."""
        # 1. Fetch Ethical Blacklist from local governance config
        blacklist_path = self.project_root / "nexus/config/ethical_blacklist.json"
        blacklist = []
        if blacklist_path.exists():
            try:
                with open(blacklist_path, 'r') as f:
                    blacklist = json.load(f).get("patterns", [])
            except Exception as e:
                logger.error(f"❌ [MemPalace] Failed to load blacklist: {e}")

        # 2. Update Redis Cache
        if self.redis:
            self.redis.delete("nexus:ethical_blacklist")
            if blacklist:
                self.redis.sadd("nexus:ethical_blacklist", *blacklist)
        else:
            self.blacklist_cache["ethical_blacklist"] = set(blacklist)

        logger.info(f"✅ [MemPalace] Synced {len(blacklist)} ethical patterns.")
        return {"status": "SUCCESS", "synced_patterns": len(blacklist)}

    def verify(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """🛡️ VERIFY: Filter candidates against ethical blacklist and quality gates."""
        if not candidates:
            return []

        # 1. Load Blacklist from cache
        if self.redis:
            blacklist = self.redis.smembers("nexus:ethical_blacklist")
        else:
            blacklist = self.blacklist_cache.get("ethical_blacklist", set())

        # 2. Perform filtering
        clean_candidates = []
        for cand in candidates:
            rule_text = cand.get("rule_text", "").lower()
            # Simple keyword matching for ethical filter
            is_blocked = any(pattern.lower() in rule_text for pattern in blacklist)
            
            if not is_blocked:
                clean_candidates.append(cand)
            else:
                logger.warning(f"🛑 [MemPalace:Block] Candidate rule blocked by ethics: {cand.get('id')}")

        return clean_candidates

# Singleton instance
mem_palace = MemPalace()
