from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nexus.contracts.break_glass_recovery import (
    BreakGlassAppliedEvidence,
    BreakGlassVerificationEvidence,
    OwnerActivationEnvelope,
    canonical_json_bytes,
    canonical_sha256,
)
from nexus.orchestrator.break_glass_recovery import (
    BreakGlassRecoveryError,
    consume_source_repair_authority,
    inspect_attempt,
    prepare_source_repair,
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


def verification(*, verifier: str = "primary-coordinator") -> BreakGlassVerificationEvidence:
    return BreakGlassVerificationEvidence(
        verifier_id=verifier,
        verifier_evidence_sha256=VERIFY_HASH,
        verified_commit_sha=COMMIT,
        verified_tree_sha=REPAIR_TREE,
        verified_diff_sha256=DIFF_HASH,
    )


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
            env, verification(verifier="worker-1"), now=NOW, state_root=tmp_path
        )

    verified = record_source_repair_verified(
        env, verification(verifier="primary-coordinator"), now=NOW, state_root=tmp_path
    )
    assert verified["phase"] == "VERIFIED"
    consumed = consume_source_repair_authority(env, now=NOW, state_root=tmp_path)
    assert consumed["phase"] == "CONSUMED"
    assert consumed["evidence"]["granted_effect"] == "SOURCE_REPAIR_ONLY"
    assert "GITHUB_MERGE" in consumed["evidence"]["excluded_effects"]
    assert "RUNTIME_RECOVERY" in consumed["evidence"]["excluded_effects"]

    with pytest.raises(BreakGlassRecoveryError, match="RECOVERY_REPLAY_DENIED"):
        consume_source_repair_authority(env, now=NOW, state_root=tmp_path)
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
        record_source_repair_verified(env, verification(), now=NOW, state_root=tmp_path)
    with pytest.raises(BreakGlassRecoveryError, match="VERIFIED_EVIDENCE_REQUIRED"):
        consume_source_repair_authority(env, now=NOW, state_root=tmp_path)


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
    bad = BreakGlassVerificationEvidence(
        verifier_id="primary-coordinator",
        verifier_evidence_sha256=VERIFY_HASH,
        verified_commit_sha="6" * 40,
        verified_tree_sha=REPAIR_TREE,
        verified_diff_sha256=DIFF_HASH,
    )
    with pytest.raises(BreakGlassRecoveryError, match="VERIFICATION_SUBJECT_MISMATCH"):
        record_source_repair_verified(env, bad, now=NOW, state_root=tmp_path)


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
