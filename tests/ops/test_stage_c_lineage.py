import subprocess
import json
import os
from pathlib import Path

def test_stage_c():
    print("🧪 Running Stage C Validation...")
    
    lineage_path = Path(".nexus/reports/lineage_chain.jsonl")
    if lineage_path.exists():
        lineage_path.unlink()

    try:
        # 1. Normal Append
        print("Case 1: Normal Append")
        if lineage_path.exists(): lineage_path.unlink()
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "test_event", '{"val": 1}'], check=True)
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "test_event", '{"val": 2}'], check=True)
        
        res = subprocess.run(["python3", "scripts/ops/verify_lineage_chain.py"], capture_output=True, text=True)
        assert res.returncode == 0
        assert "verified" in res.stdout.lower()

        # 2. Tamper with node
        print("Case 2: Tampering")
        # No reset here, we use the current valid chain
        lines = lineage_path.read_text().splitlines()
        node0 = json.loads(lines[0])
        node0["data"]["val"] = 999 # Tamper
        lines[0] = json.dumps(node0)
        lineage_path.write_text("\n".join(lines) + "\n")
        
        res = subprocess.run(["python3", "scripts/ops/verify_lineage_chain.py"], capture_output=True, text=True)
        assert res.returncode != 0
        assert "integrity check failed" in res.stdout.lower()

        # 3. Break prev_hash
        print("Case 3: Broken prev_hash")
        # RESET here
        if lineage_path.exists(): lineage_path.unlink()
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "test_event", '{"val": 1}'], check=True)
        subprocess.run(["python3", "scripts/ops/append_lineage.py", "test_event", '{"val": 2}'], check=True)
        
        lines = lineage_path.read_text().splitlines()
        node1 = json.loads(lines[1])
        node1["prev_hash"] = "wrong_hash" # Break chain
        # Re-compute its own hash to pass integrity but fail chain
        import hashlib
        node1_to_hash = {k: v for k, v in node1.items() if k != "hash"}
        node1["hash"] = hashlib.sha256(json.dumps(node1_to_hash, sort_keys=True).encode()).hexdigest()
        lines[1] = json.dumps(node1)
        lineage_path.write_text("\n".join(lines) + "\n")

        res = subprocess.run(["python3", "scripts/ops/verify_lineage_chain.py"], capture_output=True, text=True)
        assert res.returncode != 0
        assert "prev_hash mismatch" in res.stdout.lower()

        print("✅ Stage C Validation PASS")

    finally:
        if lineage_path.exists():
            lineage_path.unlink()

if __name__ == "__main__":
    test_stage_c()
