#!/usr/bin/env python3
import json
import hashlib
import sys
from pathlib import Path

SEAL_PATH = Path(".nexus/config/governance_seal.json")

def compute_sha256(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_seal():
    if not SEAL_PATH.exists():
        print("⚠️ No governance seal found. Run seal_governance.py first.")
        return False

    seal_data = json.loads(SEAL_PATH.read_text())
    files = seal_data.get("files", {})
    
    drift_detected = []
    for p_str, expected_sha in files.items():
        actual_sha = compute_sha256(Path(p_str))
        if actual_sha != expected_sha:
            drift_detected.append(f"{p_str} (Expected: {expected_sha[:8]}, Actual: {actual_sha[:8]})")

    if drift_detected:
        print("❌ GOVERNANCE DRIFT DETECTED:")
        for d in drift_detected:
            print(f"  !! {d}")
        return False

    print("✅ Governance integrity verified (No drift).")
    return True

if __name__ == "__main__":
    if not verify_seal():
        sys.exit(1)
    sys.exit(0)
