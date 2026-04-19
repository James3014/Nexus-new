import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any

class AntiDrift:
    """
    Stage 3: Anti-Drift Immutable Root.
    防止核心治理規則與腳本被惡意或意外竄改。
    """
    
    IMMUTABLE_FILES = [
        "scripts/ops/verify_report_claims.py",
        "scripts/ops/nexus_delivery_gate.sh",
        "nexus/schemas/evidence_bundle_v1.json",
        "nexus/delivery/evidence_verifier.py",
        "nexus/delivery/replay_runner.py",
        "nexus/delivery/anti_drift.py"
    ]
    
    def __init__(self, project_root: Path, manifest_path: Path):
        self.project_root = project_root
        self.manifest_path = manifest_path

    def compute_file_hash(self, relative_path: str) -> str:
        p = self.project_root / relative_path
        if not p.exists():
            return "FILE_NOT_FOUND"
        content = p.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def verify_drift(self) -> Tuple[bool, Dict[str, Any]]:
        if not self.manifest_path.exists():
            return False, {"error": "manifest_not_found"}
        
        try:
            expected_hashes = json.loads(self.manifest_path.read_text())
        except Exception as e:
            return False, {"error": f"manifest_parse_failed: {str(e)}"}
        
        results = {}
        all_passed = True
        
        for rel_path in self.IMMUTABLE_FILES:
            actual = self.compute_file_hash(rel_path)
            expected = expected_hashes.get(rel_path)
            
            match = (actual == expected)
            if not match:
                all_passed = False
                
            results[rel_path] = {
                "passed": match,
                "actual": actual,
                "expected": expected
            }
            
        return all_passed, results

    @staticmethod
    def generate_manifest(project_root: Path, target_path: Path):
        hashes = {}
        ad = AntiDrift(project_root, target_path)
        for rel_path in AntiDrift.IMMUTABLE_FILES:
            hashes[rel_path] = ad.compute_file_hash(rel_path)
        
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(hashes, indent=2))
        return hashes
