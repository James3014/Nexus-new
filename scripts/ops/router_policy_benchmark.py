import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Set
from nexus.core.state_contracts import NexusState
from nexus.engine.autonomic_router import AutonomicRouter

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "nexus/knowledge/policy_memory.jsonl"
CORE_FIXTURE = ROOT / "tests/fixtures/router_benchmark_cases.json"
HOLDOUT_FIXTURE = ROOT / "tests/fixtures/router_holdout_cases.json"

def evaluate(router, fixture_path):
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    tp = fp = tn = fn = 0
    results = []
    
    for c in cases:
        plan = router.route(c["task"], NexusState(task_id="bench"), {"est_tokens": 100})
        hits = plan.matched_policies
        matched_expected = False
        if c["expected_tags"]:
            for hit in hits:
                if any(tag.upper() in hit.upper() for tag in c["expected_tags"]):
                    matched_expected = True
                    break
            if matched_expected: tp += 1
            else: fn += 1
        else:
            if not hits: tn += 1
            else: fp += 1
        
        results.append({
            "name": c["name"],
            "hits": len(hits),
            "pass": (c["expected_tags"] and matched_expected) or (not c["expected_tags"] and not hits)
        })
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    fp_rate = fp / (fp + tn) if (fp + tn) > 0 else 0
    
    return results, {"precision": precision, "recall": recall, "f1": f1, "fp_rate": fp_rate, "tp": tp, "fp": fp, "tn": tn, "fn": fn}

def main():
    router = AutonomicRouter(str(ROOT))
    print(f"--- Nexus v4.10 Hardened Benchmark ---")
    
    core_res, core_metrics = evaluate(router, CORE_FIXTURE)
    hold_res, hold_metrics = evaluate(router, HOLDOUT_FIXTURE)
    
    print("\n[CORE SET RESULTS]")
    for r in core_res:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['name']:<25} | Hits: {r['hits']}")

    print("\n[HOLDOUT SET RESULTS]")
    for r in hold_res:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['name']:<25} | Hits: {r['hits']}")

    print("\n--- AGGREGATE METRICS ---")
    total_tp = core_metrics["tp"] + hold_metrics["tp"]
    total_fp = core_metrics["fp"] + hold_metrics["fp"]
    total_fn = core_metrics["fn"] + hold_metrics["fn"]
    total_tn = core_metrics["tn"] + hold_metrics["tn"]
    
    agg_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    agg_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    agg_f1 = 2 * (agg_prec * agg_rec) / (agg_prec + agg_rec) if (agg_prec + agg_rec) > 0 else 0
    agg_fp = total_fp / (total_fp + total_tn) if (total_fp + total_tn) > 0 else 0

    print(json.dumps({
        "precision": round(agg_prec, 4),
        "recall": round(agg_rec, 4),
        "f1": round(agg_f1, 4),
        "fp_rate": round(agg_fp, 4),
        "all_positive_pass": all(r["pass"] for r in core_res if not r["name"].startswith("noise")) and all(r["pass"] for r in hold_res if not r["name"].startswith("noise"))
    }, indent=2))

if __name__ == "__main__":
    main()
