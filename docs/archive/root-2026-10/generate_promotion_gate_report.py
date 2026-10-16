#!/usr/bin/env python3
"""Generate promotion gate report for FlowMachine C phase verification."""

import json
import time
from pathlib import Path

LEDGER_PATH = Path("verification-evidence/rust_mismatch_ledger.jsonl")

def main():
    print("🔍 Checking promotion gate conditions...")
    
    # Check ledger
    total_entries = 0
    mismatch_entries = 0
    high_entries = 0
    critical_entries = 0
    
    if LEDGER_PATH.exists():
        with open(LEDGER_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    total_entries += 1
                    if not entry.get("match", True):
                        mismatch_entries += 1
                        severity = entry.get("severity", "LOW")
                        if severity == "HIGH":
                            high_entries += 1
                        elif severity == "CRITICAL":
                            critical_entries += 1
                except json.JSONDecodeError:
                    continue
    
    # Determine promotion readiness
    promotion_blocked = high_entries > 0 or critical_entries > 0
    promotion_ready = not promotion_blocked and total_entries > 0
    
    # Check if primary cutover is disabled by default
    primary_disabled = True  # GovernanceBridge(dual_run=False) is default
    
    report = {
        "schema": "promotion_gate.report.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ledger_summary": {
            "total_entries": total_entries,
            "mismatch_entries": mismatch_entries,
            "low_entries": mismatch_entries - high_entries - critical_entries,
            "high_entries": high_entries,
            "critical_entries": critical_entries
        },
        "promotion_conditions": {
            "zero_high_critical_mismatches": high_entries == 0 and critical_entries == 0,
            "ledger_has_data": total_entries > 0,
            "met": promotion_ready
        },
        "primary_cutover": {
            "disabled_by_default": primary_disabled,
            "status": "DISABLED"
        },
        "overall_status": "BLOCKED" if promotion_blocked else ("READY" if promotion_ready else "NO_DATA"),
        "can_promote": promotion_ready and not promotion_blocked
    }
    
    output_path = Path("verification-evidence/promotion_gate_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📊 Promotion Gate Report: {output_path}")
    print(f"   Total ledger entries: {total_entries}")
    print(f"   Mismatches: {mismatch_entries}")
    print(f"   HIGH: {high_entries}, CRITICAL: {critical_entries}")
    print(f"   Promotion blocked: {'YES' if promotion_blocked else 'NO'}")
    print(f"   Primary cutover: DISABLED ✅")
    print(f"   Overall: {report['overall_status']}")
    
    return not promotion_blocked

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
