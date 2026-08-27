from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_g12_fast_start_advisory_cache_gate_is_mandatory():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")

    for text in (agents, contract):
        assert "G12 Fast Start advisory-cache gate" in text
        assert "#549" in text
        assert "ADVISORY_CACHE_ONLY" in text
        assert "BLOCKED" in text
        assert "HOST_REBIND_REQUIRED" in text
        assert "NEEDS_DECISION" in text
        assert "EVIDENCE_BLOCKED" in text
        assert "READY_CANDIDATE" in text
        assert "metadata-only" in text
        assert "source/test" in text
        assert "fail" in text.lower()

    assert "before any GitHub Issue implementation" in agents
    assert "must not read diff, patch" in agents
    assert "Fast Start consumers are read-only" in agents

    assert "before any implementation source/test body reads" in contract
    assert "must not read\n  diff, patch" in contract
    assert "Fast Start consumers are read-only" in contract
