from nexus.research.formal_report_service import FormalReportService


def test_formal_report_blocks_pass_without_evidence_receipts():
    out = FormalReportService().build(
        title="ASI experiment",
        hypothesis="semantic judge improves repair selection",
        asi_constraints=[],
        judge_votes=[],
        verification=[],
        route_receipts=[],
    )

    assert out["schema"] == "nexus_formal_report_v1"
    assert out["status"] == "CLAIM_BLOCKED"
    assert "## Evidence Gate" in out["markdown"]
    assert "PASS" not in out["claim_status"]


def test_formal_report_emits_markdown_when_evidence_chain_is_complete():
    out = FormalReportService().build(
        title="ASI experiment",
        hypothesis="semantic judge improves repair selection",
        asi_constraints=[{"blocked_pattern": "flow:retry_delay", "evidence_refs": ["pytest.log"]}],
        judge_votes=[{"judge": "fake", "ranking": ["B", "A"], "reason": "better evidence"}],
        verification=[{"command": "uv run pytest tests/engine/test_autoreason_service.py", "status": "PASS"}],
        route_receipts=[{"name": "llm_judge_panel", "evidence_present": True, "gate_passed": True}],
    )

    assert out["status"] == "READY"
    assert out["claim_status"] == "PASS"
    assert "## Judge Panel" in out["markdown"]
    assert "flow:retry_delay" in out["markdown"]
