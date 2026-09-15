from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_g12_fast_start_advisory_cache_gate_is_mandatory():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    contract = (ROOT / "docs/agents/TASK_EXECUTION_CONTRACT.md").read_text(encoding="utf-8")

    for term in (
        "G12 Fast Start advisory-cache gate",
        "#549",
        "ADVISORY_CACHE_ONLY",
        "BLOCKED",
        "HOST_REBIND_REQUIRED",
        "NEEDS_DECISION",
        "EVIDENCE_BLOCKED",
        "READY_CANDIDATE",
        "metadata-only",
        "source/test",
    ):
        assert term in agents

    assert "before any GitHub Issue implementation" in agents
    assert "must not read diff, patch" in agents
    assert "fails closed to normal authoritative discovery" in agents
    assert "Fast Start consumers are read-only" in agents

    assert "G12 Fast Start advisory-cache gate" in contract
    assert "#549" in contract
    assert "ADVISORY_CACHE_ONLY" in contract
    assert "before any implementation source/test body reads" in contract
    assert "root `AGENTS.md`" in contract
