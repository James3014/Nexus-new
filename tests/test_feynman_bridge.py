import os
import sys
import json
from pathlib import Path
import pytest

# Ensure scripts can be imported
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.ops.feynman_bridge import ComplexityRouter, DualTrackAudit

def test_complexity_router_fast_path():
    router = ComplexityRouter()
    decision, latency = router.route_task({
        "id": "BUG-999",
        "type": "bug",
        "complexity": "low"
    })
    
    assert decision == "FAST_PATH", f"Expected FAST_PATH, got {decision}"
    # SLA Check: P95 Latency protection for simple bugs
    assert latency < 0.05, f"SLA Violation: Routing latency too high ({latency:.5f}s)"

def test_complexity_router_deep_path():
    router = ComplexityRouter()
    decision, latency = router.route_task({
        "id": "ARCH-001",
        "type": "arch",
        "complexity": "critical"
    })
    
    assert decision == "DEEP_PATH", f"Expected DEEP_PATH, got {decision}"

def test_dual_track_audit_observe_only():
    auditor = DualTrackAudit()
    
    # Simulate a PR diff that contains logical drift (TODOs left)
    mock_diff = "+ def new_func():\n+    # TODO: implement feynman logic"
    mock_spec = "Implement feynman logic correctly without TODOs."
    
    findings = auditor.run_advisory_audit(mock_diff, mock_spec)
    
    assert findings["status"] == "WARN", "Expected advisory WARN status for unresolved TODOs"
    assert "TODO" in findings["warnings"][0], "Expected TODO warning in findings"
    
    # Check if SOC2 compliance file was generated
    audit_dir = REPO_ROOT / "compliance" / "audit"
    files = list(audit_dir.glob("feynman_warnings_*.json"))
    assert len(files) > 0, "Expected a compliance warning JSON file to be generated"
    
    # Verify content
    with open(files[-1], "r") as f:
        data = json.load(f)
        assert data["status"] == "WARN"

def test_dual_track_audit_pass():
    auditor = DualTrackAudit()
    
    mock_diff = "+ def clean_func():\n+    return True"
    mock_spec = "Clean function."
    
    findings = auditor.run_advisory_audit(mock_diff, mock_spec)
    assert findings["status"] == "PASS"
