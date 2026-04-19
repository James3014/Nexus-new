#!/usr/bin/env python3
import json
import hashlib
from pathlib import Path

IMMUTABLE_PATHS = [
    "scripts/ops/diagnose_regression.py",
    "scripts/ops/verify_lineage_chain.py",
    "scripts/ops/evidence_verifier.py",
    "scripts/ops/replay_runner.py",
    "nexus/core/hallucination_guard.py",
    ".nexus/reports/baseline/baseline_manifest.json"
]

SEAL_PATH = Path(".nexus/config/governance_seal.json")

def compute_sha256(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()

def generate_seal():
    SEAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    seal_data = {
        "files": {},
        "generated_at": str(__import__("datetime").datetime.now())
    }
    
    for p_str in IMMUTABLE_PATHS:
        p = Path(p_str)
        seal_data["files"][p_str] = compute_sha256(p)
        print(f"🔒 Sealed: {p_str} ({seal_data['files'][p_str][:8]})")

    SEAL_PATH.write_text(json.dumps(seal_data, indent=2), encoding="utf-8")
    print(f"✅ Governance seal created at {SEAL_PATH}")

if __name__ == "__main__":
    generate_seal()
