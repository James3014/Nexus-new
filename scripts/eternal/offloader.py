#!/usr/bin/env python3
"""Phase 2：Arweave 永恆上鏈"""
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from arweave import Transaction, Wallet

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("nexus:eternal:offload")

async def offload_slice(slice_file: str, wallet_keyfile: str = "~/.arweave/key.json") -> Dict[str, Any]:
    """上傳單一 slice 到 Arweave"""
    wallet_path = Path(wallet_keyfile).expanduser()
    if not wallet_path.exists():
        logger.error(f"錢包檔案不存在：{wallet_keyfile}")
        raise FileNotFoundError(f"錢包檔案不存在：{wallet_keyfile}")
    
    # Initialize wallet and client
    wallet = Wallet.from_keyfile(str(wallet_path))
    # Note: arweave-python-client uses a different API structure than the JS one.
    # We use the transaction broadcast method.
    
    with open(slice_file, 'rb') as f:
        data = f.read()
    
    # 建立交易
    # NOTE: arweave-python-client SDK usage:
    tx = Transaction(wallet, data=data)
    tx.add_tag("Content-Type", "application/jsonl")
    tx.add_tag("App-Name", "nexus-eternal")
    tx.add_tag("Content-Slice", Path(slice_file).name)
    tx.add_tag("Policy-Type", "policymemory")
    
    # 簽署並發布
    tx.sign()
    # Transaction.sign() is synchronous in this SDK version
    
    # Send
    # In some versions it's tx.post() or wallet.post_transaction(tx)
    try:
        response = tx.send()
        tx_id = tx.id
        logger.info(f"  ✓ Slice {Path(slice_file).name} sent. TX ID: {tx_id} | Response: {response}")
        
        return {
            "tx_id": tx_id,
            "slice_file": slice_file,
            "size_bytes": len(data),
            "timestamp": datetime.now().isoformat(),
            "wallet": wallet.address,
            "status": "pending" # Arweave needs confirmation
        }
    except Exception as e:
        logger.error(f"  ✗ Failed to send slice {slice_file}: {e}")
        raise e

async def offload_all_slices(wallet_keyfile: str = "~/.arweave/key.json") -> List[Dict[str, Any]]:
    """批量上傳所有 slices"""
    manifest_path = Path(".nexus/eternal/slices/manifest.json")
    if not manifest_path.exists():
        logger.error("請先執行 nexus:eternal slice")
        raise FileNotFoundError("請先執行 nexus:eternal slice")
    
    manifest_data = json.loads(manifest_path.read_text())
    offloads = []
    
    # 遍歷所有來源的所有 slices
    # Updated slicer supporting multiple sources
    all_slices = []
    if "sources" in manifest_data:
        for source_name, info in manifest_data["sources"].items():
            all_slices.extend(info.get("slices", []))
    else:
        # Backward compatibility with simple spec
        all_slices = manifest_data.get("slices", [])

    output_dir = Path(".nexus/eternal/offloads")
    output_dir.mkdir(parents=True, exist_ok=True)

    for slice_file in all_slices:
        logger.info(f"上傳 {Path(slice_file).name}...")
        try:
            offload = await offload_slice(slice_file, wallet_keyfile)
            offloads.append(offload)
        except Exception as e:
            logger.error(f"Skipping slice {slice_file} due to error: {e}")
    
    # 寫入 offloads manifest
    offloads_manifest = {
        "offloads": offloads,
        "total_tx": len(offloads),
        "total_mb": sum(o["size_bytes"] / (1024*1024) for o in offloads),
        "updated_at": datetime.now().isoformat()
    }
    Path(".nexus/eternal/offloads/manifest.json").write_text(json.dumps(offloads_manifest, indent=2))
    
    return offloads

from datetime import datetime

if __name__ == "__main__":
    import sys
    wallet_key = sys.argv[1] if len(sys.argv) > 1 else "~/.arweave/key.json"
    try:
        asyncio.run(offload_all_slices(wallet_key))
    except Exception as e:
        logger.critical(f"FATAL ERROR in offloader: {e}")
        sys.exit(1)
