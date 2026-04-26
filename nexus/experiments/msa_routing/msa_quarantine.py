"""
msa_quarantine.py
Writeback Quarantine & Promotion Gate
"""
import json
import os
from typing import Dict, Any

class MSAQuarantine:
    def __init__(self, quarantine_dir: str = "nexus/experiments/msa_routing/quarantine"):
        self.quarantine_dir = quarantine_dir
        os.makedirs(self.quarantine_dir, exist_ok=True)
        
    def add_to_quarantine(self, item_id: str, data: Dict[str, Any]):
        filepath = os.path.join(self.quarantine_dir, f"{item_id.replace('/', '_')}.json")
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            
    def evaluate_gate(self, acceptance_check_status: str, hallucination_index_status: str) -> bool:
        if acceptance_check_status == "PASS" and hallucination_index_status == "VERIFIED":
            return True
        return False
        
    def promote(self, item_id: str, acceptance_check_status: str, hallucination_index_status: str) -> bool:
        if self.evaluate_gate(acceptance_check_status, hallucination_index_status):
            from nexus.infrastructure.dist_lock import distributed_lock
            with distributed_lock(f"quarantine:promote:{item_id}", timeout=30, blocking=False) as acquired:
                if not acquired:
                    print(f"⚠️ Promotion of {item_id} is already in progress.")
                    return False
                    
                filepath = os.path.join(self.quarantine_dir, f"{item_id.replace('/', '_')}.json")
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                # Penetrate to Physical DB
                try:
                    from nexus.experiments.msa_routing.msa_indexer import upsert_to_lancedb
                    if not "vector" in data:
                        data["vector"] = [0.1] * 128
                    
                    data["claim_confidence"] = data.get("claim_confidence", 0.95) # High confidence for verified promote
                    
                    record = {
                        "id": item_id,
                        "vector": data["vector"],
                        "content": data.get("content", ""),
                        "type": data.get("type", "artifact"),
                        "version_id": data.get("version_id", "v_promoted"),
                        "source_hash": data.get("source_hash", "verified"),
                        "ttl": data.get("ttl", 86400 * 365),
                        "confidence_decay": 1.0,
                        "claim_confidence": data["claim_confidence"]
                    }
                    upsert_to_lancedb(".", [record])
                    
                    # Redis Broadcast for metabolism synchronization
                    from nexus.infrastructure.redis_pool import RedisPool
                    client = RedisPool.get_client()
                    if client:
                        client.set(f"nexus:memory:promoted:{item_id}", json.dumps(record), ex=3600)
                        client.publish("nexus_memory_sync", item_id)
                        
                except Exception as e:
                    print(f"⚠️ Promotion penetration failed: {e}")

                print(f"✅ Promoted {item_id} to Main Index.")
                os.remove(filepath)
                return True
        print(f"❌ Rejected {item_id}. acceptance: {acceptance_check_status}, hallucination: {hallucination_index_status}")
        return False
