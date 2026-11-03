from __future__ import annotations

from nexus.learning.zero_trust_v2_physical_runner import run_zero_trust_v2_physical_rows
from nexus.learning.zero_trust_v2_sandbox import (
    build_mock_sandbox_attestation,
    sandbox_attestation_signature,
)


def _signed(attestation: dict, signing_secret: str) -> dict:
    """The attestation as the runner issues it: signed over every field but the signature."""
    body = {key: value for key, value in attestation.items() if key != "signature"}
    return {
        **body,
        "signature": sandbox_attestation_signature(
            attestation_body=body, signing_secret=signing_secret
        ),
    }


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
        "sandbox_attestation": _signed(
            {
                **build_mock_sandbox_attestation(artifact_hash="artifact"),
                "sandbox_mode": "macos_sandbox",
                "status": "PASS",
                "raw_observation": {"returncode": 0},
            },
            signing_secret,
        ),
    }


def _workspace_probe(command: list[str], *, signing_secret: str, workspace_files: dict[str, str] | None = None) -> dict:
    assert workspace_files == {"SKILL.md": "# Safe\n"}
    return _passing_probe(command, signing_secret=signing_secret)


def _blocked_probe(command: list[str], *, signing_secret: str, **_: object) -> dict:
    return {
        "status": "BLOCKED",
        "promotion_eligible": False,
        "sandbox_attestation": _signed(
            {
                **build_mock_sandbox_attestation(artifact_hash="artifact", network_disabled=False),
                "sandbox_mode": "macos_sandbox",
                "status": "BLOCKED",
                "raw_observation": {"returncode": 71, "sandbox_apply_failed": True},
            },
            signing_secret,
        ),
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


def _tampered_probe(command: list[str], *, signing_secret: str, **_: object) -> dict:
    """A passing attestation whose signature does not match its body."""
    probe = _passing_probe(command, signing_secret=signing_secret)
    probe["sandbox_attestation"] = {
        **probe["sandbox_attestation"],
        "artifact_hash": "another-artifact",
    }
    return probe


def test_zero_trust_v2_physical_rows_block_an_attestation_whose_signature_does_not_match() -> None:
    """#3229: the runner verifies the attestation signature with its own secret."""
    rows = [_row("candidate_skill_v2"), _row("wrong_or_quarantined_skill_v2")]

    result = run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/echo", "ok"],
        signing_secret="secret",
        run_id="run-1",
        promotion_credit_allowed=True,
        sandbox_probe=_tampered_probe,
    )

    candidate = next(row for row in result if row["arm_type"] == "candidate_skill_v2")
    assert candidate["v2_evidence_count"] == 0
    assert candidate["promotion_evaluation"]["status"] == "BLOCKED"


def _credit_rows(secret: str):
    def probe(command, *, signing_secret, **_):
        return _passing_probe(command, signing_secret="secret") | {
            "sandbox_attestation": _signed(
                {
                    **build_mock_sandbox_attestation(artifact_hash="artifact"),
                    "sandbox_mode": "macos_sandbox",
                    "status": "PASS",
                    "raw_observation": {"returncode": 0},
                },
                secret,
            )
        }

    rows = [_row("candidate_skill_v2"), _row("wrong_or_quarantined_skill_v2")]
    return run_zero_trust_v2_physical_rows(
        rows,
        command=["/bin/echo", "ok"],
        signing_secret=secret,
        run_id="run-1",
        promotion_credit_allowed=True,
        sandbox_probe=probe,
    )


def test_report_built_with_the_default_secret_is_not_promotion_eligible() -> None:
    result = _credit_rows("local-nonproduction-v2-physical-runner")

    candidate = next(row for row in result if row["arm_type"] == "candidate_skill_v2")
    assert candidate["promotion_evaluation"]["status"] == "BLOCKED"
    assert "nonproduction_signing_secret" in candidate["promotion_evaluation"]["reasons"]


def test_report_built_with_a_real_secret_is_still_promotion_eligible() -> None:
    result = _credit_rows("fake-real-secret-3249")

    candidate = next(row for row in result if row["arm_type"] == "candidate_skill_v2")
    assert candidate["promotion_evaluation"]["status"] == "READY_FOR_MANUAL_APPLY"
