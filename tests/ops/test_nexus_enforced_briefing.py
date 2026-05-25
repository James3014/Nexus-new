import subprocess
from pathlib import Path


def _render_briefing(tmp_path: Path) -> str:
    out_file = tmp_path / "enforced_agent_briefing.md"
    result = subprocess.run(
        ["bash", "scripts/ops/_nexus_enforced_briefing.sh", str(out_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert str(out_file) in result.stdout
    return out_file.read_text(encoding="utf-8")


def test_enforced_briefing_requires_bootstrap_before_active(tmp_path):
    briefing = _render_briefing(tmp_path)

    assert briefing.splitlines()[0] == "[NEXUS v26 BOOTSTRAP-CANDIDATE]"
    assert "[NEXUS v26 ACTIVE]" in briefing
    assert "[NEXUS v24 ACTIVE]" not in briefing
    assert "[NEXUS v22 ACTIVE]" not in briefing


def test_enforced_briefing_blocks_report_trust_overclaims(tmp_path):
    briefing = _render_briefing(tmp_path)

    assert "FAIL_CLOSED != SUCCESS" in briefing
    assert "INFRA_INVALID" in briefing
    assert "ROOT_ARTIFACT_LEAK" in briefing
    assert "Do not kill/stash/restore/clean ambiguous targets" in briefing
    assert "deterministic local rescue profile" in briefing
    assert "selected-only" in briefing


def test_committed_protocol_matches_runtime_briefing_guardrails():
    protocol = Path("docs/AGENT_MANDATORY_PROTOCOL.md").read_text(encoding="utf-8")

    assert "v2.9" in protocol
    assert "[NEXUS v26 BOOTSTRAP-CANDIDATE]" in protocol
    assert "FAIL_CLOSED != SUCCESS" in protocol
    assert "INFRA_INVALID" in protocol
    assert "ROOT_ARTIFACT_LEAK" in protocol


def test_gemini_round_runner_uses_enforced_briefing_not_legacy_active_preamble():
    runner = Path("scripts/ops/run_gemini_nexus_round.sh").read_text(encoding="utf-8")

    assert "[NEXUS v22 ACTIVE]" not in runner
    assert "_nexus_enforced_briefing.sh" in runner
    assert 'cat "$BRIEFING_PATH"' in runner
    assert "NEXUS_BOOTSTRAP_INCOMPLETE" in runner
