from pathlib import Path


def test_delivery_gate_claim_verifier_requires_report_test_evidence():
    script = Path("scripts/ops/nexus_delivery_gate.sh").read_text(encoding="utf-8")
    assert 'AGENT_REPORT_PATH=".nexus/reports/agent_report.json"' in script
    assert '--report-file "$AGENT_REPORT_PATH"' in script
    assert '--report-newer-than "$EVIDENCE_PATH"' in script
    assert "--require-test-evidence" in script
