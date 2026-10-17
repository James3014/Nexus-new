"""Workforce dispatch binding and action request validation helpers of SHTS.

Big-file split S4 (Issue #2563). The module-level helpers moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* workforce dispatch binding: ``_workforce_dispatch_inputs``,
  ``_tracked_dispatch_required``, ``_workforce_admission_readback_matches``,
  ``validate_workforce_dispatch_binding`` and ``_recover_pre_provider_cli_envelope_drift``;
* action request validation: ``_validated_action_request``,
  ``_validate_project_entry_authority_binding`` and
  ``_reject_unbound_project_entry_authority_hints``.

The facade re-exports each of them (``from ... import X as X``), so
``self_hosted_task_service.X is dispatch_binding.X``. Their source lines are verbatim,
except that every facade-module name they load (``evaluate_runtime_workforce_admission``,
``WorkforcePolicyLoader``, ``_jsonable``, ``build_canonical_dispatch_envelope``,
``SelfHostedTaskService``, ``ContractKind``, ``LifecycleActionEnvelope``,
``LifecycleActionType``, ``canonical_request_hash``, ``AutonomyActionClass``,
``_PROJECT_ENTRY_AUTHORITY_HINTS``, and the moved helpers ``_workforce_dispatch_inputs``,
``_workforce_admission_readback_matches``, ``validate_workforce_dispatch_binding`` and
``_validate_project_entry_authority_binding`` when one helper calls another) is resolved
at call time through ``_service_module()``, so patches on the facade keep taking effect.

All of them are pure validation: they take no lock and write no state. The only
collaborators with side effects are the ones they already called before the move
(the runtime workforce admission evaluator and the policy loader, which read the
workforce policy).
"""

from __future__ import annotations

import importlib
import json
from typing import Any, Mapping, Optional


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a helper runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


# fmt: off
def _workforce_dispatch_inputs(request: Mapping[str, Any]) -> tuple[Any, Any]:
    """Extract the planner/admission pair without inventing a fallback source."""
    planner = request.get("planner_output")
    if not isinstance(planner, Mapping):
        planner = request.get("planner")
    snapshot = request.get("signal_snapshot")
    if not isinstance(snapshot, Mapping) and isinstance(planner, Mapping):
        snapshot = planner.get("signal_snapshot")
    demands = request.get("workforce_demands")
    if demands is None and isinstance(snapshot, Mapping):
        demands = snapshot.get("workforce_demands")
    admission = request.get("workforce_admission")
    if admission is None and isinstance(planner, Mapping):
        admission = planner.get("workforce_admission")
    if admission is None:
        admission = request.get("admission_binding")
    return demands, admission


def _tracked_dispatch_required(
    request: Mapping[str, Any],
    state: Optional[Mapping[str, Any]] = None,
) -> bool:
    tracked = _service_module().ContractKind.TRACKED_TASK_CARD.value
    return str(request.get("contract_kind") or "") == tracked or (
        isinstance(state, Mapping)
        and str(state.get("contract_kind") or "") == tracked
    )


def _workforce_admission_readback_matches(
    persisted: Mapping[str, Any],
    fresh: Mapping[str, Any],
) -> bool:
    """Allow only forward daily age derivation drift in a fresh ALLOW receipt."""
    if persisted.get("overall_decision") != "ALLOW" or fresh.get("overall_decision") != "ALLOW":
        return False
    old = json.loads(json.dumps(dict(persisted)))
    current = json.loads(json.dumps(dict(fresh)))
    old_records = old.get("records")
    current_records = current.get("records")
    if (
        not isinstance(old_records, list)
        or not isinstance(current_records, list)
        or len(old_records) != len(current_records)
    ):
        return False
    for old_record, current_record in zip(old_records, current_records):
        old_decision = old_record.get("decision") if isinstance(old_record, Mapping) else None
        current_decision = (
            current_record.get("decision") if isinstance(current_record, Mapping) else None
        )
        old_freshness = (
            old_decision.get("freshness_evidence") if isinstance(old_decision, Mapping) else None
        )
        current_freshness = (
            current_decision.get("freshness_evidence")
            if isinstance(current_decision, Mapping)
            else None
        )
        if not isinstance(old_freshness, Mapping) or not isinstance(current_freshness, Mapping):
            return False
        old_age = old_freshness.get("verified_age_days")
        current_age = current_freshness.get("verified_age_days")
        if (
            type(old_age) is not int
            or type(current_age) is not int
            or old_age < 0
            or current_age < old_age
        ):
            return False
        old_freshness.pop("verified_age_days", None)  # pyright: ignore[reportAttributeAccessIssue]
        current_freshness.pop("verified_age_days", None)  # pyright: ignore[reportAttributeAccessIssue]
    return old == current


def validate_workforce_dispatch_binding(
    request: Mapping[str, Any],
    *,
    require_binding: bool = False,
) -> Optional[dict[str, Any]]:
    """Validate the exact Planner -> admission -> registry dispatch binding.

    The runtime admission service remains the policy authority.  This seam only
    verifies its durable, canonical ALLOW receipt before selecting a registry
    identity; it never resolves a worker or recomputes policy.
    """
    demands, admission = _service_module()._workforce_dispatch_inputs(request)
    if demands is None and admission is None:
        if require_binding:
            raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
        return None
    if demands is None or admission is None:
        raise RuntimeError("WORKFORCE_ADMISSION_BINDING_MISSING")
    if not isinstance(admission, Mapping) or admission.get("overall_decision") != "ALLOW":
        raise RuntimeError("WORKFORCE_ADMISSION_BINDING_INVALID:overall decision is not ALLOW")
    try:
        raw_items = demands.get("demands") if isinstance(demands, Mapping) else None
        records = admission.get("records")
        if not isinstance(raw_items, list) or len(raw_items) != 1:
            raise ValueError("workforce dispatch requires exactly one demand")
        if not isinstance(records, list) or len(records) != 1:
            raise ValueError("workforce dispatch requires exactly one admission record")
        record = records[0]
        record_demand = record.get("demand") if isinstance(record, Mapping) else None
        if not isinstance(record_demand, Mapping) or any(
            record_demand.get(field) != raw_items[0].get(field)
            for field in ("demand_id", "execution_channel")
        ):
            raise ValueError("workforce admission demand/record mismatch")
        record_request = record.get("request")
        if not isinstance(record_request, Mapping):
            raise ValueError("workforce admission record request missing")
        channel = str(raw_items[0].get("execution_channel") or "")
        if channel not in {"local", "online"}:
            raise ValueError("workforce dispatch execution channel invalid")
        binding: dict[str, Any] = {
            "worker_id": record_request.get("requested_worker_id"),
            "provider": record_request.get("provider"),
            "model": record_request.get("model"),
            "controls": record_request.get("provided_controls") or [],
            "explicit_experiment_authorization": bool(
                record_request.get("explicit_experiment_authorization", False)
            ),
        }
        if not binding["worker_id"] and not binding["provider"] and not binding["model"]:
            raise ValueError("workforce admission record identity missing")
        fresh = _service_module().evaluate_runtime_workforce_admission(
            demands,
            {channel: binding},
            _service_module().WorkforcePolicyLoader(),
        ).to_dict()
        if not _service_module()._workforce_admission_readback_matches(admission, fresh):
            raise ValueError("workforce admission receipt is stale or tampered")
        fresh_records = fresh.get("records") or []
        if (
            fresh.get("overall_decision") != "ALLOW"
            or len(fresh_records) != 1
            or (fresh_records[0].get("decision") or {}).get("decision") != "ALLOW"
        ):
            raise ValueError("workforce admission is not a single ALLOW record")
        decision = fresh_records[0].get("decision") or {}
        binding = {
            "worker_id": decision.get("resolved_worker_id"),
            "provider": decision.get("resolved_provider"),
            "model": decision.get("resolved_model"),
            "policy_hash": (fresh.get("policy_identity") or {}).get("policy_hash"),
            "binding_hash": fresh_records[0].get("binding_hash"),
            "aggregate_binding_hash": fresh.get("aggregate_binding_hash"),
        }
        if any(not isinstance(binding[field], str) or not binding[field].strip() for field in (
            "worker_id", "provider", "model", "policy_hash", "binding_hash", "aggregate_binding_hash"
        )):
            raise ValueError("workforce admission resolved identity missing")
    except (TypeError, ValueError, KeyError) as exc:
        raise RuntimeError(f"WORKFORCE_ADMISSION_BINDING_INVALID:{exc}") from exc
    fallback = str(request.get("fallback_worker", request.get("fallback_provider")) or "").strip().lower()
    if fallback and fallback != str(binding["provider"]).strip().lower():
        raise RuntimeError("WORKFORCE_ADMISSION_FALLBACK_UNADMITTED")
    raw_envelope = request.get("canonical_dispatch_envelope")
    result = {
        "demands": _service_module()._jsonable(demands),
        "admission": _service_module()._jsonable(admission),
        "demand_id": str(raw_items[0].get("demand_id") or ""),
        "worker_id": str(binding["worker_id"]),
        "provider": str(binding["provider"]),
        "model": str(binding["model"]),
        "policy_hash": str(binding["policy_hash"]),
        "binding_hash": str(binding["binding_hash"]),
        "aggregate_binding_hash": str(binding["aggregate_binding_hash"]),
    }
    if raw_envelope is not None:
        if not isinstance(raw_envelope, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_INVALID")
        planner_output = request.get("planner_output")
        if not isinstance(planner_output, Mapping):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_PLANNER_MISSING")
        try:
            envelope = _service_module().build_canonical_dispatch_envelope(
                planner_output,
                {**binding, "demand_id": str(raw_items[0].get("demand_id") or "")},
                task_id=str(request.get("task_id") or ""),
                attempt_id=str(request.get("attempt_id") or ""),
                task_card_path=str(request.get("task_card_path") or ""),
                task_card_hash=str(request.get("task_card_hash") or ""),
            ).to_dict()
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"WORKFORCE_DISPATCH_ENVELOPE_INVALID:{exc}") from exc
        if dict(raw_envelope) != envelope:
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISMATCH")
        result["canonical_dispatch_envelope"] = envelope
    return result


def _recover_pre_provider_cli_envelope_drift(
    state: Mapping[str, Any],
    request: Mapping[str, Any],
    failure: RuntimeError,
) -> Optional[dict[str, Any]]:
    """Recover one fail-closed CLI bootstrap mismatch before any side effect.

    The request/envelope pair remains the admitted authority.  This recovery is
    intentionally unavailable once a Target, provider call, execution receipt,
    or Candidate may exist; it accepts only the historical service-generated
    attempt substitution that failed before worker dispatch.
    """
    if str(failure) != "WORKFORCE_DISPATCH_ENVELOPE_MISMATCH":
        return None
    if (
        state.get("status") != "FINAL_BLOCK"
        or state.get("error") != "WORKFORCE_DISPATCH_ENVELOPE_IDENTITY_DRIFT"
        or state.get("action") is not None
        or state.get("action_id") is not None
        or state.get("target_created_at") is not None
        or state.get("lease") is not None
        or state.get("worker_preflight") is not None
        or state.get("active_provider") not in (None, "")
        or state.get("worker_child_pgid") is not None
        or state.get("execution") is not None
        or state.get("candidate") is not None
        or state.get("candidate_commit_sha") is not None
        or state.get("candidate_ref") is not None
        or state.get("candidate_state_hash") is not None
        or state.get("verified_receipt") is not None
        or state.get("verified_receipt_hash") is not None
        or state.get("executions") not in (None, [])
        or str(state.get("cleanup_decision") or "") != "ALREADY_REMOVED"
        or state.get("cleanup_performed") not in (None, False)
        or state.get("cleanup_blocker") not in (None, "")
        or state.get("promotion_status") not in (None, "NOT_CREATED")
        or state.get("merge_performed") not in (None, False)
        or state.get("push_performed") not in (None, False)
    ):
        return None
    telemetry = state.get("telemetry")
    if (
        not isinstance(telemetry, Mapping)
        or int(telemetry.get("provider_calls") or 0) != 0
        or int(telemetry.get("provider_attempts") or 0) != 0
        or int(telemetry.get("provider_time_ms") or 0) != 0
        or int(telemetry.get("worktree_time_ms") or 0) != 0
        or int(telemetry.get("verifier_time_ms") or 0) != 0
    ):
        return None
    stored_envelope = state.get("canonical_dispatch_envelope")
    request_envelope = request.get("canonical_dispatch_envelope")
    if (
        not isinstance(stored_envelope, Mapping)
        or not isinstance(request_envelope, Mapping)
        or dict(stored_envelope) != dict(request_envelope)
    ):
        return None
    actual_attempt_id = str(state.get("attempt_id") or "")
    stale_attempt_id = str(stored_envelope.get("attempt_id") or "")
    attempts = state.get("attempts")
    if (
        not actual_attempt_id
        or not stale_attempt_id
        or actual_attempt_id == stale_attempt_id
        or str(request.get("attempt_id") or "") != stale_attempt_id
        or not isinstance(attempts, list)
        or len(attempts) != 1
        or not isinstance(attempts[0], Mapping)
        or str(attempts[0].get("attempt_id") or "") != actual_attempt_id
    ):
        return None
    try:
        dispatch = _service_module().validate_workforce_dispatch_binding(request, require_binding=True)
        if dispatch is None:
            return None
        expected = _service_module().build_canonical_dispatch_envelope(
            request["planner_output"],
            {**dispatch, "demand_id": dispatch.get("demand_id")},
            task_id=str(state.get("task_id") or ""),
            attempt_id=actual_attempt_id,
            task_card_path=str(state.get("task_card_path") or ""),
            task_card_hash=str(state.get("task_card_hash") or ""),
        ).to_dict()
    except (KeyError, RuntimeError, TypeError, ValueError):
        return None
    observed_without_attempt = dict(stored_envelope)
    expected_without_attempt = dict(expected)
    observed_without_attempt.pop("attempt_id", None)
    expected_without_attempt.pop("attempt_id", None)
    if observed_without_attempt != expected_without_attempt:
        return None
    reconciled_request = dict(request)
    reconciled_request.update(
        attempt_id=actual_attempt_id,
        canonical_dispatch_envelope=expected,
    )
    try:
        reconciled_dispatch = _service_module().validate_workforce_dispatch_binding(
            reconciled_request, require_binding=True
        )
        if reconciled_dispatch is None:
            return None
        reconciled_state = dict(state)
        reconciled_state.update(
            canonical_dispatch_envelope=expected,
            workforce_dispatch={
                **reconciled_dispatch,
                "canonical_dispatch_envelope": expected,
            },
        )
        _service_module().SelfHostedTaskService._assert_persisted_workforce_dispatch(
            reconciled_state,
            reconciled_request,
            reconciled_dispatch,
        )
    except (KeyError, RuntimeError, TypeError, ValueError):
        return None
    return reconciled_dispatch


def _validated_action_request(
    request: Mapping[str, Any],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    """Validate the physical action payload before resolving task state."""
    if "action" not in request and "bound_action_request" not in request:
        return dict(request), None

    raw_action = request.get("action")
    if not isinstance(raw_action, Mapping):
        raise ValueError("ACTION_ENVELOPE_INVALID")
    raw_bound = request.get("bound_action_request")
    if not isinstance(raw_bound, Mapping):
        raise ValueError("BOUND_ACTION_REQUEST_REQUIRED")
    try:
        envelope = _service_module().LifecycleActionEnvelope.model_validate(raw_action)
    except Exception as exc:
        raise ValueError(f"ACTION_ENVELOPE_INVALID: {exc}") from exc
    if envelope.action_type not in {
        _service_module().LifecycleActionType.TASK_RUN,
        _service_module().LifecycleActionType.TASK_RETRY,
    }:
        raise ValueError("ACTION_TYPE_UNSUPPORTED_FOR_TASK_SUBMISSION")

    bound = dict(raw_bound)
    if _service_module().canonical_request_hash(bound) != envelope.request_hash:
        raise ValueError("BOUND_ACTION_REQUEST_HASH_MISMATCH")
    for field in (
        "task_id",
        "attempt_id",
        "action_id",
        "idempotency_key",
        "action_type",
        "contract_kind",
    ):
        if field not in bound:
            raise ValueError(f"ACTION_IDENTITY_MISSING: {field}")
    for field, expected in (
        ("task_card_path", envelope.task_card_path),
        ("task_card_hash", envelope.task_card_hash),
        ("contract_hash", envelope.contract_hash),
    ):
        if expected is not None and field not in bound:
            raise ValueError(f"ACTION_IDENTITY_MISSING: {field}")
    if envelope.expected_head is not None and not {
        "controller_revision",
        "expected_head",
    }.intersection(bound):
        raise ValueError("ACTION_IDENTITY_MISSING: expected_head")
    if not {"allowed_files", "allowed_paths"}.intersection(bound):
        raise ValueError("ACTION_IDENTITY_MISSING: allowed_paths")

    def require_match(source: Mapping[str, Any], field: str, expected: Any) -> None:
        if field in source and source[field] != expected:
            raise ValueError(f"ACTION_IDENTITY_MISMATCH: {field}")

    identity_fields = (
        ("task_id", envelope.task_id),
        ("attempt_id", envelope.attempt_id),
        ("action_id", envelope.action_id),
        ("idempotency_key", envelope.idempotency_key),
        ("action_type", envelope.action_type.value),
        ("task_card_path", envelope.task_card_path),
        ("task_card_hash", envelope.task_card_hash),
        ("contract_kind", envelope.contract_kind.value),
        ("contract_hash", envelope.contract_hash),
    )
    for field, expected in identity_fields:
        require_match(bound, field, expected)
        require_match(request, field, expected)
    require_match(request, "action_request_hash", envelope.request_hash)
    require_match(request, "request_hash", envelope.request_hash)

    for source in (bound, request):
        require_match(source, "controller_revision", envelope.expected_head)
        require_match(source, "expected_head", envelope.expected_head)
    # #1579: the optional RIE knowledge identity hint is only honoured from the
    # signed request; an outer copy must match it exactly (an outer hint next to
    # a request signed without one is refused, not ignored).
    if "rie_knowledge_identity" in request and (
        request["rie_knowledge_identity"] != bound.get("rie_knowledge_identity")
    ):
        raise ValueError("ACTION_IDENTITY_MISMATCH: rie_knowledge_identity")
    # #1579: the optional codeintel lookup target follows the same rule.
    if "codeintel_lookup" in request and (
        request["codeintel_lookup"] != bound.get("codeintel_lookup")
    ):
        raise ValueError("ACTION_IDENTITY_MISMATCH: codeintel_lookup")
    expected_paths = tuple(envelope.allowed_paths)
    for source in (bound, request):
        if "allowed_files" in source and tuple(source["allowed_files"]) != expected_paths:
            raise ValueError("ACTION_IDENTITY_MISMATCH: allowed_paths")
        if "allowed_paths" in source and tuple(source["allowed_paths"]) != expected_paths:
            raise ValueError("ACTION_IDENTITY_MISMATCH: allowed_paths")

    effective = dict(bound)
    effective["action"] = envelope.model_dump(mode="json")
    effective["bound_action_request"] = dict(bound)
    for field, expected in identity_fields:
        if expected is not None:
            effective[field] = expected
    if envelope.expected_head is not None:
        effective["controller_revision"] = envelope.expected_head
    if envelope.allowed_paths and "allowed_files" not in effective:
        effective["allowed_files"] = list(envelope.allowed_paths)
    effective["action_request_hash"] = envelope.request_hash
    binding = _service_module()._validate_project_entry_authority_binding(effective)
    if binding is not None:
        outer_binding = request.get("project_entry_authority_binding")
        if outer_binding is not None:
            if _service_module()._validate_project_entry_authority_binding(request) != binding:
                raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_DUPLICATE_MISMATCH")
        for source in (bound, request):
            if "repository" in source and source["repository"] != binding["repository"]:
                raise ValueError("PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH")
            for key in ("issue", "issue_number"):
                if key in source and source[key] != int(binding["issue_number"]):
                    raise ValueError("PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH")
    return effective, envelope.model_dump(mode="json")


def _validate_project_entry_authority_binding(
    request: Mapping[str, Any],
    *,
    repository: str | None = None,
    issue_number: int | None = None,
) -> dict[str, str] | None:
    """Validate the explicit authority selectors persisted for project entry."""
    raw = request.get("project_entry_authority_binding")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_INVALID")
    required = ("repository", "issue_number", "goal_id", "coordination_scope_id", "canonical_remote", "intended_action_family")
    allowed = set(required) | {"binding_hash"}
    if set(raw) - allowed:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_UNKNOWN_FIELD")
    if any(key not in raw for key in required):
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE")
    if type(raw["issue_number"]) is not int or raw["issue_number"] <= 0:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_ISSUE_INVALID")
    if any(type(raw[key]) is not str or not raw[key].strip() for key in ("repository", "goal_id", "coordination_scope_id", "canonical_remote", "intended_action_family")):
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_INCOMPLETE")
    try:
        action = _service_module().AutonomyActionClass(raw["intended_action_family"])
    except ValueError as exc:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_ACTION_INVALID") from exc
    if repository is not None and str(raw["repository"]) != repository:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH")
    if issue_number is not None and raw["issue_number"] != issue_number:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH")
    if str(raw["canonical_remote"]) != "https://github.com/James3014/Nexus-new.git":
        raise ValueError("PROJECT_ENTRY_AUTHORITY_REMOTE_MISMATCH")
    values = {
        "repository": raw["repository"],
        "issue_number": str(raw["issue_number"]),
        "goal_id": raw["goal_id"],
        "coordination_scope_id": raw["coordination_scope_id"],
        "canonical_remote": raw["canonical_remote"],
        "intended_action_family": action.value,
    }
    expected = _service_module().canonical_request_hash({**values, "issue_number": raw["issue_number"]})
    if type(raw.get("binding_hash")) is not str or raw["binding_hash"] != expected:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_HASH_MISMATCH")
    for field, value in (("authority_goal_id", values["goal_id"]), ("authority_coordination_scope_id", values["coordination_scope_id"]), ("autonomy_goal_id", values["goal_id"])):
        if field in request and request[field] is not None and request[field] != value:
            raise ValueError("PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH")
    raw_submission = request.get("autonomy_submission_binding")
    if isinstance(raw_submission, Mapping) and raw_submission.get("goal_id") is not None and raw_submission["goal_id"] != values["goal_id"]:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_DUPLICATE_MISMATCH")
    return values


def _reject_unbound_project_entry_authority_hints(request: Mapping[str, Any]) -> None:
    """Material authority selectors require the complete persisted binding."""
    if request.get("project_entry_authority_binding") is not None:
        return
    if any(key in request and request.get(key) is not None for key in _service_module()._PROJECT_ENTRY_AUTHORITY_HINTS):
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED")
    contract = request.get("contract")
    if isinstance(contract, Mapping) and contract.get("standing_grant_id") is not None:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED")
    if str(request.get("execution_lane") or "").upper() in {"GOVERNED"}:
        raise ValueError("PROJECT_ENTRY_AUTHORITY_BINDING_REQUIRED")
# fmt: on
