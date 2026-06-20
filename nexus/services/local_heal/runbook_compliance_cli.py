#!/usr/bin/env python3
"""V4-C.4 Internal Repair Workflow CLI — Operator Entry Point

Usage:
    python -m nexus.services.local_heal.runbook_compliance_cli <artifact_dir>

Validates repair artifact directories against V4-C.1 runbook.
Not automatic repair routing. Not runtime/routing enablement.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, '/Users/jameschen/Workspace/nexus')

from nexus.services.local_heal.runbook_compliance import check_compliance


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m nexus.services.local_heal.runbook_compliance_cli <artifact_dir>")
        sys.exit(1)
    
    artifact_dir = Path(sys.argv[1])
    task_id = sys.argv[2] if len(sys.argv) > 2 else None
    lane = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not artifact_dir.exists():
        print(f"ERROR: Artifact directory not found: {artifact_dir}")
        sys.exit(1)
    
    result = check_compliance(artifact_dir, expected_task_id=task_id, expected_lane=lane)
    
    print(f"Compliance Status: {result.compliance_status}")
    print(f"Recommended Status: {result.recommended_final_status}")
    print(f"\nPassed Gates ({len(result.passed_gates)}):")
    for g in result.passed_gates:
        print(f"  ✅ {g}")
    print(f"\nFailed Gates ({len(result.failed_gates)}):")
    for g in result.failed_gates:
        print(f"  ❌ {g}")
    if result.missing_fields:
        print(f"\nMissing Fields ({len(result.missing_fields)}):")
        for f in result.missing_fields:
            print(f"  ⚠️  {f}")
    if result.governance_violations:
        print(f"\nGovernance Violations ({len(result.governance_violations)}):")
        for v in result.governance_violations:
            print(f"  🚨 {v}")
    if result.attribution_violations:
        print(f"\nAttribution Violations ({len(result.attribution_violations)}):")
        for v in result.attribution_violations:
            print(f"  🚨 {v}")
    if result.caveats:
        print(f"\nCaveats ({len(result.caveats)}):")
        for c in result.caveats:
            print(f"  ℹ️  {c}")
    
    print(f"\n{'✅ PASS' if result.is_pass else '❌ FAIL'}: {result.compliance_status}")
    
    sys.exit(0 if result.is_pass else 1)


if __name__ == '__main__':
    main()
