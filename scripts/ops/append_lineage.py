#!/usr/bin/env python3
import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone

LINEAGE_PATH = Path(".nexus/reports/lineage_chain.jsonl")

def compute_node_hash(node: dict) -> str:
    content = json.dumps(node, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()

def append_node(event_type: str, event_data: dict):
    LINEAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    prev_hash = "0" * 64
    if LINEAGE_PATH.exists():
        lines = LINEAGE_PATH.read_text().splitlines()
        if lines:
            last_node = json.loads(lines[-1])
            prev_hash = last_node.get("hash", "0" * 64)

    node = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "data": event_data,
        "prev_hash": prev_hash
    }
    
    node["hash"] = compute_node_hash(node)
    
    with open(LINEAGE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(node, ensure_ascii=False) + "\n")
    
    print(f"🔗 Lineage node appended: {node['hash'][:8]}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python append_lineage.py <type> <json_data>")
        sys.exit(1)
    
    event_type = sys.argv[1]
    try:
        event_data = json.loads(sys.argv[2])
    except:
        event_data = {"raw": sys.argv[2]}
    
    append_node(event_type, event_data)
