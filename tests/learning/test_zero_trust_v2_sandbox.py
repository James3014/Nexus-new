from __future__ import annotations

from nexus.learning.zero_trust_v2_sandbox import build_mock_sandbox_attestation, validate_sandbox_attestation


def test_mock_sandbox_attestation_is_diagnostic_only_by_default() -> None:
    attestation = build_mock_sandbox_attestation(artifact_hash="artifact")

    verdict = validate_sandbox_attestation(attestation)

    assert verdict["status"] == "BLOCKED"
    assert verdict["reasons"] == ["mocked_sandbox_non_promotion"]


def test_network_enabled_blocks_promotion() -> None:
    attestation = {
        **build_mock_sandbox_attestation(artifact_hash="artifact"),
        "sandbox_mode": "macos_sandbox",
        "network_disabled": False,
    }

    verdict = validate_sandbox_attestation(attestation)

    assert verdict["status"] == "BLOCKED"
    assert "network_not_disabled" in verdict["reasons"]


def test_blocked_physical_sandbox_status_blocks_promotion() -> None:
    attestation = {
        **build_mock_sandbox_attestation(artifact_hash="artifact"),
        "sandbox_mode": "macos_sandbox",
        "status": "BLOCKED",
    }

    verdict = validate_sandbox_attestation(attestation)

    assert verdict["status"] == "BLOCKED"
    assert "sandbox_status_not_pass" in verdict["reasons"]


def test_teardown_fail_blocks_and_marks_reason() -> None:
    attestation = {
        **build_mock_sandbox_attestation(artifact_hash="artifact", teardown_status="FAIL"),
        "sandbox_mode": "linux_cgroup",
    }

    verdict = validate_sandbox_attestation(attestation)

    assert verdict["status"] == "BLOCKED"
    assert "teardown_not_pass" in verdict["reasons"]


def test_approved_sandbox_mode_can_pass() -> None:
    attestation = {
        **build_mock_sandbox_attestation(artifact_hash="artifact"),
        "sandbox_mode": "linux_cgroup",
        "signature": "runner-signature",
    }

    verdict = validate_sandbox_attestation(attestation)

    assert verdict == {"status": "PASS", "reasons": [], "sandbox_mode": "linux_cgroup"}
