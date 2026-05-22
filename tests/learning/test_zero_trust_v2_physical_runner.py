from __future__ import annotations

from nexus.learning.zero_trust_v2_physical_runner import run_zero_trust_v2_physical_rows
from nexus.learning.zero_trust_v2_sandbox import build_mock_sandbox_attestation


def _row(arm_type: str) -> dict:
    return {
        "row_id": f"row-{arm_type}",
        "capability_id": "codeintel",
        "skill_id": "code-skill",
        "source_skill_id": "code-skill",
        "arm_type": arm_type,
        "security_contract_version": "v2",
        "promotion_credit_source": "v2_only",
    }


def _passing_probe(command: list[str], *, signing_secret: str, **_: object) -> dict:
    assert command == ["/bin/echo", "ok"]
    assert signing_secret == "secret"
    return {
        "status": "PASS",
        "promotion_eligible": True,
        "sandbox_attestation": {
            **build_mock_sandbox_attestation(artifact_hash="artifact"),
            "sandbox_mode": "macos_sandbox",
            "status": "PASS",
            "signature": "runner-signature",
            "raw_observation": {"returncode": 0},
        },
    }


def _workspace_probe(command: list[str], *, signing_secret: str, workspace_files: dict[str, str] | None = None) -> dict:
    assert workspace_files == {"SKILL.md": "# Safe\n"}
    return _passing_probe(command, signing_secret=signing_secret)


def _blocked_probe(command: list[str], *, signing_secret: str, **_: object) -> dict:
    return {
        "status": "BLOCKED",
        "promotion_eligible": False,
        "sandbox_attestation": {
            **build_mock_sandbox_attestation(artifact_hash="artifact", network_disabled=False),
            "sandbox_mode": "macos_sandbox",
            "status": "BLOCKED",
            "signature": "runner-signature",
            "raw_observation": {"returncode": 71, "sandbox_apply_failed": True},
        },
    }


def test_zero_trust_v2_physical_rows_can_reach_manual_apply_ready_with_complete_evidence() -> None:
    rows = [
        _row("capability_only_v2"),
        _row("candidate_skill_v2"),
        _row("wrong_or_quarantined_skill_v2"),
        _row("shadow_candidate_v2"),
    ]

    result = run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        run_id="run-1",
        promotion_credit_allowed=True,
        sandbox_probe=_passing_probe,
    )

    by_arm = {row["arm_type"]: row for row in result}
    assert by_arm["wrong_or_quarantined_skill_v2"]["execution_status"] == "BLOCKED_BY_POLICY"
    assert by_arm["candidate_skill_v2"]["v2_evidence_count"] == 1
    assert by_arm["candidate_skill_v2"]["negative_control_blocked_count"] == 1
    assert by_arm["candidate_skill_v2"]["promotion_evaluation"]["status"] == "READY_FOR_MANUAL_APPLY"
    assert by_arm["shadow_candidate_v2"]["promotion_evaluation"]["status"] == "READY_FOR_MANUAL_APPLY"


def test_zero_trust_v2_physical_rows_default_to_probe_only_no_promotion_credit() -> None:
    rows = [_row("candidate_skill_v2"), _row("wrong_or_quarantined_skill_v2")]

    result = run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        run_id="run-1",
        sandbox_probe=_passing_probe,
    )

    candidate = next(row for row in result if row["arm_type"] == "candidate_skill_v2")
    assert candidate["execution_status"] == "PASS"
    assert candidate["probe_only"] is True
    assert candidate["v2_evidence_count"] == 0
    assert candidate["promotion_evaluation"]["status"] == "BLOCKED"
    assert "insufficient_v2_evidence" in candidate["promotion_evaluation"]["reasons"]


def test_zero_trust_v2_physical_rows_keep_candidate_blocked_when_sandbox_blocks() -> None:
    rows = [_row("candidate_skill_v2"), _row("wrong_or_quarantined_skill_v2")]

    result = run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        run_id="run-1",
        sandbox_probe=_blocked_probe,
    )

    candidate = next(row for row in result if row["arm_type"] == "candidate_skill_v2")
    assert candidate["execution_status"] == "BLOCKED_BY_POLICY"
    assert candidate["v2_evidence_count"] == 0
    assert candidate["negative_control_blocked_count"] == 1
    assert candidate["promotion_evaluation"]["status"] == "BLOCKED"
    assert "sandbox_attestation_not_pass" in candidate["promotion_evaluation"]["reasons"]


def test_zero_trust_v2_physical_rows_pass_workspace_files_to_probe() -> None:
    rows = [_row("candidate_skill_v2"), _row("wrong_or_quarantined_skill_v2")]

    result = run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        run_id="run-1",
        workspace_files_by_key={("codeintel", "code-skill"): {"SKILL.md": "# Safe\n"}},
        sandbox_probe=_workspace_probe,
    )

    candidate = next(row for row in result if row["arm_type"] == "candidate_skill_v2")
    assert candidate["execution_status"] == "PASS"
