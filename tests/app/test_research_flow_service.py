import pytest
from pathlib import Path
from nexus.app import research_flow_service

def test_build_route_returns_complete_fields(tmp_path: Path):
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="Fix flaky timeout",
        task_type="bug",
        candidate_count=2,
        root_cause_confidence=0.4,
        findings_query=None,
    )
    
    assert "should_research" in out
    assert "mode" in out
    assert "reason" in out
    assert "recommended_flow" in out
    assert "explain_payload" in out
    assert out["explain_payload"]["risk"] == "CRITICAL"
