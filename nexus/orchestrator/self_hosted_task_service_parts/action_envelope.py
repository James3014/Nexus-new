"""Task-action envelope and approval projections of ``SelfHostedTaskService``.

Big-file split S6a (Issue #2568). ``_ActionEnvelopeMixin`` holds the pure projections
moved out of ``nexus/orchestrator/self_hosted_task_service.py``: ``_candidate_commit``,
``_terminal_failure_blocker``, ``_projected_blocker``,
``_settled_candidate_less_final_block``, ``_task_action_envelope``, ``_with_task_action``
and ``_approval_requirements``. Their source lines are verbatim, except that every
facade-module name they load (the status sets ``INVALID_STATE_STATUSES``,
``DURABLE_SELF_HOSTED_STATUSES``, ``PENDING_CANDIDATE_STATUSES``, ``TERMINAL_STATUSES``,
``ACTIVE_EXECUTION_STATUSES``, ``RESUMABLE_STATUSES`` and ``_bounded_failure_text``) is
resolved at call time through ``_service_module()``, so patches on the facade keep taking
effect; the status sets stay imported (from ``nexus_runtime.task_lifecycle``) by the
facade only.

They take no lock and do no I/O: they map a state mapping to a new value and never mutate
their input. The state lock and the state store stay in the facade class, which still
computes the persisted ``task_action`` (``_normalize_state_write``) and the read-side one
(``_validate_state_payload`` / ``_invalid_state_status``) through these methods via
``cls`` / ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from typing import Any, Mapping, Optional


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _ActionEnvelopeMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    # fmt: off
    @staticmethod
    def _candidate_commit(state: Mapping[str, Any]) -> Optional[str]:
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        return state.get("candidate_commit_sha") or packet.get("candidate_commit_sha")  # pyright: ignore[reportOptionalMemberAccess]

    @classmethod
    def _terminal_failure_blocker(cls, state: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if str(state.get("status") or "") not in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
            return None
        raw_error = str(state.get("error") or "")
        error = raw_error.strip()
        if not error:
            return None
        request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        evidence: dict[str, Any] = {
            "code": "WORKER_EXECUTION_FAILED",
            "detail": _service_module()._bounded_failure_text("worker execution failed"),
            "error_sha256": hashlib.sha256(raw_error.encode("utf-8")).hexdigest(),
            "failure_stage": "worker_execution",
        }
        provider = str(state.get("worker_provider") or request.get("provider") or "").strip()  # pyright: ignore[reportOptionalMemberAccess]
        model = str(request.get("model") or "").strip()  # pyright: ignore[reportOptionalMemberAccess]
        if provider:
            evidence["provider"] = provider
        if model:
            evidence["model"] = model
        if state.get("exit_code") is not None:
            try:
                evidence["exit_code"] = int(state["exit_code"])
            except (TypeError, ValueError):
                pass
        if state.get("execution_outcome"):
            evidence["execution_outcome"] = str(state["execution_outcome"])
        return evidence

    @classmethod
    def _projected_blocker(cls, state: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        if "blocker" in state and state["blocker"] is not None:
            return state["blocker"]
        return cls._terminal_failure_blocker(state)

    @classmethod
    def _settled_candidate_less_final_block(cls, state: Mapping[str, Any]) -> bool:
        """Identify a terminal failure whose retry is historical, not required."""
        if (
            state.get("status") != "FINAL_BLOCK"
            or state.get("promotion_status") != "NOT_CREATED"
            or state.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            or state.get("cleanup_blocker")
            or state.get("reconciliation_required") is True
            or state.get("reconciliation_status") not in {None, "RECONCILED", "NOT_REQUIRED"}
            or state.get("reconciliation_decision") not in {None, "NO_MUTATION_OBSERVED"}
            or state.get("uncertain_mutation") is True
            or state.get("candidate_created") not in {None, False}
            or state.get("candidate_status") not in {None, "", "NOT_CREATED", "FINAL_BLOCK"}
            or state.get("state_retention_status") not in {None, "TERMINAL", "ARCHIVED"}
            or state.get("approved_binding")
            or state.get("integration_receipt")
            or state.get("integration_result_sha")
            or state.get("merge_performed")
        ):
            return False

        candidate = state.get("promotion_packet")
        candidate_fields = (
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
            "candidate_ref",
        )
        if any(state.get(field) for field in candidate_fields):
            return False
        if isinstance(candidate, Mapping) and any(candidate.get(field) for field in candidate_fields):
            return False
        return True

    @classmethod
    def _task_action_envelope(cls, state: Mapping[str, Any]) -> dict[str, Any]:
        status = str(state.get("status") or "UNKNOWN")
        promotion_status = str(state.get("promotion_status") or "")
        candidate_commit = cls._candidate_commit(state)

        if status in _service_module().INVALID_STATE_STATUSES or status not in _service_module().DURABLE_SELF_HOSTED_STATUSES:
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "inspect_lifecycle_state"
            recommended_tool = None
        elif status == "DIRECT_RECONCILE_REQUIRED" and state.get("reconciliation_decision") == "RETAINED_FOR_REVIEW":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "inspect_receipt_and_candidate"
            recommended_tool = "nexus_task_status"
        elif status == "DIRECT_RECONCILE_REQUIRED":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "nexus_task_reconcile"
            recommended_tool = "nexus_task_reconcile"
        elif status == "DIRECT_COMPLETED":
            action_state = "TERMINAL"
            attention_required = False
            next_action = "none"
            recommended_tool = None
        elif status in {"DIRECT_INTENT_RECORDED", "DIRECT_STARTED", "DIRECT_APPLIED", "DIRECT_VERIFIED", "DIRECT_COMMITTED"}:
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "nexus_task_finish"
            recommended_tool = "nexus_task_finish"
        elif status == "INTEGRATING":
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "wait_for_task"
            recommended_tool = "nexus_self_hosted_wait_task"
        elif status == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "owner_review_post_apply_failure"
            recommended_tool = "nexus_self_hosted_get_receipt"
        elif status == "INTEGRATION_FAILED_PRE_APPLY":
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "retry_integration_same_task"
            recommended_tool = "nexus_self_hosted_retry_integration"
        elif status == "INTEGRATED_TARGET_RETAINED":
            action_state = "ACTION_REQUIRED"
            attention_required = True
            next_action = "retry_cleanup"
            recommended_tool = "nexus_self_hosted_cleanup"
        elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
            action_state = "FINAL_BLOCK"
            attention_required = True
            cleanup_removed = state.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            verified_uncommitted = bool(
                (state.get("verified_receipt") or {}).get("verified")
                and (state.get("attempt_resolution") or {}).get("verdict") == "PROVEN"
                and not candidate_commit
                and not cleanup_removed
            )
            if status == "INTEGRATION_FAILED" and not state.get("merge_performed"):
                next_action = "retry_integration_same_task"
                recommended_tool = "nexus_self_hosted_retry_integration"
            elif verified_uncommitted:
                next_action = "recover_verified_candidate"
                recommended_tool = "nexus_self_hosted_recover_verified_uncommitted_candidate"
            elif status == "RETAINED_FOR_REVIEW" and state.get("cleanup_decision") == "BLOCKED_BY_UNSAVED_CHANGES":
                next_action = "salvage_or_dispose_retained_target"
                recommended_tool = "nexus_self_hosted_cleanup"
            elif status == "FINAL_BLOCK" and not candidate_commit and promotion_status == "NOT_CREATED" and cleanup_removed:
                next_action = "retry_same_task"
                recommended_tool = "nexus_self_hosted_retry"
            else:
                next_action = "inspect_receipt_and_candidate"
                recommended_tool = "nexus_self_hosted_get_receipt"
            if cls._settled_candidate_less_final_block(state):
                action_state = "TERMINAL"
                attention_required = False
        elif status in (_service_module().PENDING_CANDIDATE_STATUSES - {"INTEGRATING"}) or promotion_status in {"PENDING_HUMAN_APPROVAL", "APPROVED", "APPROVAL_INVALIDATED"}:
            action_state = "ACTION_REQUIRED"
            attention_required = True
            if promotion_status == "APPROVED" or status == "APPROVED":
                next_action = "integrate_approved_candidate"
                recommended_tool = "nexus_self_hosted_integrate_approved"
            elif promotion_status == "APPROVAL_INVALIDATED" or status == "APPROVAL_INVALIDATED":
                next_action = "resubmit_exact_approval_binding"
                recommended_tool = "nexus_candidate_approve"
            else:
                next_action = "approve_candidate"
                recommended_tool = "nexus_candidate_approve"
        elif status in _service_module().TERMINAL_STATUSES:
            action_state = "TERMINAL"
            attention_required = False
            next_action = "none"
            recommended_tool = None
        elif status in (_service_module().ACTIVE_EXECUTION_STATUSES | _service_module().RESUMABLE_STATUSES):
            action_state = "IN_PROGRESS"
            attention_required = False
            next_action = "wait_for_task"
            recommended_tool = "nexus_self_hosted_wait_task"
        else:
            action_state = "FINAL_BLOCK"
            attention_required = True
            next_action = "inspect_lifecycle_state"
            recommended_tool = None

        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        return {
            "schema": "nexus.self_hosted_task_action.v1",
            "task_id": state.get("task_id"),
            "task_status": status,
            "promotion_status": promotion_status or None,
            "action_state": action_state,
            "attention_required": attention_required,
            "next_action": next_action,
            "recommended_tool": recommended_tool,
            "candidate_commit_sha": candidate_commit,
            "candidate_ref": state.get("candidate_ref"),
            "candidate": {
                "candidate_commit_sha": candidate_commit,
                "candidate_tree_sha": state.get("candidate_tree_sha") or packet.get("candidate_tree_sha"),  # pyright: ignore[reportOptionalMemberAccess]
                "candidate_state_hash": state.get("candidate_state_hash") or packet.get("candidate_state_hash"),  # pyright: ignore[reportOptionalMemberAccess]
                "verified_receipt_hash": state.get("verified_receipt_hash") or packet.get("verified_receipt_hash"),  # pyright: ignore[reportOptionalMemberAccess]
            },
            "cleanup_status": {
                "cleanup_eligible": state.get("cleanup_eligible", False),
                "cleanup_decision": state.get("cleanup_decision"),
                "cleanup_blocker": state.get("cleanup_blocker"),
                "cleanup_performed": state.get("cleanup_performed", False),
                "cleanup_performed_at": state.get("cleanup_performed_at"),
                "state_retention_status": state.get("state_retention_status"),
                "archive_eligible": state.get("archive_eligible", False),
            },
        }

    @classmethod
    def _with_task_action(cls, state: dict[str, Any]) -> dict[str, Any]:
        state = dict(state)
        state["task_action"] = cls._task_action_envelope(state)
        return state

    @staticmethod
    def _approval_requirements(state: Mapping[str, Any]) -> dict[str, Any]:
        """Project durable Architecture Approval inputs without granting approval."""
        input_reasons: list[str] = []

        def approval_source(name: str) -> Mapping[str, Any]:
            if name not in state:
                return {}
            source = state[name]
            if source is None:
                return {}
            if isinstance(source, Mapping):
                if not source:
                    input_reasons.append(
                        f"malformed_source:{name}:empty_or_missing_contract_fields"
                    )
                return source
            input_reasons.append(f"malformed_source:{name}:expected_mapping")
            return {}

        packet = approval_source("promotion_packet")
        candidate = state.get("candidate") if isinstance(state.get("candidate"), Mapping) else {}
        receipt = approval_source("verified_receipt")

        def values(
            field: str,
            *sources: tuple[str, Mapping[str, Any]],
            pattern: str,
        ) -> list[tuple[str, str]]:
            resolved = []
            for name, source in sources:
                raw = source.get(field)
                if raw is None or raw == "":
                    continue
                if type(raw) is not str:
                    input_reasons.append(f"invalid_type:{name}.{field}")
                    continue
                value = raw.strip()
                if not value:
                    continue
                if not re.fullmatch(pattern, value):
                    input_reasons.append(f"invalid_format:{name}.{field}")
                    continue
                resolved.append((name, value))
            return resolved

        required_values = []
        for name, source in (
            ("promotion_packet", packet),
            ("verified_receipt", receipt),
        ):
            raw = source.get("authority_change_required", False)
            if type(raw) is not bool:
                input_reasons.append(f"invalid_type:{name}.authority_change_required")
                raw = False
            required_values.append((name, raw))
        required = any(value for _, value in required_values)

        approval_shaped = any(
            isinstance(value, Mapping) and value.get("architecture_approval") is not None
            for value in (state.get("approved_binding"), packet, receipt)
        )
        binding = {
            "bound_task_id": "",
            "bound_attempt_id": "",
            "candidate_commit_sha": "",
            "candidate_tree_sha": "",
            "authority_findings_sha256": "",
        }
        for state_field, binding_field in (
            ("task_id", "bound_task_id"),
            ("attempt_id", "bound_attempt_id"),
        ):
            raw = state.get(state_field)
            if raw is None or raw == "":
                continue
            if type(raw) is not str:
                input_reasons.append(f"invalid_type:task.{state_field}")
                continue
            binding[binding_field] = raw.strip()
        if state.get("state_valid") is False:
            blocker = state.get("blocker") if isinstance(state.get("blocker"), Mapping) else {}
            source_reasons = blocker.get("approval_requirements_reasons")  # pyright: ignore[reportOptionalMemberAccess]
            if isinstance(source_reasons, list) and all(
                type(reason) is str and reason for reason in source_reasons
            ):
                input_reasons.extend(source_reasons)
            else:
                code = blocker.get("code") if type(blocker.get("code")) is str else "UNKNOWN"  # pyright: ignore[reportOptionalMemberAccess]
                input_reasons.append(f"invalid_state:{code}")

        field_sources = {
            "candidate_commit_sha": values(
                "candidate_commit_sha",
                ("task", state),
                ("promotion_packet", packet),
                ("candidate", candidate),  # pyright: ignore[reportArgumentType]
                ("verified_receipt", receipt),
                pattern=r"[0-9a-f]{40}",
            )
            + values(
                "commit_sha",
                ("candidate", candidate),  # pyright: ignore[reportArgumentType]
                pattern=r"[0-9a-f]{40}",
            ),
            "candidate_tree_sha": values(
                "candidate_tree_sha",
                ("task", state),
                ("promotion_packet", packet),
                ("candidate", candidate),  # pyright: ignore[reportArgumentType]
                ("verified_receipt", receipt),
                pattern=r"[0-9a-f]{40}",
            )
            + values(
                "tree_sha",
                ("candidate", candidate),  # pyright: ignore[reportArgumentType]
                pattern=r"[0-9a-f]{40}",
            ),
            "authority_findings_sha256": values(
                "authority_findings_sha256",
                ("promotion_packet", packet),
                ("verified_receipt", receipt),
                pattern=r"[0-9a-f]{64}",
            ),
        }
        missing: list[str] = []
        mismatches: list[str] = []
        for field, source_values in field_sources.items():
            unique_values = {value for _, value in source_values}
            if not source_values:
                missing.append(field)
            elif len(unique_values) > 1:
                mismatches.append(field)
            else:
                binding[field] = source_values[0][1]

        if not binding["bound_task_id"]:
            missing.append("bound_task_id")
        if not binding["bound_attempt_id"]:
            missing.append("bound_attempt_id")
        if required_values[0][1] != required_values[1][1] and any(
            value for _, value in required_values
        ):
            mismatches.append("authority_change_required")
        missing = sorted(set(missing))
        mismatches = sorted(set(mismatches))

        stale = approval_shaped or (
            required
            and state.get("promotion_status") in {"APPROVED", "INTEGRATED", "APPROVAL_INVALIDATED"}
        )
        if not required and input_reasons:
            status = "NOT_APPROVABLE"
            completeness = "INCOMPLETE"
            approvability = "NOT_APPROVABLE"
        elif not required:
            status = "NOT_REQUIRED"
            completeness = "NOT_REQUIRED"
            approvability = "NOT_REQUIRED"
        elif stale:
            status = "NOT_APPROVABLE"
            completeness = "INCOMPLETE"
            approvability = "NOT_APPROVABLE"
            missing.append("stale_approval_requirements")
        elif input_reasons or missing or mismatches:
            status = "NOT_APPROVABLE"
            completeness = "INCOMPLETE"
            approvability = "NOT_APPROVABLE"
        else:
            status = "APPROVABLE"
            completeness = "COMPLETE"
            approvability = "APPROVABLE"

        reasons = list(input_reasons)
        if required:
            reasons.extend(f"missing:{field}" for field in missing)
            reasons.extend(f"mismatch:{field}" for field in mismatches)
        if stale:
            reasons.append("stale:approval_requirements")
        return {
            "schema": "nexus.architecture_approval_requirements.v1",
            "required": required,
            "status": status,
            "completeness": completeness,
            "approvability": approvability,
            "task_id": binding["bound_task_id"],
            "attempt_id": binding["bound_attempt_id"],
            "binding": binding,
            "missing": sorted(set(missing)),
            "mismatches": mismatches,
            "reasons": sorted(set(reasons)),
            "stale": stale,
        }
    # fmt: on
