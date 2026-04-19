import subprocess
from pathlib import Path

def test_stage_e():
    print("🧪 Running Stage E Validation...")
    
    target_file = Path("scripts/ops/diagnose_regression.py")
    original_content = target_file.read_text()
    
    try:
        # 1. Verification with Seal
        print("Case 1: Verification (Initial)")
        res = subprocess.run(["python3", "scripts/ops/verify_governance_seal.py"], capture_output=True, text=True)
        assert res.returncode == 0
        
        # 2. Modify and Check Drift
        print("Case 2: Detecting Drift")
        target_file.write_text(original_content + "\n# TAMPERED\n")
        res = subprocess.run(["python3", "scripts/ops/verify_governance_seal.py"], capture_output=True, text=True)
        assert res.returncode != 0
        assert "drift detected" in res.stdout.lower()
        
        # 3. Reseal and Verify
        print("Case 3: Reseal and Verify")
        subprocess.run(["python3", "scripts/ops/seal_governance.py"], check=True)
        res = subprocess.run(["python3", "scripts/ops/verify_governance_seal.py"], capture_output=True, text=True)
        assert res.returncode == 0
        
        print("✅ Stage E Validation PASS")

    finally:
        target_file.write_text(original_content)
        # Restore seal to original state (based on original content)
        subprocess.run(["python3", "scripts/ops/seal_governance.py"], check=True)

if __name__ == "__main__":
    test_stage_e()
