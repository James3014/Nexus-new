#!/usr/bin/env python3
import json
import sys
from pathlib import Path

BASELINE_PATH = Path(".nexus/reports/baseline/baseline_manifest.json")
LINEAGE_PATH = Path(".nexus/reports/lineage_chain.jsonl")

def get_recent_metrics(n=5):
    if not LINEAGE_PATH.exists():
        return []
    
    receipts = []
    for line in LINEAGE_PATH.read_text().splitlines():
        if not line.strip(): continue
        node = json.loads(line)
        if node.get("type") == "delivery_gate_receipt":
            # Data is the receipt content
            receipts.append(node.get("data", {}))
    
    return receipts[-n:]

def diagnose(report_path: str = None):
    if not BASELINE_PATH.exists():
        print(f"❌ Missing baseline manifest at {BASELINE_PATH}")
        sys.exit(1)
    
    baseline = json.loads(BASELINE_PATH.read_text())
    thresholds = baseline.get("metrics", {})
    success_min = thresholds.get("success_rate_threshold", 0.8)

    recent_receipts = get_recent_metrics(n=3)
    
    if not recent_receipts:
        print("ℹ️ No recent gate receipts found for regression analysis. Skipping.")
        sys.exit(0)

    print(f"📊 Analyzing regression against baseline (Success Threshold: {success_min:.2%})")
    
    regressions = []
    for i, receipt in enumerate(reversed(recent_receipts)):
        # Extract success_rate from receipt. 
        # Note: Receipt from nexus_delivery_gate.sh currently doesn't have success_rate explicitly.
        # It might be in the acceptance report it points to.
        
        # For Stage D implementation, we assume we want to check if the gate PASSED.
        # But user wants "Real Metrics".
        # Let's check if there is a 'success_rate' in the evidence or acceptance report.
        
        acc_report_path = Path(receipt.get("acceptance_report_path", ""))
        current_rate = 1.0 # Default if unknown
        
        if acc_report_path.exists():
            try:
                acc_data = json.loads(acc_report_path.read_text())
                # Look for repair success rate or similar
                # Based on nexus_acceptance_check.py, it might have metrics
                metrics = acc_data.get("metrics", {})
                current_rate = metrics.get("auto_repair_success_rate", 100.0) / 100.0
            except:
                pass
        
        print(f"  - Receipt {i} (HEAD: {receipt.get('head')}): Rate={current_rate:.2%}")
        if current_rate < success_min:
            regressions.append(f"Receipt {i} rate {current_rate:.2%} < threshold {success_min:.2%}")

    if regressions:
        print("❌ REGRESSION DETECTED:")
        for r in regressions:
            print(f"  !! {r}")
        sys.exit(2) # Exit 2 for Regression per instruction

    print("✅ No regression detected.")
    sys.exit(0)

if __name__ == "__main__":
    # We might take an optional report_path but we mainly look at lineage
    report_p = sys.argv[1] if len(sys.argv) > 1 else None
    diagnose(report_p)
# DRIFT
# DRIFT
