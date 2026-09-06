from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus.contracts.break_glass_recovery import (
    BreakGlassAppliedEvidence,
    BreakGlassGovernanceCanaryEvidence,
    OwnerActivationEnvelope,
    OwnerCanaryEnvelope,
    OwnerIntegrationEnvelope,
    OwnerTerminalEnvelope,
    OwnerVerificationEnvelope,
    canonical_json_bytes,
    canonical_sha256,
)
from nexus.orchestrator.break_glass_recovery import (
    BreakGlassRecoveryError,
    assert_emergency_integration_not_consumed,
    assert_source_not_globally_terminal,
    consume_source_repair_authority,
    inspect_attempt,
    inspect_emergency_integration,
    prepare_emergency_integration,
    prepare_source_repair,
    record_emergency_integration_consumed,
    record_source_repair_applied,
    record_source_repair_verified,
)

NOW = datetime(2026, 9, 6, 0, 0, tzinfo=timezone.utc)
BASE = "8e8e02911c888d4c8a4667d4b5dd13df85c20cfd"
TREE = "78da10b2402f8c25f4d04ae5b470e7c10bd984f7"
COMMIT = "1" * 40
REPAIR_TREE = "2" * 40
DIFF_HASH = "3" * 64
VERIFY_HASH = "4" * 64


def envelope() -> OwnerActivationEnvelope:
    payload = {
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
        "base_sha": BASE,
        "base_tree": TREE,
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
    payload_hash = canonical_sha256(payload)
    assert payload_hash == "d2313d38c4b15d16cf42497c267bd7071195bf3f58f485eea6d659ded6e09a95"
    return OwnerActivationEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 5555340739,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-5555340739",
        "author_login": "James3014",
        "comment_body_sha256": "5" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def applied(
    *, changed_paths: tuple[str, ...] | None = None, implementer: str = "impl"
) -> BreakGlassAppliedEvidence:
    return BreakGlassAppliedEvidence(
        repair_commit_sha=COMMIT,
        repair_tree_sha=REPAIR_TREE,
        full_diff_sha256=DIFF_HASH,
        changed_paths=changed_paths
        or (
            "nexus/contracts/break_glass_recovery.py",
            "nexus/orchestrator/break_glass_recovery.py",
        ),
        implementer_id=implementer,
    )


def verification_envelope(
    *, verifier: str = "primary-coordinator", commit: str = COMMIT
) -> OwnerVerificationEnvelope:
    source = envelope()
    payload = {
        "schema": "nexus.break_glass_owner_verification.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": source.payload.recovery_id,
        "source_attempt_id": source.payload.attempt_id,
        "source_activation_payload_sha256": source.payload_sha256,
        "verified_commit_sha": commit,
        "verified_tree_sha": REPAIR_TREE,
        "verified_diff_sha256": DIFF_HASH,
        "verifier_id": verifier,
        "checks": [
            {
                "schema": "nexus.break_glass_check_evidence.v1",
                "name": "Nexus Exact-Base Ruff CI",
                "run_id": 1001,
                "head_sha": commit,
                "conclusion": "success",
            },
            {
                "schema": "nexus.break_glass_check_evidence.v1",
                "name": "Nexus Pytest CI",
                "run_id": 1002,
                "head_sha": commit,
                "conclusion": "success",
            },
        ],
        "issued_at": "2026-09-06T07:00:00+08:00",
        "expires_at": "2026-09-06T23:00:00+08:00",
        "claim_ceiling": "source_repair_verification_only",
    }
    payload_hash = canonical_sha256(payload)
    return OwnerVerificationEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 6000000001,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000001",
        "author_login": "James3014",
        "comment_body_sha256": "6" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def integration_envelope(
    verification: OwnerVerificationEnvelope,
    *,
    accepted_head: str = COMMIT,
    expected_base: str = BASE,
    verification_payload_sha256: str | None = None,
) -> OwnerIntegrationEnvelope:
    source = envelope()
    payload = {
        "schema": "nexus.break_glass_owner_integration.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": source.payload.recovery_id,
        "integration_attempt_id": "BG-806-I1",
        "source_attempt_id": source.payload.attempt_id,
        "source_activation_payload_sha256": source.payload_sha256,
        "verification_payload_sha256": verification_payload_sha256 or verification.payload_sha256,
        "effect_class": "EMERGENCY_INTEGRATION",
        "pr_number": 808,
        "accepted_head_sha": accepted_head,
        "accepted_tree_sha": REPAIR_TREE,
        "accepted_diff_sha256": DIFF_HASH,
        "expected_base_sha": expected_base,
        "merge_method": "merge",
        "checks": [
            {
                **item.model_dump(mode="json"),
                "head_sha": accepted_head,
            }
            for item in verification.payload.checks
        ],
        "issued_at": "2026-09-06T07:05:00+08:00",
        "expires_at": "2026-09-06T23:00:00+08:00",
        "claim_ceiling": "emergency_integration_only",
    }
    payload_hash = canonical_sha256(payload)
    return OwnerIntegrationEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 6000000002,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000002",
        "author_login": "James3014",
        "comment_body_sha256": "7" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def canary(*, main_sha: str = "8" * 40) -> BreakGlassGovernanceCanaryEvidence:
    source = envelope()
    return BreakGlassGovernanceCanaryEvidence(
        recovery_id=source.payload.recovery_id,
        source_attempt_id=source.payload.attempt_id,
        integrated_main_sha=main_sha,
        source_runtime_identity_sha256="9" * 64,
        action_binding_sha256="a" * 64,
        normal_authority_readback_sha256="b" * 64,
        governance_operation_receipt_sha256="c" * 64,
        verifier_receipt_sha256="d" * 64,
        observed_at=NOW,
        normal_governance_restored=True,
    )


def owner_canary(
    evidence: BreakGlassGovernanceCanaryEvidence | None = None,
    *,
    source_hash: str | None = None,
) -> OwnerCanaryEnvelope:
    source = envelope()
    observed = evidence or canary()
    payload = {
        "schema": "nexus.break_glass_owner_canary.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": observed.recovery_id,
        "source_attempt_id": observed.source_attempt_id,
        "source_activation_payload_sha256": source_hash or source.payload_sha256,
        "integrated_main_sha": observed.integrated_main_sha,
        "source_runtime_identity_sha256": observed.source_runtime_identity_sha256,
        "action_binding_sha256": observed.action_binding_sha256,
        "normal_authority_readback_sha256": observed.normal_authority_readback_sha256,
        "governance_operation_receipt_sha256": observed.governance_operation_receipt_sha256,
        "verifier_receipt_sha256": observed.verifier_receipt_sha256,
        "observed_at": observed.model_dump(mode="json")["observed_at"],
        "normal_governance_restored": True,
        "issued_at": "2026-09-06T08:01:00+08:00",
        "claim_ceiling": "post_recovery_canary_only",
    }
    payload_hash = canonical_sha256(payload)
    return OwnerCanaryEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 6000000007,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000007",
        "author_login": "James3014",
        "comment_body_sha256": "f" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def terminal_envelope(
    *, recovery_id: str = "BG-806-20260906", source_hash: str | None = None
) -> OwnerTerminalEnvelope:
    source = envelope()
    payload = {
        "schema": "nexus.break_glass_owner_terminal.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "recovery_id": recovery_id,
        "source_attempt_id": source.payload.attempt_id,
        "source_activation_payload_sha256": source_hash or source.payload_sha256,
        "terminal_state": "CONSUMED",
        "reason": "normal-governance-restored-after-pr-808",
        "integrated_main_sha": "8" * 40,
        "canary_evidence_sha256": canary().evidence_sha256,
        "integration_payload_sha256": "a" * 64,
        "issued_at": "2026-09-06T08:00:00+08:00",
    }
    payload_hash = canonical_sha256(payload)
    return OwnerTerminalEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 6000000003,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000003",
        "author_login": "James3014",
        "comment_body_sha256": "8" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def test_prepare_is_idempotent_and_binds_exact_base(tmp_path: Path) -> None:
    env = envelope()
    first = prepare_source_repair(
        env,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    second = prepare_source_repair(
        env,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    assert first == second
    assert first["phase"] == "PREPARED"
    assert inspect_attempt(env.payload, state_root=tmp_path)["transition_count"] == 1

    with pytest.raises(BreakGlassRecoveryError, match="BASE_IDENTITY_MISMATCH"):
        prepare_source_repair(
            env,
            observed_base_sha="0" * 40,
            observed_base_tree=TREE,
            now=NOW,
            state_root=tmp_path / "other",
        )


def test_full_chain_requires_independent_verifier_and_denies_replay(tmp_path: Path) -> None:
    env = envelope()
    prepare_source_repair(
        env, observed_base_sha=BASE, observed_base_tree=TREE, now=NOW, state_root=tmp_path
    )
    app = applied(implementer="worker-1")
    record_source_repair_applied(env, app, now=NOW, state_root=tmp_path)

    with pytest.raises(BreakGlassRecoveryError, match="INDEPENDENT_VERIFIER_REQUIRED"):
        record_source_repair_verified(
            env,
            verification_envelope(verifier="worker-1"),
            now=NOW,
            state_root=tmp_path,
        )

    verified = record_source_repair_verified(
        env,
        verification_envelope(verifier="primary-coordinator"),
        now=NOW,
        state_root=tmp_path,
    )
    assert verified["phase"] == "VERIFIED"
    consumed = consume_source_repair_authority(env, owner_canary(), now=NOW, state_root=tmp_path)
    assert consumed["phase"] == "CONSUMED"
    assert consumed["evidence"]["granted_effect"] == "SOURCE_REPAIR_ONLY"
    assert "GITHUB_MERGE" in consumed["evidence"]["excluded_effects"]
    assert "RUNTIME_RECOVERY" in consumed["evidence"]["excluded_effects"]

    with pytest.raises(BreakGlassRecoveryError, match="RECOVERY_REPLAY_DENIED"):
        consume_source_repair_authority(env, owner_canary(), now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="RECOVERY_REPLAY_DENIED"):
        record_source_repair_applied(env, app, now=NOW, state_root=tmp_path)


def test_phase_skips_fail_closed(tmp_path: Path) -> None:
    env = envelope()
    with pytest.raises(BreakGlassRecoveryError, match="PREPARE_REQUIRED"):
        record_source_repair_applied(env, applied(), now=NOW, state_root=tmp_path)
    prepare_source_repair(
        env, observed_base_sha=BASE, observed_base_tree=TREE, now=NOW, state_root=tmp_path
    )
    with pytest.raises(BreakGlassRecoveryError, match="APPLIED_EVIDENCE_REQUIRED"):
        record_source_repair_verified(env, verification_envelope(), now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="VERIFIED_EVIDENCE_REQUIRED"):
        consume_source_repair_authority(env, owner_canary(), now=NOW, state_root=tmp_path)


def test_scope_widening_and_forbidden_change_fail_before_applied_transition(tmp_path: Path) -> None:
    env = envelope()
    prepare_source_repair(
        env, observed_base_sha=BASE, observed_base_tree=TREE, now=NOW, state_root=tmp_path
    )
    with pytest.raises(Exception, match="OUT_OF_SCOPE_PATH_CHANGED"):
        record_source_repair_applied(
            env,
            applied(changed_paths=("README.md",)),
            now=NOW,
            state_root=tmp_path,
        )
    with pytest.raises(Exception, match="FORBIDDEN_PATH_CHANGED"):
        record_source_repair_applied(
            env,
            applied(changed_paths=("nexus/orchestrator/standing_grant_store.py",)),
            now=NOW,
            state_root=tmp_path,
        )
    assert inspect_attempt(env.payload, state_root=tmp_path)["status"] == "PREPARED"


def test_conflicting_retry_is_rejected(tmp_path: Path) -> None:
    env = envelope()
    prepare_source_repair(
        env, observed_base_sha=BASE, observed_base_tree=TREE, now=NOW, state_root=tmp_path
    )
    record_source_repair_applied(env, applied(), now=NOW, state_root=tmp_path)
    conflicting = BreakGlassAppliedEvidence(
        repair_commit_sha="5" * 40,
        repair_tree_sha=REPAIR_TREE,
        full_diff_sha256=DIFF_HASH,
        changed_paths=("nexus/contracts/break_glass_recovery.py",),
        implementer_id="impl",
    )
    with pytest.raises(BreakGlassRecoveryError, match="APPLIED_EVIDENCE_CONFLICT"):
        record_source_repair_applied(env, conflicting, now=NOW, state_root=tmp_path)


def test_verification_subject_substitution_is_rejected(tmp_path: Path) -> None:
    env = envelope()
    prepare_source_repair(
        env, observed_base_sha=BASE, observed_base_tree=TREE, now=NOW, state_root=tmp_path
    )
    record_source_repair_applied(env, applied(), now=NOW, state_root=tmp_path)
    bad = verification_envelope(commit="6" * 40)
    with pytest.raises(BreakGlassRecoveryError, match="VERIFICATION_SUBJECT_MISMATCH"):
        record_source_repair_verified(env, bad, now=NOW, state_root=tmp_path)


def test_emergency_integration_requires_separate_owner_grant_and_denies_replay(
    tmp_path: Path,
) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)

    integration = integration_envelope(verification)
    prepared = prepare_emergency_integration(source, integration, now=NOW, state_root=tmp_path)
    assert prepared["phase"] == "PREPARED"
    assert prepared["effect_class"] == "EMERGENCY_INTEGRATION"
    assert prepared["forbidden_effects"] == [
        "FORCE_PUSH",
        "REF_DELETE",
        "UNRELATED_MERGE",
        "RUNTIME_RECOVERY",
        "RELEASE",
        "PRODUCTION_PUBLIC_CLAIM",
    ]

    merged_main = "8" * 40
    consumed = record_emergency_integration_consumed(
        integration,
        merge_commit_sha=merged_main,
        observed_main_sha=merged_main,
        merged_pr_number=808,
        now=NOW,
        state_root=tmp_path,
    )
    assert consumed["phase"] == "CONSUMED"
    assert consumed["granted_effect"] == "EMERGENCY_INTEGRATION_ONLY"
    assert inspect_emergency_integration(integration, state_root=tmp_path)["status"] == "CONSUMED"
    with pytest.raises(BreakGlassRecoveryError, match="INTEGRATION_REPLAY_DENIED"):
        assert_emergency_integration_not_consumed(integration, state_root=tmp_path)


def test_emergency_integration_requires_verified_source_first(tmp_path: Path) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="VERIFIED_EVIDENCE_REQUIRED"):
        prepare_emergency_integration(
            source,
            integration_envelope(verification),
            now=NOW,
            state_root=tmp_path,
        )


def test_emergency_integration_verification_grant_substitution_fails_closed(
    tmp_path: Path,
) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="INTEGRATION_VERIFICATION_MISMATCH"):
        prepare_emergency_integration(
            source,
            integration_envelope(
                verification,
                verification_payload_sha256="e" * 64,
            ),
            now=NOW,
            state_root=tmp_path,
        )


def test_emergency_integration_remote_readback_is_exact(tmp_path: Path) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)
    integration = integration_envelope(verification)
    prepare_emergency_integration(source, integration, now=NOW, state_root=tmp_path)

    with pytest.raises(BreakGlassRecoveryError, match="INTEGRATION_PR_MISMATCH"):
        record_emergency_integration_consumed(
            integration,
            merge_commit_sha="8" * 40,
            observed_main_sha="8" * 40,
            merged_pr_number=809,
            now=NOW,
            state_root=tmp_path,
        )
    with pytest.raises(BreakGlassRecoveryError, match="INTEGRATION_READBACK_MISMATCH"):
        record_emergency_integration_consumed(
            integration,
            merge_commit_sha="8" * 40,
            observed_main_sha="9" * 40,
            merged_pr_number=808,
            now=NOW,
            state_root=tmp_path,
        )
    assert inspect_emergency_integration(integration, state_root=tmp_path)["status"] == "PREPARED"


def test_source_consumption_rejects_canary_identity_substitution(tmp_path: Path) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)
    bad_data = canary().model_dump(mode="json")
    bad_data["recovery_id"] = "BG-OTHER"
    bad_canary = BreakGlassGovernanceCanaryEvidence.model_validate(bad_data)
    with pytest.raises(BreakGlassRecoveryError, match="GOVERNANCE_CANARY_AUTHORITY_MISMATCH"):
        consume_source_repair_authority(
            source, owner_canary(bad_canary), now=NOW, state_root=tmp_path
        )


def test_source_consumption_rejects_canary_activation_hash_substitution(
    tmp_path: Path,
) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="GOVERNANCE_CANARY_AUTHORITY_MISMATCH"):
        consume_source_repair_authority(
            source,
            owner_canary(source_hash="e" * 64),
            now=NOW,
            state_root=tmp_path,
        )


def test_emergency_integration_rebinds_current_main_after_source_base_drift(
    tmp_path: Path,
) -> None:
    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )
    record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)

    with pytest.raises(BreakGlassRecoveryError, match="INTEGRATION_SUBJECT_MISMATCH"):
        prepare_emergency_integration(
            source,
            integration_envelope(verification, accepted_head="5" * 40),
            now=NOW,
            state_root=tmp_path,
        )

    current_main = "6" * 40
    rebound = prepare_emergency_integration(
        source,
        integration_envelope(verification, expected_base=current_main),
        now=NOW,
        state_root=tmp_path,
    )
    assert rebound["expected_base_sha"] == current_main
    assert rebound["accepted_head_sha"] == COMMIT


def test_self_hosting_recovery_e2e_restores_normal_path_then_collapses_authority(
    tmp_path: Path,
) -> None:
    candidate_plane = tmp_path / "candidate-governance-plane.json"
    integrated_plane = tmp_path / "main-governance-plane.json"
    merged_main = "8" * 40

    def normal_governance_canary() -> BreakGlassGovernanceCanaryEvidence:
        try:
            observed = json.loads(integrated_plane.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError("NORMAL_GOVERNANCE_UNAVAILABLE") from exc
        expected = {
            "recovery_id": "BG-806-20260906",
            "repair_commit": COMMIT,
            "integrated_main": merged_main,
            "authority_path": "normal-governance",
        }
        if observed != expected:
            raise RuntimeError("NORMAL_GOVERNANCE_NOT_RESTORED")
        return canary(main_sha=observed["integrated_main"])

    with pytest.raises(RuntimeError, match="NORMAL_GOVERNANCE_UNAVAILABLE"):
        normal_governance_canary()

    source = envelope()
    verification = verification_envelope()
    prepare_source_repair(
        source,
        observed_base_sha=BASE,
        observed_base_tree=TREE,
        now=NOW,
        state_root=tmp_path,
    )

    repaired_state = {
        "recovery_id": source.payload.recovery_id,
        "repair_commit": COMMIT,
        "authority_path": "normal-governance",
    }
    candidate_plane.write_text(
        json.dumps(repaired_state, sort_keys=True),
        encoding="utf-8",
    )
    assert json.loads(candidate_plane.read_text(encoding="utf-8")) == repaired_state

    record_source_repair_applied(
        source, applied(implementer="dev-mcp-owner-direct"), now=NOW, state_root=tmp_path
    )
    record_source_repair_verified(source, verification, now=NOW, state_root=tmp_path)

    integration = integration_envelope(verification)
    prepare_emergency_integration(source, integration, now=NOW, state_root=tmp_path)
    integrated_state = {
        **json.loads(candidate_plane.read_text(encoding="utf-8")),
        "integrated_main": merged_main,
    }
    integrated_plane.write_text(
        json.dumps(integrated_state, sort_keys=True),
        encoding="utf-8",
    )
    record_emergency_integration_consumed(
        integration,
        merge_commit_sha=merged_main,
        observed_main_sha=merged_main,
        merged_pr_number=808,
        now=NOW,
        state_root=tmp_path,
    )

    restored_canary = normal_governance_canary()
    consumed = consume_source_repair_authority(
        source, owner_canary(restored_canary), now=NOW, state_root=tmp_path
    )
    assert consumed["evidence"]["governance_canary_sha256"] == restored_canary.evidence_sha256
    assert consumed["evidence"]["authority_terminal"] is True

    integrated_plane.unlink()
    with pytest.raises(RuntimeError, match="NORMAL_GOVERNANCE_UNAVAILABLE"):
        normal_governance_canary()
    with pytest.raises(BreakGlassRecoveryError, match="RECOVERY_REPLAY_DENIED"):
        record_source_repair_applied(source, applied(), now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="INTEGRATION_REPLAY_DENIED"):
        assert_emergency_integration_not_consumed(integration, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="RECOVERY_GLOBALLY_TERMINAL"):
        assert_source_not_globally_terminal(source, (terminal_envelope(),))


def test_matching_owner_terminal_blocks_fresh_session_source_replay() -> None:
    source = envelope()
    with pytest.raises(BreakGlassRecoveryError, match="RECOVERY_GLOBALLY_TERMINAL"):
        assert_source_not_globally_terminal(source, (terminal_envelope(),))


def test_unrelated_owner_terminal_does_not_block_source() -> None:
    source = envelope()
    assert_source_not_globally_terminal(
        source,
        (terminal_envelope(recovery_id="BG-806-OTHER"),),
    )


def test_transition_tamper_is_detected(tmp_path: Path) -> None:
    env = envelope()
    prepare_source_repair(
        env, observed_base_sha=BASE, observed_base_tree=TREE, now=NOW, state_root=tmp_path
    )
    prepared = tmp_path / env.payload.recovery_id / env.payload.attempt_id / "01-prepared.json"
    payload = json.loads(prepared.read_text())
    payload["evidence"]["claim_ceiling"] = "forged"
    prepared.write_bytes(canonical_json_bytes(payload) + b"\n")
    os.chmod(prepared, 0o600)
    with pytest.raises(BreakGlassRecoveryError, match="STATE_HASH_INVALID"):
        inspect_attempt(env.payload, state_root=tmp_path)


def test_symlink_state_file_is_rejected(tmp_path: Path) -> None:
    env = envelope()
    attempt_dir = tmp_path / env.payload.recovery_id / env.payload.attempt_id
    attempt_dir.mkdir(parents=True, mode=0o700)
    target = tmp_path / "target.json"
    target.write_text("{}")
    (attempt_dir / "01-prepared.json").symlink_to(target)
    with pytest.raises(BreakGlassRecoveryError, match="STATE_FILE_UNSAFE"):
        inspect_attempt(env.payload, state_root=tmp_path)
