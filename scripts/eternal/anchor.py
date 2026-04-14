#!/usr/bin/env python3
"""Phase 3：鏈上 anchor 索引同步與校驗"""
import json
import asyncio
import hashlib
import aiohttp
import aiofiles
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("nexus:eternal:anchor")

def write_anchors() -> Dict[str, Any]:
    """將 TX ID 寫回主索引"""
    offloads_path = Path(".nexus/eternal/offloads/manifest.json")
    if not offloads_path.exists():
        logger.error("Offloads manifest not found. Please run offload first.")
        # Return empty shell
        return {"offloaded_mb": 0, "total_mb": 0, "anchors_count": 0}

    offloads_manifest = json.loads(offloads_path.read_text())
    
    anchors = {
        "last_updated": offloads_path.stat().st_mtime,
        "total_offloaded_mb": offloads_manifest.get("total_mb", 0),
        "total_slices": offloads_manifest.get("total_tx", 0),
        "recent_anchors": offloads_manifest.get("offloads", [])[-5:],  # 最近 5 個
        "gateway": "https://arweave.net",
        "wallet": offloads_manifest["offloads"][0]["wallet"] if offloads_manifest.get("offloads") else None,
        "anchors_count": len(offloads_manifest.get("offloads", []))
    }
    
    anchor_file = Path(".nexus/eternal/anchors.json")
    anchor_file.write_text(json.dumps(anchors, indent=2))
    logger.info(f"✅ Anchors updated: {anchor_file}")
    return anchors

async def verify_anchor(tx_id: str) -> bool:
    """鏈上資料校驗 (MD5 對比)"""
    gateway_url = f"https://arweave.net/{tx_id}"
    
    # Try to find local file from offload manifest
    offloads_manifest = json.loads(Path(".nexus/eternal/offloads/manifest.json").read_text())
    local_file = None
    for item in offloads_manifest["offloads"]:
        if item["tx_id"] == tx_id:
            local_file = Path(item["slice_file"])
            break
            
    if not local_file or not local_file.exists():
        logger.warning(f"Local file for {tx_id} not found. Skipping verification.")
        return False

    logger.info(f"驗證 {tx_id}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(gateway_url) as resp:
                if resp.status == 200:
                    remote_data = await resp.read()
                    remote_hash = hashlib.md5(remote_data).hexdigest()
                    local_hash = hashlib.md5(local_file.read_bytes()).hexdigest()
                    
                    match = remote_hash == local_hash
                    if match:
                        logger.info(f"  ✓ {tx_id} MD5 Match.")
                    else:
                        logger.error(f"  ✗ {tx_id} HASH MISMATCH! Local: {local_hash}, Remote: {remote_hash}")
                    return match
                else:
                    logger.error(f"  ✗ {tx_id} fetch failed (Status {resp.status}).")
                    return False
    except Exception as e:
        logger.error(f"  ✗ Error verifying {tx_id}: {e}")
        return False

async def download_anchor(tx_id: str, output_dir: str = ".nexus/eternal/downloads"):
    """透過 gateway 下載單一 TX"""
    gateway_url = f"https://arweave.net/{tx_id}"
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"下載 {tx_id} 永恆記憶...")
    async with aiohttp.ClientSession() as session:
        async with session.get(gateway_url) as resp:
            if resp.status == 200:
                data = await resp.read()
                output_file = out_dir / f"{tx_id}.jsonl"
                async with aiofiles.open(output_file, 'wb') as f:
                    await f.write(data)
                logger.info(f"  ✓ 保存至 {output_file}")
                return str(output_file)
            else:
                logger.error(f"  ✗ 下載失敗 (Status {resp.status}).")
                return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: anchor.py --update | --verify <txid> | --download <txid>")
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd == "--update":
        write_anchors()
    elif cmd == "--verify" and len(sys.argv) > 2:
        asyncio.run(verify_anchor(sys.argv[2]))
    elif cmd == "--download" and len(sys.argv) > 2:
        asyncio.run(download_anchor(sys.argv[2]))
    else:
        print("Unknown command.")
