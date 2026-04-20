"""
msa_lifecycle.py
Lifecycle & A/B Kill Switch
"""
import time
import os
from nexus.experiments.msa_routing.msa_indexer import get_file_hash
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
        from nexus.experiments.msa_routing.benchmark_gates import PHASE1_GATES
        
        msa_precision = benchmark_results.get("precision", 0.0)
        base_precision = baseline.get("precision", 0.0)
        
        unknown_rate = benchmark_results.get("unknown_correct_rate", 0.0)
        regression = benchmark_results.get("regression_rate", 0.0)
        latency = benchmark_results.get("p50_latency_ms", 0.0)
        
        reasons = []
        
        # 1. Precision & relative gain
        rel_improvement = (msa_precision - base_precision) / max(0.001, base_precision)
        if msa_precision < base_precision:
            reasons.append(f"Precision degraded ({msa_precision} < {base_precision})")
        elif rel_improvement < PHASE1_GATES["relative_improvement_min"]:
            reasons.append(f"Relative improvement {rel_improvement:.2%} < {PHASE1_GATES['relative_improvement_min']:.2%}")
            
        # 2. Unknown Rate (P0)
        if unknown_rate < PHASE1_GATES["unknown_correct_rate_min"]:
            reasons.append(f"Unknown accuracy {unknown_rate} below P0 threshold {PHASE1_GATES['unknown_correct_rate_min']}")
            
        # 3. Regression limit
        if regression > PHASE1_GATES["regression_rate_max"]:
            reasons.append(f"Regression {regression} > max {PHASE1_GATES['regression_rate_max']}")
            
        # 4. Latency
        if latency > PHASE1_GATES["p50_latency_ms_max"]:
            reasons.append(f"Latency {latency}ms > max {PHASE1_GATES['p50_latency_ms_max']}ms")
            
        if reasons:
            raise KillSwitchTriggeredError(f"Kill Switch Triggered: {', '.join(reasons)}")
        return {"triggered": False, "reasons": []}
