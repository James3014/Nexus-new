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
    OwnerRuntimeRecoveryEnvelope,
    OwnerRuntimeRevocationEnvelope,
    OwnerTerminalEnvelope,
    OwnerVerificationEnvelope,
    canonical_json_bytes,
    canonical_sha256,
)
from nexus.contracts.gateway_deployment import (
    EffectClass,
    GatewayReconcileOutcome,
    GatewayRecoveryRequest,
    ResultClass,
    canonical_hash,
)
from nexus.orchestrator.break_glass_recovery import (
    BreakGlassRecoveryError,
    assert_emergency_integration_not_consumed,
    assert_source_not_globally_terminal,
    consume_source_repair_authority,
    execute_runtime_recovery,
    inspect_attempt,
    inspect_emergency_integration,
    inspect_runtime_recovery,
    prepare_emergency_integration,
    prepare_runtime_recovery,
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


def gateway_request() -> GatewayRecoveryRequest:
    values = {
        "request_id": "BG-973-GW-REQ-1",
        "idempotency_fence": "BG-973-FENCE-1",
        "operation": "gateway-recover",
        "effect_class": EffectClass.GATEWAY_DURABLE_RECOVERY,
        "recovery_authority_id": "gateway-recovery-authority-1",
        "recovery_authority_hash": "a" * 64,
        "desired_manifest_id": "desired-973",
        "desired_manifest_hash": "b" * 64,
        "predecessor_manifest_id": "predecessor-973",
        "predecessor_manifest_hash": "c" * 64,
    }
    return GatewayRecoveryRequest(**values, request_hash=canonical_hash(values))


def runtime_envelope(
    request: GatewayRecoveryRequest | None = None,
    *,
    expires_at: str = "2026-09-06T23:00:00+08:00",
    runtime_attempt_id: str = "BG-973-R1",
) -> OwnerRuntimeRecoveryEnvelope:
    request = request or gateway_request()
    payload = {
        "schema": "nexus.break_glass_owner_runtime_recovery.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "runtime_recovery_issue": 973,
        "recovery_id": "BG-973-20260906",
        "runtime_attempt_id": runtime_attempt_id,
        "effect_class": "RUNTIME_RECOVERY",
        "action": "GATEWAY_DURABLE_RECOVERY",
        "service_identity": "com.nexus.mcp.gateway.direct",
        "gateway_request_id": request.request_id,
        "gateway_request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "desired_manifest_id": request.desired_manifest_id,
        "desired_manifest_sha256": request.desired_manifest_hash,
        "predecessor_manifest_id": request.predecessor_manifest_id,
        "predecessor_manifest_sha256": request.predecessor_manifest_hash,
        "issued_at": "2026-09-06T07:30:00+08:00",
        "expires_at": expires_at,
        "claim_ceiling": "runtime_recovery_only",
    }
    payload_hash = canonical_sha256(payload)
    return OwnerRuntimeRecoveryEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 6000000973,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000973",
        "author_login": "James3014",
        "comment_body_sha256": "e" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def runtime_revocation(runtime: OwnerRuntimeRecoveryEnvelope) -> OwnerRuntimeRevocationEnvelope:
    payload = {
        "schema": "nexus.break_glass_owner_runtime_revocation.v1",
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "owner_login": "James3014",
        "runtime_recovery_issue": 973,
        "recovery_id": runtime.payload.recovery_id,
        "runtime_attempt_id": runtime.payload.runtime_attempt_id,
        "runtime_recovery_payload_sha256": runtime.payload_sha256,
        "reason": "owner-revoked-before-effect",
        "issued_at": "2026-09-06T07:45:00+08:00",
    }
    payload_hash = canonical_sha256(payload)
    return OwnerRuntimeRevocationEnvelope.model_validate({
        "repository": "James3014/Nexus-new",
        "issue": 806,
        "comment_id": 6000000974,
        "comment_url": "https://github.com/James3014/Nexus-new/issues/806#issuecomment-6000000974",
        "author_login": "James3014",
        "comment_body_sha256": "f" * 64,
        "payload_sha256": payload_hash,
        "payload": payload,
    })


def gateway_outcome(
    request: GatewayRecoveryRequest,
    *,
    result: ResultClass = ResultClass.VERIFIED,
    effect_started: bool = True,
) -> GatewayReconcileOutcome:
    values = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "desired_manifest_id": request.desired_manifest_id,
        "predecessor_manifest_id": request.predecessor_manifest_id,
        "physical_observation": {
            "service_identity": "com.nexus.mcp.gateway.direct",
            "postflight": "IDENTITY_AND_HEALTH_VERIFIED",
        },
        "effect_started": effect_started,
        "result": result,
    }
    return GatewayReconcileOutcome(**values, evidence_hash=canonical_hash(values))


def run_runtime_recovery(
    runtime: OwnerRuntimeRecoveryEnvelope,
    request: GatewayRecoveryRequest,
    *,
    executor,
    state_root: Path,
    clock_values: tuple[datetime, ...] = (NOW, NOW),
    revocation_snapshots: tuple[tuple[OwnerRuntimeRevocationEnvelope, ...], ...] = ((), ()),
):
    clocks = iter(clock_values)
    snapshots = iter(revocation_snapshots)
    return execute_runtime_recovery(
        runtime,
        request,
        clock=lambda: next(clocks),
        revocation_provider=lambda: next(snapshots),
        executor=executor,
        state_root=state_root,
    )


def _must_not_refresh_authority() -> tuple[OwnerRuntimeRevocationEnvelope, ...]:
    raise AssertionError("post-DISPATCH reconciliation must not re-open authority freshness")


def _must_not_read_clock() -> datetime:
    raise AssertionError("post-DISPATCH reconciliation must not re-open expiry")


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


def test_runtime_recovery_exact_authority_consumes_once_and_redacts_physical_details(
    tmp_path: Path,
) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)
    calls: list[str] = []

    def executor(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        calls.append(actual.request_id)
        return gateway_outcome(actual)

    terminal = run_runtime_recovery(runtime, request, executor=executor, state_root=tmp_path)
    assert terminal["status"] == "CONSUMED"
    assert terminal["authority_terminal"] is True
    assert terminal["post_terminal_replay"] == "DENY"
    assert "physical_observation" not in terminal
    expected_outcome = gateway_outcome(request)
    assert terminal["physical_observation_sha256"] == canonical_sha256(
        dict(expected_outcome.physical_observation)
    )
    assert calls == [request.request_id]

    structural = inspect_runtime_recovery(runtime, state_root=tmp_path)
    assert structural["status"] == "TERMINAL_RECORDED_REQUIRES_GATEWAY_OUTCOME"
    verified = inspect_runtime_recovery(
        runtime,
        gateway_request=request,
        gateway_outcome=expected_outcome,
        state_root=tmp_path,
    )
    assert verified["status"] == "CONSUMED"
    assert verified["verified_against_gateway_outcome"] is True

    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_REPLAY_DENIED"):
        execute_runtime_recovery(
            runtime,
            request,
            clock=_must_not_read_clock,
            revocation_provider=_must_not_refresh_authority,
            executor=executor,
            state_root=tmp_path,
        )
    assert calls == [request.request_id]


def test_runtime_recovery_rejects_expired_revoked_and_mismatched_before_effect(
    tmp_path: Path,
) -> None:
    request = gateway_request()
    calls: list[str] = []

    def executor(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        calls.append(actual.request_id)
        return gateway_outcome(actual)

    expired = runtime_envelope(request, expires_at="2026-09-06T07:31:00+08:00")
    with pytest.raises(Exception, match="RUNTIME_RECOVERY_EXPIRED"):
        run_runtime_recovery(
            expired,
            request,
            executor=executor,
            state_root=tmp_path / "expired",
        )

    runtime = runtime_envelope(request)
    revocation = runtime_revocation(runtime)
    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_REVOKED"):
        run_runtime_recovery(
            runtime,
            request,
            executor=executor,
            revocation_snapshots=((revocation,),),
            state_root=tmp_path / "revoked",
        )

    values = {
        key: value
        for key, value in request.model_dump().items()
        if key not in {"schema", "request_hash"}
    }
    values["request_id"] = "BG-973-GW-REQ-OTHER"
    values["effect_class"] = EffectClass.GATEWAY_DURABLE_RECOVERY
    other = GatewayRecoveryRequest(**values, request_hash=canonical_hash(values))
    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_GATEWAY_REQUEST_MISMATCH"):
        run_runtime_recovery(
            runtime,
            other,
            executor=executor,
            state_root=tmp_path / "mismatch",
        )
    assert calls == []


def test_runtime_recovery_fresh_commit_clock_catches_expiry_after_initial_readback(
    tmp_path: Path,
) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request, expires_at="2026-09-06T08:05:00+08:00")
    calls: list[str] = []

    def executor(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        calls.append(actual.request_id)
        return gateway_outcome(actual)

    with pytest.raises(Exception, match="RUNTIME_RECOVERY_EXPIRED"):
        run_runtime_recovery(
            runtime,
            request,
            executor=executor,
            clock_values=(NOW, datetime(2026, 9, 6, 0, 6, tzinfo=timezone.utc)),
            revocation_snapshots=((), ()),
            state_root=tmp_path,
        )
    assert calls == []
    assert not (
        tmp_path
        / runtime.payload.recovery_id
        / runtime.payload.runtime_attempt_id
        / "02-runtime-dispatched.json"
    ).exists()


def test_runtime_recovery_rereads_revocation_immediately_before_dispatch(
    tmp_path: Path,
) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)
    revocation = runtime_revocation(runtime)
    calls: list[str] = []

    def executor(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        calls.append(actual.request_id)
        return gateway_outcome(actual)

    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_REVOKED"):
        run_runtime_recovery(
            runtime,
            request,
            executor=executor,
            revocation_snapshots=((), (revocation,)),
            state_root=tmp_path,
        )
    assert calls == []
    assert not (
        tmp_path
        / runtime.payload.recovery_id
        / runtime.payload.runtime_attempt_id
        / "02-runtime-dispatched.json"
    ).exists()


def test_runtime_recovery_lost_ack_reconciles_same_request_after_expiry_and_revocation(
    tmp_path: Path,
) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request, expires_at="2026-09-06T08:05:00+08:00")
    durable_manager_result: GatewayReconcileOutcome | None = None
    physical_activations = 0
    calls = 0

    def executor(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        nonlocal durable_manager_result, physical_activations, calls
        calls += 1
        if durable_manager_result is None:
            physical_activations += 1
            durable_manager_result = gateway_outcome(actual)
            raise TimeoutError("ack lost after durable manager effect")
        return durable_manager_result

    with pytest.raises(
        BreakGlassRecoveryError,
        match="RUNTIME_RECOVERY_OUTCOME_UNKNOWN_RECONCILE_SAME_REQUEST",
    ):
        run_runtime_recovery(runtime, request, executor=executor, state_root=tmp_path)
    assert inspect_runtime_recovery(runtime, state_root=tmp_path)["status"] == (
        "DISPATCHED_RECONCILE_ONLY"
    )
    assert physical_activations == 1

    terminal = execute_runtime_recovery(
        runtime,
        request,
        clock=_must_not_read_clock,
        revocation_provider=_must_not_refresh_authority,
        executor=executor,
        state_root=tmp_path,
    )
    assert terminal["status"] == "CONSUMED"
    assert calls == 2
    assert physical_activations == 1


def test_runtime_recovery_records_rollback_as_terminal_and_denies_replay(tmp_path: Path) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)
    outcome = gateway_outcome(request, result=ResultClass.ROLLED_BACK)
    terminal = run_runtime_recovery(
        runtime,
        request,
        executor=lambda actual: outcome,
        state_root=tmp_path,
    )
    assert terminal["status"] == "ROLLED_BACK"
    assert terminal["effect_started"] is True
    verified = inspect_runtime_recovery(
        runtime,
        gateway_request=request,
        gateway_outcome=outcome,
        state_root=tmp_path,
    )
    assert verified["status"] == "ROLLED_BACK"
    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_REPLAY_DENIED"):
        prepare_runtime_recovery(runtime, request, now=NOW, state_root=tmp_path)


def test_runtime_recovery_self_rehashed_prepared_tamper_is_rejected(tmp_path: Path) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)
    prepare_runtime_recovery(runtime, request, now=NOW, state_root=tmp_path)
    prepared_path = (
        tmp_path
        / runtime.payload.recovery_id
        / runtime.payload.runtime_attempt_id
        / "01-runtime-prepared.json"
    )
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    prepared["service_identity"] = "com.example.forged"
    body = {key: value for key, value in prepared.items() if key != "transition_hash"}
    prepared["transition_hash"] = canonical_sha256(body)
    prepared_path.write_text(
        json.dumps(prepared, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_PREPARED_TAMPERED"):
        inspect_runtime_recovery(runtime, state_root=tmp_path)


def test_runtime_recovery_self_rehashed_dispatch_tamper_is_rejected(tmp_path: Path) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)

    def lost_ack(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        _ = gateway_outcome(actual)
        raise TimeoutError("ack lost after dispatch")

    with pytest.raises(
        BreakGlassRecoveryError,
        match="RUNTIME_RECOVERY_OUTCOME_UNKNOWN_RECONCILE_SAME_REQUEST",
    ):
        run_runtime_recovery(
            runtime,
            request,
            executor=lost_ack,
            state_root=tmp_path,
        )

    dispatched_path = (
        tmp_path
        / runtime.payload.recovery_id
        / runtime.payload.runtime_attempt_id
        / "02-runtime-dispatched.json"
    )
    dispatched = json.loads(dispatched_path.read_text(encoding="utf-8"))
    dispatched["gateway_request_hash"] = "0" * 64
    body = {key: value for key, value in dispatched.items() if key != "transition_hash"}
    dispatched["transition_hash"] = canonical_sha256(body)
    dispatched_path.write_text(
        json.dumps(dispatched, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_DISPATCH_TAMPERED"):
        inspect_runtime_recovery(runtime, state_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "ROLLED_BACK"),
        ("phase", "DISPATCHED"),
        ("effect_started", False),
        ("gateway_outcome_evidence_sha256", "0" * 64),
        ("physical_observation_sha256", "1" * 64),
        ("gateway_request_hash", "2" * 64),
        ("claim_ceiling", "production_success"),
    ],
)
def test_runtime_recovery_self_rehashed_terminal_semantic_tamper_fails_closed(
    tmp_path: Path, field: str, value: object
) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)
    outcome = gateway_outcome(request)
    run_runtime_recovery(
        runtime,
        request,
        executor=lambda actual: outcome,
        state_root=tmp_path,
    )
    terminal_path = (
        tmp_path
        / runtime.payload.recovery_id
        / runtime.payload.runtime_attempt_id
        / "03-runtime-terminal.json"
    )
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal[field] = value
    body = {key: item for key, item in terminal.items() if key != "transition_hash"}
    terminal["transition_hash"] = canonical_sha256(body)
    terminal_path.write_text(
        json.dumps(terminal, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    if field in {"status", "gateway_outcome_evidence_sha256", "physical_observation_sha256"}:
        structural = inspect_runtime_recovery(runtime, state_root=tmp_path)
        assert structural["status"] == "TERMINAL_RECORDED_REQUIRES_GATEWAY_OUTCOME"
    else:
        with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_TERMINAL"):
            inspect_runtime_recovery(runtime, state_root=tmp_path)

    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_TERMINAL"):
        inspect_runtime_recovery(
            runtime,
            gateway_request=request,
            gateway_outcome=outcome,
            state_root=tmp_path,
        )


def test_runtime_recovery_pre_effect_block_terminalizes_and_denies_replay(tmp_path: Path) -> None:
    request = gateway_request()
    runtime = runtime_envelope(request)
    outcome = gateway_outcome(
        request,
        result=ResultClass.BLOCKED,
        effect_started=False,
    )
    calls: list[str] = []

    def executor(actual: GatewayRecoveryRequest) -> GatewayReconcileOutcome:
        calls.append(actual.request_id)
        return outcome

    terminal = run_runtime_recovery(
        runtime,
        request,
        executor=executor,
        state_root=tmp_path,
    )
    assert terminal["status"] == "BLOCKED_BEFORE_EFFECT"
    assert terminal["effect_started"] is False
    assert terminal["authority_terminal"] is True
    assert terminal["post_terminal_replay"] == "DENY"

    structural = inspect_runtime_recovery(runtime, state_root=tmp_path)
    assert structural["status"] == "TERMINAL_RECORDED_REQUIRES_GATEWAY_OUTCOME"
    verified = inspect_runtime_recovery(
        runtime,
        gateway_request=request,
        gateway_outcome=outcome,
        state_root=tmp_path,
    )
    assert verified["status"] == "BLOCKED_BEFORE_EFFECT"
    assert verified["verified_against_gateway_outcome"] is True

    with pytest.raises(BreakGlassRecoveryError, match="RUNTIME_RECOVERY_REPLAY_DENIED"):
        execute_runtime_recovery(
            runtime,
            request,
            clock=_must_not_read_clock,
            revocation_provider=_must_not_refresh_authority,
            executor=executor,
            state_root=tmp_path,
        )
    assert calls == [request.request_id]
