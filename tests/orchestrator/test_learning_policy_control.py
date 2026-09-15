from __future__ import annotations

import copy
import multiprocessing

import pytest

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.contracts.learning_experience import (
    build_learning_policy_adoption,
    build_learning_policy_recommendation,
    build_learning_policy_rollback,
    build_nexus_learning_episode,
    evaluate_learning_policy_recommendation,
)
from nexus.engine.learning_policy_loader import (
    DEFAULT_GOVERNED_ADOPTION_PATH,
    DEFAULT_GOVERNED_ROLLBACK_PATH,
)
from nexus.infrastructure.state_json_store import StateJsonStore
from nexus.orchestrator.learning_policy_control import (
    LearningPolicyControlError,
    apply_learning_policy_effect,
)


def _artifacts():
    episode = build_nexus_learning_episode(
        task_id="task_A",
        source="runtime_closure",
        terminal_outcome="SUCCESS",
        terminal_evidence={"verifier": "pytest", "receipt": "rec_A", "verifier_status": "passed"},
        qualification={
            "repeatability": True,
            "prevention_rule": "rule",
            "authority_qualification": True,
        },
        lesson_disposition="graduated",
        learning_write_succeeded=True,
    )
    scope = {
        "task_family": "record_serialization",
        "model_name": "qwen2.5-coder:7b",
        "runtime_identity": "local_model_executor",
    }
    recommendation = build_learning_policy_recommendation(
        source_episodes=[episode],
        source_evidence_refs=["rec_A", "retrieval_receipt:g2", "physical_consumption:ollama"],
        source_revision="rev_current",
        runtime_identity=scope["runtime_identity"],
        task_fingerprint="task_1",
        off_arm={"task_id": "task_1", "verifier_status": "failed", "receipt": "rec_off"},
        on_arm={"task_id": "task_1", "verifier_status": "passed", "receipt": "rec_on"},
        applicable_scope=scope,
        recommended_policy_delta={"episodic_memory_injection": {"enabled": True}},
        current_policy={"episodic_memory_injection": {"enabled": False}},
        expected_effect="Improve pass rate",
        rollback_target={
            "target_state": {"episodic_memory_injection": {"enabled": False}, "描述": "停用"},
            "trigger": "regression",
        },
    )
    validation = evaluate_learning_policy_recommendation(
        recommendation,
        validator_identity="reviewer",
        current_workspace_revision="rev_current",
        current_runtime_identity=scope["runtime_identity"],
    )
    adoption = build_learning_policy_adoption(
        owner_authority_reference="owner-ref",
        recommendation=recommendation,
        validation=validation,
        source_revision="rev_current",
        adopted_scope=scope,
        target_policy_delta=recommendation["recommended_policy_delta"],
        previous_policy=recommendation["current_policy"],
        rollback_target=recommendation["rollback_target"],
    )
    rollback = build_learning_policy_rollback(adoption=adoption, reason="test")
    return recommendation, validation, adoption, rollback, scope


def _apply(root, action, artifact, scope, **kwargs):
    previous = kwargs.pop("previous_adoption", None)
    return apply_learning_policy_effect(
        action=action,
        project_root=root,
        artifact=artifact,
        expected_current_digest=kwargs.pop("expected_current_digest", None),
        operation_id=kwargs.pop("operation_id", "op-1"),
        idempotency_key=kwargs.pop("idempotency_key", "idem-1"),
        source_revision="rev_current",
        task_family=scope["task_family"],
        model_name=scope["model_name"],
        runtime_identity=scope["runtime_identity"],
        previous_adoption=previous,
        previous_adoption_id=(previous.get("adoption_id") if previous else None),
        previous_adoption_hash=(previous.get("adoption_hash") if previous else None),
        **kwargs,
    )


def test_adoption_requires_original_provenance_and_cas_readback(tmp_path):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    with pytest.raises(LearningPolicyControlError, match="PROVENANCE_REQUIRED"):
        _apply(tmp_path, AutonomyActionClass.LEARNING_POLICY_ADOPT, adoption, scope)
    result = _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
    )
    assert result["status"] == "APPLIED"
    target = tmp_path / DEFAULT_GOVERNED_ADOPTION_PATH
    assert StateJsonStore().read_dict(target) == adoption
    duplicate = _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
    )
    assert duplicate["status"] == "RECONCILED_DUPLICATE"


def test_completed_operation_cannot_reapply_after_target_deletion(tmp_path):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
    )
    (tmp_path / DEFAULT_GOVERNED_ADOPTION_PATH).unlink()
    with pytest.raises(LearningPolicyControlError, match="RECONCILIATION_REQUIRED"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
        )


def test_strict_malformed_and_symlink_controls(tmp_path):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    target = tmp_path / DEFAULT_GOVERNED_ADOPTION_PATH
    target.parent.mkdir(parents=True)
    target.write_text("{malformed", encoding="utf-8")
    with pytest.raises(LearningPolicyControlError, match="STRICT_READ_FAILED"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
        )
    target.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    target.symlink_to(outside)
    with pytest.raises(LearningPolicyControlError, match="TARGET_SYMLINK"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
        )


def test_unknown_effect_after_target_write_reconciles(tmp_path, monkeypatch):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    original = StateJsonStore.compare_and_swap_dict
    calls = {"target": 0}

    def fail_after_target(self, path, expected, payload):
        result = original(self, path, expected, payload)
        if path.name == "governed_learning_policy_adoption.json" and calls["target"] == 0:
            calls["target"] += 1
            raise RuntimeError("simulated post-write disconnect")
        return result

    monkeypatch.setattr(StateJsonStore, "compare_and_swap_dict", fail_after_target)
    result = _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
    )
    assert result["status"] == "RECONCILED_AFTER_UNKNOWN_EFFECT"


def test_pending_journal_survives_crash_before_target_then_reconciles(tmp_path, monkeypatch):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    original = StateJsonStore.compare_and_swap_dict
    crashed = {"value": False}

    def crash_after_pending(self, path, expected, payload):
        result = original(self, path, expected, payload)
        if path.name == "governed_learning_policy_control_operations.json" and not crashed["value"]:
            crashed["value"] = True
            raise RuntimeError("simulated crash after pending journal")
        return result

    monkeypatch.setattr(StateJsonStore, "compare_and_swap_dict", crash_after_pending)
    with pytest.raises(RuntimeError, match="simulated crash"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
            operation_id="pending-op",
            idempotency_key="pending-idem",
        )
    monkeypatch.setattr(StateJsonStore, "compare_and_swap_dict", original)
    result = _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
        operation_id="pending-op",
        idempotency_key="pending-idem",
    )
    assert result["status"] == "APPLIED"


def test_pending_journal_reconciles_after_target_before_completion(tmp_path, monkeypatch):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    original = StateJsonStore.compare_and_swap_dict
    crashed = {"value": False}

    def crash_after_target(self, path, expected, payload):
        if (
            path.name == "governed_learning_policy_control_operations.json"
            and payload.get("pending-op-after-target", {}).get("status") == "COMPLETED"
            and not crashed["value"]
        ):
            crashed["value"] = True
            raise RuntimeError("simulated crash after target before completion")
        return original(self, path, expected, payload)

    monkeypatch.setattr(StateJsonStore, "compare_and_swap_dict", crash_after_target)
    with pytest.raises(RuntimeError, match="after target"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
            operation_id="pending-op-after-target",
            idempotency_key="pending-idem-after-target",
        )
    monkeypatch.setattr(StateJsonStore, "compare_and_swap_dict", original)
    result = _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
        operation_id="pending-op-after-target",
        idempotency_key="pending-idem-after-target",
    )
    assert result["status"] == "RECONCILED_AFTER_UNKNOWN_EFFECT"


def test_idempotency_key_cannot_change_operation_id(tmp_path):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
        operation_id="original-operation",
        idempotency_key="stable-idempotency-key",
    )
    with pytest.raises(LearningPolicyControlError, match="IDEMPOTENCY_KEY_REUSE"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
            operation_id="different-operation",
            idempotency_key="stable-idempotency-key",
        )


def test_tamper_stale_target_and_rollback_binding_fail_before_effect(tmp_path):
    recommendation, validation, adoption, rollback, scope = _artifacts()
    tampered = copy.deepcopy(adoption)
    tampered["adoption_status"] = "ACTIVE_CANDIDATE"
    tampered["target_policy_delta"] = {"unexpected": True}
    with pytest.raises(LearningPolicyControlError, match="ADOPTION_INVALID|PROVENANCE_MISMATCH"):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            tampered,
            scope,
            recommendation=recommendation,
            validation=validation,
        )
    with pytest.raises(
        LearningPolicyControlError, match="EXPECTED_ABSENT_MISMATCH|EXPECTED_DIGEST_MISMATCH"
    ):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
            expected_current_digest="0" * 64,
        )
    with pytest.raises(
        LearningPolicyControlError, match="ADOPTION_BINDING_MISMATCH|PERSISTED_ADOPTION_MISSING"
    ):
        _apply(
            tmp_path,
            AutonomyActionClass.LEARNING_POLICY_ROLLBACK,
            rollback,
            scope,
            previous_adoption={**adoption, "adoption_id": "other"},
        )
    assert not (tmp_path / DEFAULT_GOVERNED_ROLLBACK_PATH).exists()


def _rollback_worker(root, rollback, adoption, scope, queue):
    try:
        result = _apply(
            __import__("pathlib").Path(root),
            AutonomyActionClass.LEARNING_POLICY_ROLLBACK,
            rollback,
            scope,
            previous_adoption=adoption,
            operation_id="rollback-process",
            idempotency_key="rollback-process-idem",
        )
        queue.put(result["status"])
    except Exception as exc:  # pragma: no cover - asserted by parent process
        queue.put(type(exc).__name__ + ":" + str(exc))


def test_rollback_reconciles_after_process_restart(tmp_path):
    recommendation, validation, adoption, rollback, scope = _artifacts()
    _apply(
        tmp_path,
        AutonomyActionClass.LEARNING_POLICY_ADOPT,
        adoption,
        scope,
        recommendation=recommendation,
        validation=validation,
        operation_id="adopt-1",
        idempotency_key="adopt-idem",
    )
    ctx = multiprocessing.get_context("spawn")
    for expected in ("APPLIED", "RECONCILED_DUPLICATE"):
        queue = ctx.Queue()
        process = ctx.Process(
            target=_rollback_worker, args=(str(tmp_path), rollback, adoption, scope, queue)
        )
        process.start()
        outcome = queue.get(timeout=20)
        process.join(timeout=20)
        assert outcome == expected


def _race_worker(root, adoption, recommendation, validation, scope, operation_id, queue):
    try:
        result = _apply(
            __import__("pathlib").Path(root),
            AutonomyActionClass.LEARNING_POLICY_ADOPT,
            adoption,
            scope,
            recommendation=recommendation,
            validation=validation,
            operation_id=operation_id,
            idempotency_key=operation_id,
        )
        queue.put(result["status"])
    except Exception as exc:  # pragma: no cover - asserted by parent process
        queue.put(type(exc).__name__ + ":" + str(exc))


def test_two_process_adoption_race_has_one_effect_and_one_fail_closed(tmp_path):
    recommendation, validation, adoption, _rollback, scope = _artifacts()
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    processes = [
        ctx.Process(
            target=_race_worker,
            args=(
                str(tmp_path),
                adoption,
                recommendation,
                validation,
                scope,
                f"race-{index}",
                queue,
            ),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    outcomes = [queue.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
    assert sorted(outcomes)[0] == "APPLIED"
    assert any(
        "EXPECTED_ABSENT_MISMATCH" in outcome
        or "LEARNING_POLICY_EXPECTED_DIGEST_MISMATCH" in outcome
        for outcome in outcomes
    )
    assert StateJsonStore().read_dict(tmp_path / DEFAULT_GOVERNED_ADOPTION_PATH) == adoption
