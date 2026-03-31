#!/usr/bin/env python3
import sys
import tempfile
import json
from pathlib import Path
from unittest import mock

# Setup imports
project_root = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(project_root))
import scripts.ops.nexus_acceptance_check as nac

def run_test_case(name: str, mode: str, is_high_risk: bool, ready: bool, heal_eff: float, learn_gain: float, expected_pass: bool):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        metrics_dir = tmp_path / ".nexus" / "metrics"
        metrics_dir.mkdir(parents=True)
        reports_dir = tmp_path / ".nexus" / "reports"
        
        # Write dummy optimization runs
        (metrics_dir / "skills_optimization_runs.jsonl").write_text(json.dumps({"success": True}) + "\n")
        
        # Write dummy outcome events ensuring learning_check fails (Warning)
        # We need PR < 30 or NRH < 20 to fail learning check
        outcome_event = {
            "pattern_reuse": 10.0,
            "next_run_hit": 10.0,
            "sandbox_mode": "system" if is_high_risk else "isolated",
            "pregate_skip": is_high_risk,
            "regression_pass_rate": 100.0,
            "retry_count": 0
        }
        (metrics_dir / "skill_outcome_events.jsonl").write_text(json.dumps(outcome_event) + "\n")
        
        # Mock build_skills_health
        health_mock = {
            "ready_for_formal_use": ready,
            "summary": {
                "healing_efficiency": heal_eff,
                "learning_gain": learn_gain
            }
        }
        
        test_args = [
            "nexus_acceptance_check",
            "--project-root", str(tmp_path),
            "--output-dir", str(reports_dir),
            "--learning-gate-mode", mode
        ]
        
        with mock.patch("sys.argv", test_args), \
             mock.patch("scripts.ops.nexus_acceptance_check.build_skills_health", return_value=health_mock):
            
            try:
                ret = nac.main()
            except SystemExit as exc:
                ret = exc.code
                
        passed = (ret == 0)
        
        # Load final report
        report_data = json.loads((reports_dir / "acceptance_check.json").read_text())
        
        print(f"[{name}]")
        print(f"  Mode: {mode}")
        print(f"  Risk: {'High' if is_high_risk else 'Low'}")
        print(f"  Health: Ready={ready}, Heal={heal_eff}, Gain={learn_gain}")
        print(f"  Expected Pass: {expected_pass} | Actual Pass: {passed}")
        assert passed == expected_pass, f"Test {name} failed: expected {expected_pass}, got {passed}"
        
        # Verify JSON
        if not expected_pass:
            # Should have blocked
            assert report_data["gate_passed"] is False
            assert "stage2_deferred_warning" in report_data and not report_data["stage2_deferred_warning"]
        else:
            if mode == "soft_block":
                # Must be WARN_DEFERRED since warning occurred but blocked was deferred
                assert report_data["stage2_deferred_warning"] is True
                assert report_data["gate_passed"] is True
            

if __name__ == "__main__":
    print("Testing Stage 2 Overlay...")
    
    # 1. 低風險 + warning => PASS / WARN_DEFERRED
    run_test_case("Case 1: Low Risk with Warning", "soft_block", is_high_risk=False, ready=False, heal_eff=10.0, learn_gain=10.0, expected_pass=True)
    
    # 2. 高風險 + 健康穩健 => PASS / WARN_DEFERRED
    run_test_case("Case 2: High Risk but Healthy", "soft_block", is_high_risk=True, ready=True, heal_eff=90.0, learn_gain=80.0, expected_pass=True)
    
    # 3. 高風險 + 健康衰退 => BLOCK (FAIL)
    run_test_case("Case 3: High Risk and Unhealthy (Ready=False)", "soft_block", is_high_risk=True, ready=False, heal_eff=90.0, learn_gain=80.0, expected_pass=False)
    run_test_case("Case 4: High Risk and Unhealthy (Heal<50)", "soft_block", is_high_risk=True, ready=True, heal_eff=40.0, learn_gain=80.0, expected_pass=False)
    run_test_case("Case 5: High Risk and Unhealthy (Gain<40)", "soft_block", is_high_risk=True, ready=True, heal_eff=90.0, learn_gain=30.0, expected_pass=False)
    
    print("\n✅ All Stage 2 Policy Tests Passed Perfectly!")
