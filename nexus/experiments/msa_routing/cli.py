import json
import argparse
from typing import Dict, Any, List
import os

from nexus.experiments.msa_routing.msa_router_contract import MSARouter, MemoryCandidate
from nexus.experiments.msa_routing.msa_quarantine import MSAQuarantine
from nexus.experiments.msa_routing.msa_lifecycle import MSALifecycle

def run_smoke_test() -> Dict[str, Any]:
    print("🚀 Running MSA Routing Smoke Test...", flush=True)

    # 1. Router
    router = MSARouter(confidence_threshold=0.8)
    candidates = [
        MemoryCandidate(id="test1", content="c1", type="code", score=0.9, version_id="v1", source_hash="h1"),
    ]
    route_result = router.route("query-123", candidates)

    # 2. Quarantine
    quarantine = MSAQuarantine()
    quarantine.add_to_quarantine("test1", {"data": "test"})
    # Let's mock the hallucination and acceptance check outcomes
    promoted = quarantine.promote("test1", "PASS", "VERIFIED")

    # 3. Lifecycle & Benchmark Kill Switch
    lifecycle = MSALifecycle()
    baseline = {"precision": 0.8, "unknown_correct_rate": 0.96, "regression_rate": 0.05, "cost_per_success": 1.0}
    
    # We construct a mock benchmark result to simulate the output
    benchmark_results = {
        "precision": 0.85,
        "unknown_correct_rate": 0.98,
        "regression_rate": 0.04,
        "cost_per_success": 0.85
    }
    kill_switch_eval = lifecycle.evaluate_kill_switch(benchmark_results, baseline)

    output = {
        "precision": benchmark_results["precision"],
        "unknown_correct_rate": benchmark_results["unknown_correct_rate"],
        "regression_rate": benchmark_results["regression_rate"],
        "cost_per_success": benchmark_results["cost_per_success"],
        "kill_switch_triggered": kill_switch_eval["triggered"],
        "reasons": kill_switch_eval["reasons"],
        "route_status": route_result.status,
        "promoted": promoted
    }

    return output

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MSA Routing CLI")
    parser.add_argument("--smoke", action="store_true", help="Run smoke test and output JSON")
    args = parser.parse_args()

    if args.smoke:
        results = run_smoke_test()
        print(json.dumps(results, indent=2))
