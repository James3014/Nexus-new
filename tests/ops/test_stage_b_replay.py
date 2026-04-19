import subprocess
import json
from pathlib import Path

def test_stage_b():
    print("🧪 Running Stage B Validation...")
    
    evidence_path = Path(".nexus/reports/test_b_evidence.json")
    
    try:
        # Case 1: Empty test_artifacts
        print("Case 1: No test_artifacts (Fail-Closed)")
        evidence_path.write_text(json.dumps({
            "final_response": "I have completed the task.",
            "evidence_bundle": {
                "code_artifacts": ["app.py"],
                "test_artifacts": []
            }
        }))
        res = subprocess.run(["python3", "scripts/ops/evidence_verifier.py", str(evidence_path)], capture_output=True, text=True)
        # Should exit non-zero and be REJECTED
        assert res.returncode != 0
        data = json.loads(res.stdout)
        assert data["status"] == "REJECTED"
        assert data["overall_trust"] == "LOW"
        assert data["replay"]["status"] == "FAIL"

        # Case 2: No test_artifacts BUT allow_no_replay=true
        print("Case 2: No test_artifacts (Allowed)")
        res = subprocess.run(["python3", "scripts/ops/evidence_verifier.py", str(evidence_path), "--allow-no-replay"], capture_output=True, text=True)
        # Hallucination guard might still give partial due to evidence gap, but replay runner should be PARTIAL/PASS
        data = json.loads(res.stdout)
        assert data["replay"]["status"] == "PARTIAL"

        # Case 3: Valid test_artifacts
        print("Case 3: Valid test_artifacts")
        evidence_path.write_text(json.dumps({
            "final_response": "The task is ready for review.",
            "evidence_bundle": {
                "code_artifacts": ["app.py"],
                "test_artifacts": [{"aggregates": {"success_rate": 1.0}}],
                "command_artifacts": ["pytest"]
            }
        }))
        res = subprocess.run(["python3", "scripts/ops/evidence_verifier.py", str(evidence_path)], capture_output=True, text=True)
        # Should be VERIFIED and exit 0
        data = json.loads(res.stdout)
        assert res.returncode == 0
        assert data["status"] == "VERIFIED"
        assert data["overall_trust"] == "HIGH"
        assert data["replay"]["status"] == "PASS"

        print("✅ Stage B Validation PASS")

    finally:
        if evidence_path.exists():
            evidence_path.unlink()

if __name__ == "__main__":
    test_stage_b()
