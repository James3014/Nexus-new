"""
Nexus Arweave Eternal Memory Uploader
支援 lesson_events.jsonl 的永久、不可變存儲。
"""

import asyncio
import json
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone
import aiohttp
from irys_sdk import Uploader  # irys-sdk

from nexus.services.continuous_learning import load_jsonl, utc_now_iso


ARWEAVE_NODE = "https://node2.irys.xyz"
# WALLET_KEY: ~/.nexus/wallet.json or provided by user
DEFAULT_WALLET_PATH = Path.home() / ".nexus" / "wallet.json"


def write_jsonl(path: Path, data: List[Dict[str, Any]]):
    """Write list of dicts to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def upload_lessons_to_arweave(
    repo_root: Path,
    min_confidence: float = 0.7,
    tags: Optional[Dict[str, str]] = None,
    wallet_key_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    上傳過濾後的 lessons 到 Arweave，產生 immutable CID。
    """
    jsonl_path = repo_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    if not jsonl_path.exists():
        return {"status": "skip", "reason": "no lessons"}
    
    # 過濾高品質 lessons
    lessons = load_jsonl(jsonl_path)
    high_quality = [
        lesson for lesson in lessons
        if lesson.get("confidence", 0) >= min_confidence
    ]
    
    if not high_quality:
        return {"status": "skip", "reason": f"no lessons meeting confidence threshold {min_confidence}"}
    
    content = json.dumps(high_quality, ensure_ascii=False, indent=2)
    
    # 計算 content hash (用於去重)
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # 檢查是否已上傳
    cid_file = repo_root / ".nexus" / "learning" / "arweave_cids.jsonl"
    existing_cids = load_jsonl(cid_file)
    for cid_record in existing_cids:
        if cid_record.get("content_hash") == content_hash:
            return {
                "status": "cached",
                "tx_id": cid_record["arweave_tx"],
                "lesson_count": len(high_quality)
            }
    
    wallet_path = wallet_key_path or DEFAULT_WALLET_PATH
    if not wallet_path.exists():
        return {
            "status": "error", 
            "reason": f"Wallet not found at {wallet_path}. Eternal memory upload aborted.",
            "content_hash": content_hash
        }

    try:
        # Load wallet data (assuming it is formatted for the token, e.g. Ethereum/Arweave private key)
        with open(wallet_path, "r") as f:
            wallet_data = json.load(f)
        
        # Irys/Bundlr implementation (Using Ethereum token for example, can be adjusted)
        # Note: Irys sdk expects specific token name and provider
        irys = Uploader(ARWEAVE_NODE, "ethereum", token_opts={"private_key": wallet_data.get("private_key")})
        
        upload_tags = [
            {"name": "App-Name", "value": "Nexus-Lessons"},
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Schema-Version", "value": "lesson_event.v1"},
            {"name": "Workspace", "value": repo_root.name},
            {"name": "Confidence-Min", "value": str(min_confidence)},
            {"name": "Lesson-Count", "value": str(len(high_quality))},
        ]
        if tags:
            for k, v in tags.items():
                upload_tags.append({"name": k, "value": v})
        
        # Funding and Uploading (simplified for v22 logic)
        # For real production, check balance and fund if needed
        # price = irys.get_price(len(content))
        # irys.fund(price) 
        
        tx = irys.upload(content.encode(), tags=upload_tags)
        tx_id = tx.get("id")
        
        # 記錄 CID
        cid_record = {
            "timestamp_utc": utc_now_iso(),
            "workspace": repo_root.name,
            "lesson_count": len(high_quality),
            "content_hash": content_hash,
            "arweave_tx": tx_id,
            "tags": {t["name"]: t["value"] for t in upload_tags},
            "min_confidence": min_confidence,
        }
        
        # Append 到本地 CID 索引
        existing_cids.append(cid_record)
        write_jsonl(cid_file, existing_cids)
        
        return {
            "status": "uploaded",
            "tx_id": tx_id,
            "lesson_count": len(high_quality),
            "gateway_url": f"https://gateway.irys.xyz/{tx_id}",
            "content_hash": content_hash
        }
    except Exception as e:
        return {"status": "error", "reason": str(e), "content_hash": content_hash}


async def download_lessons_from_arweave(tx_id: str) -> List[Dict[str, Any]]:
    """
    從 Arweave CID 下載 lessons。
    """
    async with aiohttp.ClientSession() as session:
        url = f"https://gateway.irys.xyz/{tx_id}"
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            content = await resp.text()
            return json.loads(content)
