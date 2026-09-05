from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.break_glass_recovery import (
    BreakGlassActivationPayload,
    BreakGlassContractError,
    BreakGlassEffectClass,
    BreakGlassOwnerIntegrationPayload,
    BreakGlassOwnerTerminalPayload,
    BreakGlassOwnerVerificationPayload,
    OwnerActivationEnvelope,
    canonical_sha256,
    integration_readback_from_github,
    owner_envelope_from_github_comment,
    owner_integration_from_github_comment,
    owner_terminal_from_github_comment,
    owner_terminals_from_github_comments,
    owner_verification_from_github_comment,
)

EXPECTED_PAYLOAD_SHA256 = "d2313d38c4b15d16cf42497c267bd7071195bf3f58f485eea6d659ded6e09a95"


def activation_dict() -> dict[str, object]:
    return {
        "allowed_paths": [
            "docs/agents/TASK_EXECUTION_CONTRACT.md",
            "docs/governance/current_operating_mode.yaml",
            "docs/governance/rollback_runbook.md",
            "docs/specs/NEXUS_BREAK_GLASS_RECOVERY_001.md",
            "nexus/contracts/break_glass_recovery.py",
            "nexus/orchestrator/break_glass_recovery.py",
            "scripts/ops/break_glass_recovery.py",
            "tests/contracts/test_break_glass_recovery_contract.py",
            "tests/nexus/orchestrator/test_break_glass_recovery.py",
        ],
        "attempt_id": "BG-806-A1",
        "base_sha": "8e8e02911c888d4c8a4667d4b5dd13df85c20cfd",
        "base_tree": "78da10b2402f8c25f4d04ae5b470e7c10bd984f7",
        "claim_ceiling": "break_glass_source_candidate_only",
        "effect_class": "SOURCE_REPAIR",
        "expires_at": "2026-09-06T23:00:00+08:00",
        "failure_class": "GOVERNANCE_PLANE_RECOVERY_REQUIRED",
        "failure_evidence_sha256": "dc69ec5c42111fc37a6effefd8301a0ab8ee2bd55294d08cc69af872ec1d4ee8",
        "forbidden_paths": [
            ".git",
            "nexus/orchestrator/standing_grant_store.py",
            "nexus/orchestrator/unified_mcp_gateway.py",
            "scripts/ops/mcp_gateway_durable.py",
        ],
        "issue": 806,
        "issued_at": "2026-09-06T06:55:00+08:00",
        "owner_login": "James3014",
        "recovery_id": "BG-806-20260906",
        "repository": "James3014/Nexus-new",
        "schema": "nexus.break_glass_owner_activation.v1",
        "verifier_commands": [
            "python3 -m pytest tests/contracts/test_break_glass_recovery_contract.py tests/nexus/orchestrator/test_break_glass_recovery.py -q",
            "python3 -m pytest tests/nexus/orchestrator/test_standing_grant_store.py tests/ops/test_bootstrap_authority_files.py -q",
            "python3 -m py_compile nexus/contracts/break_glass_recovery.py nexus/orchestrator/break_glass_recovery.py scripts/ops/break_glass_recovery.py",
            "git diff --check",
        ],
    }


def envelope_dict() -> dict[str, object]:
    return {
        "schema": "nexus.break_glass_owner_comment_envelope.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 5555340739,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-5555340739",
        "author_login": "James3014",
        "comment_body_sha256": "5" * 64,
        "payload_sha256": EXPECTED_PAYLOAD_SHA256,
        "payload": activation_dict(),
    }


def test_real_owner_activation_payload_hash_is_frozen() -> None:
    payload = BreakGlassActivationPayload.model_validate(activation_dict())
    assert payload.payload_sha256 == EXPECTED_PAYLOAD_SHA256
    envelope = OwnerActivationEnvelope.model_validate(envelope_dict())
    assert envelope.payload.attempt_id == "BG-806-A1"
    assert envelope.payload.effect_class is BreakGlassEffectClass.SOURCE_REPAIR


def raw_github_comment() -> dict[str, object]:
    payload = activation_dict()
    body = (
        "## `BREAK_GLASS_G1` — Owner recovery activation / SOURCE_REPAIR\n\n"
        f"Canonical activation payload SHA-256: `{canonical_sha256(payload)}`\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n```\n"
    )
    return {
        "id": 5555340739,
        "html_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-5555340739",
        "issue_url": "https://api.github.com/repos/James3014/Nexus-new/issues/806",
        "user": {"login": "James3014"},
        "body": body,
    }


def test_raw_github_comment_is_independently_parsed_and_bound() -> None:
    envelope = owner_envelope_from_github_comment(raw_github_comment())
    assert envelope.comment_id == 5555340739
    assert envelope.author_login == "James3014"
    assert envelope.payload_sha256 == EXPECTED_PAYLOAD_SHA256
    assert len(envelope.comment_body_sha256) == 64


def test_raw_github_comment_forged_owner_is_rejected() -> None:
    comment = raw_github_comment()
    comment["user"] = {"login": "worker-model"}
    with pytest.raises(BreakGlassContractError, match="GITHUB_COMMENT_OWNER_MISMATCH"):
        owner_envelope_from_github_comment(comment)


def test_raw_github_comment_body_payload_tamper_is_rejected() -> None:
    comment = raw_github_comment()
    body = str(comment["body"])
    comment["body"] = body.replace("8e8e02911c888d4c8a4667d4b5dd13df85c20cfd", "0" * 40)
    with pytest.raises(BreakGlassContractError, match="GITHUB_COMMENT_PAYLOAD_HASH_MISMATCH"):
        owner_envelope_from_github_comment(comment)


def test_forged_owner_is_rejected() -> None:
    data = envelope_dict()
    data["author_login"] = "worker-model"
    with pytest.raises(ValidationError):
        OwnerActivationEnvelope.model_validate(data)


def test_payload_tamper_is_rejected_by_hash() -> None:
    data = envelope_dict()
    payload = dict(data["payload"])  # type: ignore[arg-type]
    payload["claim_ceiling"] = "break_glass_source_candidate_only"
    payload["base_sha"] = "0" * 40
    data["payload"] = payload
    with pytest.raises(ValidationError, match="PAYLOAD_HASH_MISMATCH"):
        OwnerActivationEnvelope.model_validate(data)


def test_comment_identity_swap_is_rejected() -> None:
    data = envelope_dict()
    data["comment_id"] = 5555340740
    with pytest.raises(ValidationError, match="COMMENT_ID_URL_MISMATCH"):
        OwnerActivationEnvelope.model_validate(data)


def test_activation_expiry_and_not_yet_valid_fail_closed() -> None:
    payload = BreakGlassActivationPayload.model_validate(activation_dict())
    with pytest.raises(BreakGlassContractError, match="ACTIVATION_NOT_YET_VALID"):
        payload.assert_current(now=datetime(2026, 9, 5, 22, 54, tzinfo=timezone.utc))
    with pytest.raises(BreakGlassContractError, match="ACTIVATION_EXPIRED"):
        payload.assert_current(now=datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc))


def test_source_activation_cannot_be_substituted_for_runtime_or_integration() -> None:
    for effect in ("EMERGENCY_INTEGRATION", "RUNTIME_RECOVERY"):
        data = activation_dict()
        data["effect_class"] = effect
        with pytest.raises(ValidationError, match="SOURCE_REPAIR_AUTHORITY_REQUIRED"):
            BreakGlassActivationPayload.model_validate(data)


def test_scope_widening_and_forbidden_path_fail_closed() -> None:
    payload = BreakGlassActivationPayload.model_validate(activation_dict())
    with pytest.raises(BreakGlassContractError, match="OUT_OF_SCOPE_PATH_CHANGED"):
        payload.assert_paths_authorized(("README.md",))
    with pytest.raises(BreakGlassContractError, match="FORBIDDEN_PATH_CHANGED"):
        payload.assert_paths_authorized(("nexus/orchestrator/standing_grant_store.py",))


def verification_payload_dict() -> dict[str, object]:
    return {
        "schema": "nexus.break_glass_owner_verification.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": "BG-806-20260906",
        "source_attempt_id": "BG-806-A1",
        "source_activation_payload_sha256": EXPECTED_PAYLOAD_SHA256,
        "verified_commit_sha": "1" * 40,
        "verified_tree_sha": "2" * 40,
        "verified_diff_sha256": "3" * 64,
        "verifier_id": "primary-coordinator",
        "checks": [
            {
                "schema": "nexus.break_glass_check_evidence.v1",
                "name": "Nexus Exact-Base Ruff CI",
                "run_id": 1001,
                "head_sha": "1" * 40,
                "conclusion": "success",
            },
            {
                "schema": "nexus.break_glass_check_evidence.v1",
                "name": "Nexus Pytest CI",
                "run_id": 1002,
                "head_sha": "1" * 40,
                "conclusion": "success",
            },
        ],
        "issued_at": "2026-09-06T07:00:00+08:00",
        "expires_at": "2026-09-06T23:00:00+08:00",
        "claim_ceiling": "source_repair_verification_only",
    }


def integration_payload_dict() -> dict[str, object]:
    verification = verification_payload_dict()
    verification_hash = canonical_sha256(verification)
    return {
        "schema": "nexus.break_glass_owner_integration.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": "BG-806-20260906",
        "integration_attempt_id": "BG-806-I1",
        "source_attempt_id": "BG-806-A1",
        "source_activation_payload_sha256": EXPECTED_PAYLOAD_SHA256,
        "verification_payload_sha256": verification_hash,
        "effect_class": "EMERGENCY_INTEGRATION",
        "pr_number": 808,
        "accepted_head_sha": "1" * 40,
        "accepted_tree_sha": "2" * 40,
        "accepted_diff_sha256": "3" * 64,
        "expected_base_sha": "8e8e02911c888d4c8a4667d4b5dd13df85c20cfd",
        "merge_method": "merge",
        "checks": verification["checks"],
        "issued_at": "2026-09-06T07:05:00+08:00",
        "expires_at": "2026-09-06T23:00:00+08:00",
        "claim_ceiling": "emergency_integration_only",
    }


def raw_owner_evidence_comment(
    *, marker: str, payload: dict[str, object], comment_id: int
) -> dict[str, object]:
    body = (
        f"{marker}: `{canonical_sha256(payload)}`\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n```\n"
    )
    return {
        "id": comment_id,
        "html_url": (
            f"https://github.com/James3014/Nexus-new/issues/806#issuecomment-{comment_id}"
        ),
        "issue_url": "https://api.github.com/repos/James3014/Nexus-new/issues/806",
        "user": {"login": "James3014"},
        "body": body,
    }


def test_owner_verification_comment_binds_successful_exact_head_checks() -> None:
    payload = verification_payload_dict()
    parsed = owner_verification_from_github_comment(
        raw_owner_evidence_comment(
            marker="Canonical verification payload SHA-256",
            payload=payload,
            comment_id=6000000001,
        )
    )
    assert isinstance(parsed.payload, BreakGlassOwnerVerificationPayload)
    assert parsed.payload.verified_commit_sha == "1" * 40
    assert {item.conclusion for item in parsed.payload.checks} == {"success"}


def test_verification_check_subject_substitution_is_rejected() -> None:
    payload = verification_payload_dict()
    checks = list(payload["checks"])  # type: ignore[arg-type]
    checks[0] = {**checks[0], "head_sha": "4" * 40}  # type: ignore[arg-type]
    payload["checks"] = checks
    with pytest.raises(ValidationError, match="CHECK_SUBJECT_MISMATCH"):
        BreakGlassOwnerVerificationPayload.model_validate(payload)


def test_owner_integration_comment_is_separate_exact_effect_authority() -> None:
    payload = integration_payload_dict()
    parsed = owner_integration_from_github_comment(
        raw_owner_evidence_comment(
            marker="Canonical integration payload SHA-256",
            payload=payload,
            comment_id=6000000002,
        )
    )
    assert isinstance(parsed.payload, BreakGlassOwnerIntegrationPayload)
    assert parsed.payload.effect_class == "EMERGENCY_INTEGRATION"
    assert parsed.payload.pr_number == 808
    assert parsed.payload.claim_ceiling == "emergency_integration_only"


def test_integration_comment_tamper_is_rejected_by_canonical_hash() -> None:
    payload = integration_payload_dict()
    comment = raw_owner_evidence_comment(
        marker="Canonical integration payload SHA-256",
        payload=payload,
        comment_id=6000000002,
    )
    comment["body"] = str(comment["body"]).replace('"pr_number":808', '"pr_number":809')
    with pytest.raises(BreakGlassContractError, match="GITHUB_COMMENT_PAYLOAD_HASH_MISMATCH"):
        owner_integration_from_github_comment(comment)


def terminal_payload_dict(*, state: str = "CONSUMED") -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "nexus.break_glass_owner_terminal.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": "BG-806-20260906",
        "source_attempt_id": "BG-806-A1",
        "source_activation_payload_sha256": EXPECTED_PAYLOAD_SHA256,
        "terminal_state": state,
        "reason": "normal-governance-restored-after-pr-808",
        "issued_at": "2026-09-06T08:00:00+08:00",
    }
    if state == "CONSUMED":
        payload.update({
            "integrated_main_sha": "8" * 40,
            "canary_evidence_sha256": "9" * 64,
            "integration_payload_sha256": "a" * 64,
        })
    return payload


def github_integration_readback(
    *,
    merged: bool = True,
    state: str = "closed",
    head_sha: str = "1" * 40,
    merge_sha: str = "8" * 40,
    main_sha: str = "8" * 40,
) -> tuple[dict[str, object], dict[str, object]]:
    pull_request = {
        "number": 808,
        "state": state,
        "merged": merged,
        "merge_commit_sha": merge_sha,
        "head": {"sha": head_sha},
        "base": {"ref": "main"},
    }
    main_branch = {"commit": {"sha": main_sha}}
    return pull_request, main_branch


def test_github_integration_readback_binds_merged_pr_head_and_main() -> None:
    integration = BreakGlassOwnerIntegrationPayload.model_validate(integration_payload_dict())
    pull_request, main_branch = github_integration_readback()
    assert integration_readback_from_github(integration, pull_request, main_branch) == (
        "8" * 40,
        "8" * 40,
        808,
    )


def test_github_integration_readback_rejects_unmerged_or_head_substitution() -> None:
    integration = BreakGlassOwnerIntegrationPayload.model_validate(integration_payload_dict())
    pull_request, main_branch = github_integration_readback(merged=False, state="open")
    with pytest.raises(BreakGlassContractError, match="GITHUB_PR_NOT_MERGED"):
        integration_readback_from_github(integration, pull_request, main_branch)
    pull_request, main_branch = github_integration_readback(head_sha="7" * 40)
    with pytest.raises(BreakGlassContractError, match="INTEGRATION_HEAD_READBACK_MISMATCH"):
        integration_readback_from_github(integration, pull_request, main_branch)


def test_github_integration_readback_rejects_main_mismatch() -> None:
    integration = BreakGlassOwnerIntegrationPayload.model_validate(integration_payload_dict())
    pull_request, main_branch = github_integration_readback(main_sha="9" * 40)
    with pytest.raises(BreakGlassContractError, match="INTEGRATION_READBACK_MISMATCH"):
        integration_readback_from_github(integration, pull_request, main_branch)


def test_owner_terminal_comment_binds_global_consumption() -> None:
    payload = terminal_payload_dict()
    parsed = owner_terminal_from_github_comment(
        raw_owner_evidence_comment(
            marker="Canonical terminal payload SHA-256",
            payload=payload,
            comment_id=6000000003,
        )
    )
    assert isinstance(parsed.payload, BreakGlassOwnerTerminalPayload)
    assert parsed.payload.terminal_state == "CONSUMED"
    assert parsed.payload.source_activation_payload_sha256 == EXPECTED_PAYLOAD_SHA256


def test_non_owner_terminal_marker_cannot_dos_global_scan() -> None:
    payload = terminal_payload_dict()
    comment = raw_owner_evidence_comment(
        marker="Canonical terminal payload SHA-256",
        payload=payload,
        comment_id=6000000004,
    )
    comment["user"] = {"login": "external-commenter"}
    assert owner_terminals_from_github_comments((comment,)) == ()


def test_owner_incidental_terminal_marker_without_schema_is_ignored() -> None:
    comment = {
        "id": 6000000005,
        "html_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000005",
        "issue_url": "https://api.github.com/repos/James3014/Nexus-new/issues/806",
        "user": {"login": "James3014"},
        "body": "Canonical terminal payload SHA-256: mentioned only as documentation",
    }
    assert owner_terminals_from_github_comments((comment,)) == ()


def test_owner_malformed_terminal_candidate_fails_closed() -> None:
    payload = terminal_payload_dict()
    comment = raw_owner_evidence_comment(
        marker="Canonical terminal payload SHA-256",
        payload=payload,
        comment_id=6000000006,
    )
    comment["body"] = str(comment["body"]).replace('"terminal_state":"CONSUMED"', "broken")
    with pytest.raises(BreakGlassContractError):
        owner_terminals_from_github_comments((comment,))


def test_consumed_terminal_requires_integrated_main_and_canary() -> None:
    payload = terminal_payload_dict()
    payload.pop("integrated_main_sha")
    with pytest.raises(ValidationError, match="CONSUMED_TERMINAL_EVIDENCE_REQUIRED"):
        BreakGlassOwnerTerminalPayload.model_validate(payload)


def test_terminal_comment_tamper_is_rejected_by_canonical_hash() -> None:
    payload = terminal_payload_dict()
    comment = raw_owner_evidence_comment(
        marker="Canonical terminal payload SHA-256",
        payload=payload,
        comment_id=6000000003,
    )
    comment["body"] = str(comment["body"]).replace(
        '"terminal_state":"CONSUMED"', '"terminal_state":"REVOKED"'
    )
    with pytest.raises(BreakGlassContractError, match="GITHUB_COMMENT_PAYLOAD_HASH_MISMATCH"):
        owner_terminal_from_github_comment(comment)


def test_relative_path_escape_is_rejected() -> None:
    data = activation_dict()
    data["allowed_paths"] = ["../outside"]
    with pytest.raises(ValidationError, match="PATH_INVALID"):
        BreakGlassActivationPayload.model_validate(data)
