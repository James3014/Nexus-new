from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nexus.contracts.break_glass_recovery import (
    BreakGlassActivationPayload,
    BreakGlassContractError,
    BreakGlassEffectClass,
    OwnerActivationEnvelope,
    canonical_sha256,
    owner_envelope_from_github_comment,
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


def test_relative_path_escape_is_rejected() -> None:
    data = activation_dict()
    data["allowed_paths"] = ["../outside"]
    with pytest.raises(ValidationError, match="PATH_INVALID"):
        BreakGlassActivationPayload.model_validate(data)
