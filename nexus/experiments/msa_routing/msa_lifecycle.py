"""
msa_lifecycle.py
Lifecycle & A/B Kill Switch
"""
import time
import os
from .msa_indexer import get_file_hash
from typing import Dict, Any, List

class KillSwitchTriggeredError(Exception):
    pass

class MSALifecycle:
    def __init__(self, decay_rate: float = 0.5):
        self.decay_rate = decay_rate
        
    def check_drift_and_decay(self, repo_root: str, db_entry: Dict[str, Any]) -> Dict[str, Any]:
        filepath = db_entry.get("id", "")
        full_path = os.path.join(repo_root, filepath)
        
        current_hash = get_file_hash(full_path)
        stored_hash = db_entry.get("source_hash", "")
        
        current_time = int(time.time())
        created_time = db_entry.get("created_at", current_time)
        if db_entry.get("ttl", -1) > 0 and (current_time - created_time) > db_entry.get("ttl", -1):
            db_entry["confidence_decay"] = 0.0
            return db_entry
            
        if current_hash and stored_hash and current_hash != stored_hash:
            db_entry["confidence_decay"] = db_entry.get("confidence_decay", 1.0) * self.decay_rate
            print(f"⚠️ Drift detected on {filepath}. Confidence decayed to {db_entry['confidence_decay']}")
            
        return db_entry
        
    def evaluate_kill_switch(self, benchmark_results: Dict[str, float], baseline: Dict[str, float]) -> Dict[str, Any]:
        msa_precision = benchmark_results.get("precision", 0.0)
        base_precision = baseline.get("precision", 0.0)
        
        unknown_rate = benchmark_results.get("unknown_correct_rate", 0.0)
        
        regression = benchmark_results.get("regression_rate", 0.0)
        base_regression = baseline.get("regression_rate", 0.0)
        
        cost = benchmark_results.get("cost_per_success", 1.0)
        base_cost = baseline.get("cost_per_success", 1.0)
        
        reasons = []
        if msa_precision < base_precision:
            reasons.append(f"Precision degraded ({msa_precision} < {base_precision})")
        if unknown_rate < 0.95:
            reasons.append(f"Unknown accuracy below 0.95 ({unknown_rate})")
        if regression > base_regression:
            reasons.append(f"Regression increased ({regression} > {base_regression})")
        if cost > (base_cost * 0.9):
            reasons.append(f"Cost efficiency not improved by 10% ({cost} vs {base_cost})")
            
        if reasons:
            raise KillSwitchTriggeredError(f"Kill Switch Triggered: {', '.join(reasons)}")
        return {"triggered": False, "reasons": []}
