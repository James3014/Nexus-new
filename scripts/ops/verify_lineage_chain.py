#!/usr/bin/env python3
import json
import sys
import hashlib
from pathlib import Path

LINEAGE_PATH = Path(".nexus/reports/lineage_chain.jsonl")

def compute_node_hash(node: dict) -> str:
    # Hash of the content excluding the hash of itself if it were stored there
    # But here we store the hash of (event_data + prev_hash)
    content = json.dumps(node, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()

def verify_chain():
    if not LINEAGE_PATH.exists():
        print("ℹ️ Lineage chain empty (File not found)")
        return True

    nodes = []
    for line in LINEAGE_PATH.read_text().splitlines():
        if not line.strip(): continue
        nodes.append(json.loads(line))

    if not nodes:
        return True

    expected_prev_hash = "0" * 64 # Genesis
    for i, node in enumerate(nodes):
        if node.get("prev_hash") != expected_prev_hash:
            print(f"❌ Lineage broken at node {i}: prev_hash mismatch")
            return False
        
        # Current node's hash will be the expected_prev_hash for next node
        # But we need to verify the node's integrity.
        # Typically, a lineage chain stores H(data + prev_hash).
        # Here we assume the node structure is: {"data": ..., "prev_hash": ..., "hash": ...}
        actual_hash = node.get("hash")
        # Recompute hash without the 'hash' key
        node_to_check = {k: v for k, v in node.items() if k != "hash"}
        recomputed = compute_node_hash(node_to_check)
        
        if actual_hash != recomputed:
            print(f"❌ Lineage broken at node {i}: integrity check failed (tampered)")
            return False
        
        expected_prev_hash = actual_hash

    print(f"✅ Lineage chain verified ({len(nodes)} nodes)")
    return True

if __name__ == "__main__":
    if not verify_chain():
        sys.exit(1)
    sys.exit(0)
