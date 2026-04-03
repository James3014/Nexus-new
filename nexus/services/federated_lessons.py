"""
P1-E2: Federated Lessons Sync
Tailscale P2P + Arweave Fallback 的雙軌經驗池。
支援 Provenance Envelope 與 治理門禁。
"""

import asyncio
import aiohttp
import json
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta

from nexus.services.arweave_uploader import download_lessons_from_arweave
from nexus.services.continuous_learning import load_jsonl, utc_now_iso


@dataclass
class FederatedPeer:
    name: str
    source_type: str  # "p2p" / "arweave"
    locator: str
    trust_tier: str   # "peer" / "eternal"
    enabled: bool = True


def load_federated_peers(repo_root: Path) -> List[FederatedPeer]:
    peers_path = repo_root / ".nexus" / "learning" / "federated_peers.json"
    if not peers_path.exists():
        return []
    try:
        config = json.loads(peers_path.read_text())
        return [FederatedPeer(**p) for p in config.get("peers", []) if p.get("enabled")]
    except Exception:
        return []


async def fetch_remote_lessons(session: aiohttp.ClientSession, source: str) -> List[Dict[str, Any]]:
    """從 Tailscale 或 Arweave 拉 lessons"""
    if source.startswith("arweave://"):
        tx_id = source.replace("arweave://", "")
        return await download_lessons_from_arweave(tx_id)
    
    # Tailscale P2P (Assume the locator is the raw URL to the peer's JSONL)
    try:
        async with session.get(source, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            content = await resp.text()
            return [json.loads(line) for line in content.splitlines() if line.strip()]
    except Exception:
        return []


def validate_and_filter_lessons(
    lessons: List[Dict[str, Any]], 
    min_confidence: float = 0.7, 
    max_age_days: int = 30
) -> List[Dict[str, Any]]:
    """品質過濾 + 治理門禁 (Schema + Integrity)"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    valid = []
    
    REQUIRED_FIELDS = ["lesson_id", "task_id", "category", "root_cause", "corrective_action", "confidence", "schema_version"]
    
    for lesson in lessons:
        try:
            # 1. Schema check
            if lesson.get("schema_version") != "lesson_event.v1":
                continue
            
            # 2. Integrity check
            if not all(field in lesson for field in REQUIRED_FIELDS):
                continue
                
            # 3. Quality threshold
            if lesson.get("confidence", 0) < min_confidence:
                continue
            
            # 4. Success outcome only
            if lesson.get("outcome") == "failure":
                continue
                
            # 5. Recency
            ts_str = lesson["timestamp_utc"].replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_str)
            if ts < cutoff:
                continue
                
            valid.append(lesson)
        except (ValueError, KeyError, TypeError):
            continue
            
    return valid


def wrap_envelope(lesson: Dict[str, Any], peer: FederatedPeer) -> Dict[str, Any]:
    """將 lesson event 封裝於 Federated Cache Envelope"""
    # cache_id = sha256(peer_name + lesson_id) 確保同來源去重
    source_key = f"{peer.name}:{lesson['lesson_id']}"
    cache_id = hashlib.sha256(source_key.encode()).hexdigest()
    
    return {
        "cache_id": cache_id,
        "lesson": lesson,
        "source_type": peer.source_type,
        "source_repo": peer.name,
        "source_locator": peer.locator,
        "trust_tier": peer.trust_tier,
        "fetched_at_utc": utc_now_iso(),
        "local_weight": 0.85 if peer.trust_tier == "peer" else 0.80,
        "contract_version": "v22"
    }


def write_jsonl(path: Path, data: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


async def sync_federated_lessons(
    repo_root: Path,
    min_confidence: float = 0.7,
    max_age_days: int = 30,
    max_cache_entries: int = 500,
) -> Dict[str, Any]:
    """主同步服務邏輯"""
    peers = load_federated_peers(repo_root)
    cache_path = repo_root / ".nexus" / "learning" / "shared_lessons.jsonl"
    
    # 讀取現有快取 (by cache_id for deduplication)
    current_cache = {l["cache_id"]: l for l in load_jsonl(cache_path)}
    newly_fetched = 0
    
    async with aiohttp.ClientSession() as session:
        for peer in peers:
            print(f"🔄 [Federated] Syncing {peer.name} ({peer.source_type})...")
            remote_lessons = await fetch_remote_lessons(session, peer.locator)
            validated = validate_and_filter_lessons(remote_lessons, min_confidence, max_age_days)
            
            for lesson in validated:
                envelope = wrap_envelope(lesson, peer)
                if envelope["cache_id"] not in current_cache:
                    newly_fetched += 1
                current_cache[envelope["cache_id"]] = envelope
    
    # 按信譽與新舊排序並截斷
    # 優先保留: 高 confidence -> 新 fetched_at
    sorted_cache = list(current_cache.values())
    sorted_cache.sort(
        key=lambda x: (x["lesson"].get("confidence", 0), x["fetched_at_utc"]),
        reverse=True
    )
    
    final_cache = sorted_cache[:max_cache_entries]
    write_jsonl(cache_path, final_cache)
    
    return {
        "status": "completed",
        "new_lessons": newly_fetched,
        "total_cache": len(final_cache),
        "peers_attempted": len(peers),
        "max_entries": max_cache_entries
    }
