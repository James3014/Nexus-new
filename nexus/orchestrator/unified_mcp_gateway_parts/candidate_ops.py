"""Candidate operations of ``UnifiedMCPGateway``.

Big-file split G10 (Issue #2525). ``_CandidateOpsMixin`` holds ``_candidate_approve``,
``_candidate_adopt_external``, ``_validate_external_adoption_result``,
``_candidate_bind_integration`` and ``_candidate_dispose``, moved out of
``nexus/orchestrator/unified_mcp_gateway.py``. Their source lines are verbatim, except that
every gateway-module name they load that tests patch on the gateway module (``_git``,
``CANONICAL_SOURCE_ROOT``, ``SERVER_INSTANCE_ID``, ``pre_action_guard``,
``TOOL_MANIFEST_REVISION``, and the authority / permission collaborators
``_require_bound_controller``, ``resolve_contract_identity``, ``validate_approval_grant`` and
``ControlledIntegrationManager``) or that the gateway defines
(``GatewayInputError``, ``_text``, ``FULL_TOOL_SCHEMA_HASH``, ``PERMISSION_POLICY_HASH``,
``LIFECYCLE_REVISION``, ``GITHUB_REPOSITORY`` and the ``_LEGACY_EPB_*`` constants) is
resolved at call time through ``_gateway()``.

``_candidate_integrate`` (the integration effect owner) stays in the gateway class, as do
the owner authority check (``_require_owner_effect_authority`` / ``_owner_effect_key``) and
the ``_recovery_payload`` / ``_exact_hash`` / ``_safe_slug`` helpers, reached through ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.contracts.lifecycle_action import (
    ContractKind,
    ExternalCandidateAdoptionRequest,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
)
from nexus.contracts.target_integration_lifecycle import ExternalAcceptanceReceipt
from nexus.orchestrator.self_hosted_task_service import candidate_dispose_effect

if TYPE_CHECKING:
    # Typing only: the mutation-admission (and, through it, worker-candidate / model-probe /
    # assist) helpers, including the owner-authority stubs, called through ``self``.
    from nexus.orchestrator.unified_mcp_gateway_parts.mutation_admission import (
        _MutationAdmissionMixin as _CandidateOpsBase,
    )
else:
    _CandidateOpsBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


class _CandidateOpsMixin(_CandidateOpsBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway

        @staticmethod
        def _safe_slug(value: Any, field: str, *, max_length: int = 80) -> str: ...

        @staticmethod
        def _recovery_payload(
            state: Mapping[str, Any],
            *,
            operation: str = "status",
            include_state: bool = False,
        ) -> dict[str, Any]: ...

    # fmt: off
    def _candidate_approve(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _gateway()._require_bound_controller()
        task_id = _gateway()._text(arguments.get("task_id"), "task_id")
        candidate_commit_sha = self._exact_hash(arguments.get("candidate_commit_sha"), "candidate_commit_sha", 40)
        candidate_tree_sha = self._exact_hash(arguments.get("candidate_tree_sha"), "candidate_tree_sha", 40)
        candidate_state_hash = self._exact_hash(arguments.get("candidate_state_hash"), "candidate_state_hash", 64)
        verified_receipt_hash = self._exact_hash(arguments.get("verified_receipt_hash"), "verified_receipt_hash", 64)
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise _gateway().GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise _gateway().GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        try:
            identity = _gateway().resolve_contract_identity(state, expected_task_id=task_id, expected_head=base)
        except RuntimeError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
        contract_kind = identity["contract_kind"]
        contract_hash = identity["contract_hash"]
        task_card_hash = identity["task_card_hash"]
        owner_inline_contract = identity["owner_inline_contract"]
        if contract_kind == ContractKind.TRACKED_TASK_CARD.value and not re.fullmatch(r"[0-9a-f]{64}", task_card_hash):
            raise _gateway().GatewayInputError("CANDIDATE_TASK_CARD_HASH_REQUIRED")
        if contract_kind == ContractKind.OWNER_INLINE.value and not contract_hash:
            raise _gateway().GatewayInputError("CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED")
        approval_receipt = _gateway().validate_approval_grant(
            arguments.get("approval"),
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=task_card_hash,
            contract_kind=contract_kind,
            contract_hash=contract_hash,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            full_tool_schema_hash=_gateway().FULL_TOOL_SCHEMA_HASH,
            permission_policy_hash=_gateway().PERMISSION_POLICY_HASH,
            lifecycle_revision=_gateway().LIFECYCLE_REVISION,
            server_instance_id=_gateway().SERVER_INSTANCE_ID,
        )
        action_request = {**dict(arguments), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),  # pyright: ignore[reportOptionalMemberAccess]
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),  # pyright: ignore[reportOptionalMemberAccess]
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_APPROVE,
            request=action_request,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=[],
            mutation=True,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.LIFECYCLE_STATE,
        )
        guard_receipt = _gateway().pre_action_guard(action, request={}, current_head=base, tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION)
        result = self.service.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
            approval_context={**dict(arguments.get("approval") or {}), "validation_receipt": approval_receipt},
        )
        payload = self._recovery_payload(result, operation="candidate_approve", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["approval_receipt"] = approval_receipt
        return payload

    def _candidate_adopt_external(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Adopt one externally accepted Candidate, stopping at approval pending.

        The gateway owns only the public/runtime and Owner-authority boundary;
        physical Candidate verification remains exclusively in the lifecycle
        service.  Keep the transport envelope closed so callers cannot smuggle
        internal state or downstream approval/integration fields.
        """
        _gateway()._require_bound_controller()
        runtime_fields = {
            "server_instance_id", "lifecycle_revision", "full_tool_schema_hash",
            "permission_policy_hash", "controller_repo_root", "controller_branch",
            "controller_head", "campaign_id", "spec_id", "spec_sha256",
            "authority_goal_id", "authority_coordination_scope_id",
        }
        required_runtime_fields = runtime_fields - {"campaign_id", "spec_id", "spec_sha256"}
        request_fields = set(ExternalCandidateAdoptionRequest.model_fields)
        unknown = set(arguments) - request_fields - runtime_fields
        if unknown:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SCHEMA_CLOSED")
        missing_runtime = required_runtime_fields - set(arguments)
        if missing_runtime:
            raise _gateway().GatewayInputError(
                "CANDIDATE_ADOPTION_RUNTIME_BINDING_REQUIRED:" + ",".join(sorted(missing_runtime))
            )
        if str(arguments["server_instance_id"]) != _gateway().SERVER_INSTANCE_ID:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVER_INSTANCE_MISMATCH")
        if str(arguments["lifecycle_revision"]) != _gateway().LIFECYCLE_REVISION:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_LIFECYCLE_REVISION_MISMATCH")
        if str(arguments["full_tool_schema_hash"]) != _gateway().FULL_TOOL_SCHEMA_HASH:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_TOOL_SCHEMA_MISMATCH")
        if str(arguments["permission_policy_hash"]) != _gateway().PERMISSION_POLICY_HASH:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_PERMISSION_POLICY_MISMATCH")
        legacy_fields = {"campaign_id", "spec_id", "spec_sha256"}
        supplied_legacy_fields = legacy_fields & set(arguments)
        if supplied_legacy_fields and supplied_legacy_fields != legacy_fields:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_LEGACY_METADATA_INCOMPLETE")
        legacy_metadata = None
        if supplied_legacy_fields:
            legacy_metadata = {
                "campaign_id": str(arguments["campaign_id"]).strip(),
                "spec_id": str(arguments["spec_id"]).strip(),
                "spec_sha256": str(arguments["spec_sha256"]).strip(),
            }
            if legacy_metadata != {
                "campaign_id": _gateway()._LEGACY_EPB_CAMPAIGN_ID,
                "spec_id": _gateway()._LEGACY_EPB_SPEC_ID,
                "spec_sha256": _gateway()._LEGACY_EPB_SPEC_SHA256,
            }:
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_LEGACY_METADATA_MISMATCH")
        if str(arguments.get("repository")) != _gateway().GITHUB_REPOSITORY.repository_id:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_REPOSITORY_MISMATCH")

        controller_root = Path(str(arguments["controller_repo_root"])).expanduser().resolve()
        if controller_root != _gateway().CANONICAL_SOURCE_ROOT.resolve():
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_CONTROLLER_ROOT_MISMATCH")
        current_branch = _gateway()._git("branch", "--show-current").strip()
        if str(arguments["controller_branch"]) != current_branch:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_CONTROLLER_BRANCH_MISMATCH")
        current_head = _gateway()._git("rev-parse", "HEAD").strip()
        if str(arguments["controller_head"]) != current_head:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_CONTROLLER_HEAD_MISMATCH")
        if str(arguments.get("controller_head")) != str(arguments.get("controller_revision")):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_CONTROLLER_REVISION_MISMATCH")

        request_data = {key: arguments[key] for key in request_fields if key in arguments}
        try:
            request = ExternalCandidateAdoptionRequest.model_validate(request_data)
        except Exception as exc:
            raise _gateway().GatewayInputError(f"CANDIDATE_ADOPTION_REQUEST_INVALID:{exc}") from exc
        if request.action.tool_manifest_hash != _gateway().TOOL_MANIFEST_REVISION:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_ACTION_MANIFEST_MISMATCH")
        if request.tool_manifest_hash != _gateway().TOOL_MANIFEST_REVISION:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_REQUEST_MANIFEST_MISMATCH")
        if request.action.expected_head != request.controller_revision:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_ACTION_HEAD_MISMATCH")
        effect = {
            "repository": request.repository,
            "task_id": request.task_id,
            "attempt_id": request.attempt_id,
            "action_id": request.action_id,
            "idempotency_key": request.idempotency_key,
            "task_card_path": request.task_card_path,
            "task_card_hash": request.task_card_hash,
            "target_base_revision": request.target_base_revision,
            "controller_revision": request.controller_revision,
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_diff_sha256": request.candidate_diff_sha256,
            "validation_receipt_sha256": request.validation_receipt_sha256,
            "acceptance_receipt_sha256": request.acceptance_receipt_sha256,
            "adoption_request_hash": request.semantic_hash(),
            "server_instance_id": _gateway().SERVER_INSTANCE_ID,
            "lifecycle_revision": _gateway().LIFECYCLE_REVISION,
            "tool_manifest_hash": _gateway().TOOL_MANIFEST_REVISION,
            "full_tool_schema_hash": _gateway().FULL_TOOL_SCHEMA_HASH,
            "permission_policy_hash": _gateway().PERMISSION_POLICY_HASH,
            "controller_repo_root": str(controller_root),
            "controller_branch": current_branch,
            "controller_head": current_head,
            "action": request.action.model_dump(mode="json"),
        }
        if legacy_metadata is not None:
            effect.update(legacy_metadata)
        owner_authority = self._require_owner_effect_authority(
            AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL, effect,
            key=self._owner_effect_key(arguments),
        )
        rebound_root = Path(str(arguments["controller_repo_root"])).expanduser().resolve()
        rebound_branch = _gateway()._git("branch", "--show-current").strip()
        rebound_head = _gateway()._git("rev-parse", "HEAD").strip()
        if rebound_root != controller_root or rebound_branch != current_branch or rebound_head != current_head:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_CONTROLLER_DRIFT_AFTER_AUTHORITY")
        if rebound_head != request.controller_revision:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_CONTROLLER_REVISION_DRIFT_AFTER_AUTHORITY")
        result = self.service.adopt_external_candidate(request)
        self._validate_external_adoption_result(result, request)
        return {
            "schema": "nexus.candidate_adoption_gateway_result.v1",
            "operation": "candidate_adopt_external",
            "task_id": result.get("task_id"),
            "status": result.get("status"),
            "promotion_status": result.get("promotion_status"),
            "candidate_commit_sha": result.get("candidate_commit_sha"),
            "candidate_tree_sha": result.get("candidate_tree_sha"),
            "candidate_state_hash": result.get("candidate_state_hash"),
            "verified_receipt_hash": result.get("verified_receipt_hash"),
            "candidate_ref": result.get("candidate_ref"),
            "adoption_receipt": result.get("adoption_receipt"),
            "adoption_receipt_hash": result.get("adoption_receipt_hash"),
            "owner_authority": owner_authority,
            "claim_ceiling": [
                "CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY",
                "NO_APPROVAL", "NO_INTEGRATION", "NO_MERGE", "NO_PUSH",
                "NO_RELEASE", "NO_PRODUCTION",
            ],
        }

    @staticmethod
    def _validate_external_adoption_result(
        result: Any,
        request: ExternalCandidateAdoptionRequest | None = None,
    ) -> None:
        if not isinstance(result, Mapping):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_INVALID")
        if result.get("status") != "PENDING_HUMAN_APPROVAL" or result.get("promotion_status") != "PENDING_HUMAN_APPROVAL":
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_NOT_PENDING")
        authority_tokens = (
            "approval", "approved", "integrat", "merge", "push",
            "release", "activat", "deploy", "production",
        )

        def is_negative(value: Any) -> bool:
            return value in (
                None, False, "", "PENDING", "NOT_CREATED",
                "PENDING_HUMAN_APPROVAL", [], {},
            )

        for key, value in result.items():
            if any(token in key.lower() for token in authority_tokens) and not is_negative(value):
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_UNEXPECTED_DOWNSTREAM_FIELD")
        adoption_receipt = result.get("adoption_receipt")
        adoption_receipt_hash = str(result.get("adoption_receipt_hash") or "")
        if not isinstance(adoption_receipt, Mapping) or not re.fullmatch(r"[0-9a-f]{64}", adoption_receipt_hash):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_REQUIRED")
        computed_receipt_hash = hashlib.sha256(json.dumps(
            dict(adoption_receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        if computed_receipt_hash != adoption_receipt_hash:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_HASH_MISMATCH")
        receipt_fields = {
            "schema", "task_id", "attempt_id", "action_id", "idempotency_key",
            "adoption_request_hash", "task_card_path", "task_card_hash", "contract_hash",
            "controller_revision", "target_base_revision", "candidate_commit_sha",
            "candidate_tree_sha", "candidate_diff_sha256", "candidate_state_hash",
            "verified_receipt_hash", "validation_receipt_sha256",
            "acceptance_receipt_sha256", "repository_contract_policy_revision_hash",
            "derived_contract_projection", "forbidden_repository_patterns", "reviewer_id",
            "candidate_ref", "promotion_packet_hash", "worker_invocations",
            "candidate_rewritten", "approval_performed", "integration_performed",
            "merge_performed", "push_performed", "public_claim_allowed",
            "production_ready", "claim_ceiling", "issued_at",
        }
        if set(adoption_receipt) != receipt_fields:
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_FIELDS_INVALID")
        if (
            adoption_receipt.get("schema") != "nexus.external_candidate_adoption_receipt.v1"
            or adoption_receipt.get("worker_invocations") != 0
            or adoption_receipt.get("candidate_rewritten") is not False
            or adoption_receipt.get("approval_performed") is not False
            or adoption_receipt.get("integration_performed") is not False
            or adoption_receipt.get("merge_performed") is not False
            or adoption_receipt.get("push_performed") is not False
            or adoption_receipt.get("public_claim_allowed") is not False
            or adoption_receipt.get("production_ready") is not False
            or adoption_receipt.get("claim_ceiling")
            != ["CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY"]
        ):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_SEMANTICS_INVALID")
        if request is not None:
            expected_subject = {
                "task_id": request.task_id,
                "attempt_id": request.attempt_id,
                "action_id": request.action_id,
                "idempotency_key": request.idempotency_key,
                "adoption_request_hash": request.semantic_hash(),
                "task_card_path": request.task_card_path,
                "task_card_hash": request.task_card_hash,
                "controller_revision": request.controller_revision,
                "target_base_revision": request.target_base_revision,
                "candidate_commit_sha": request.candidate_commit_sha,
                "candidate_tree_sha": request.candidate_tree_sha,
                "candidate_diff_sha256": request.candidate_diff_sha256,
                "validation_receipt_sha256": request.validation_receipt_sha256,
                "acceptance_receipt_sha256": request.acceptance_receipt_sha256,
            }
            if any(adoption_receipt.get(key) != value for key, value in expected_subject.items()):
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_SUBJECT_MISMATCH")
        for field in (
            "contract_hash", "candidate_state_hash", "verified_receipt_hash",
            "repository_contract_policy_revision_hash", "promotion_packet_hash",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(adoption_receipt.get(field) or "")):
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_HASH_FIELD_INVALID")
        if (
            result.get("candidate_commit_sha") != adoption_receipt.get("candidate_commit_sha")
            or result.get("candidate_tree_sha") != adoption_receipt.get("candidate_tree_sha")
            or result.get("candidate_state_hash") != adoption_receipt.get("candidate_state_hash")
            or result.get("verified_receipt_hash") != adoption_receipt.get("verified_receipt_hash")
            or result.get("candidate_ref") != adoption_receipt.get("candidate_ref")
        ):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_STATE_MISMATCH")
        for key, value in adoption_receipt.items():
            if any(token in key.lower() for token in authority_tokens) and not is_negative(value):
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_RECEIPT_DOWNSTREAM_EFFECT")
        allowed_downstream_fields = {
            "approved_binding", "integration_authorization", "integration_receipt",
            "merge_performed", "push_performed", "production_ready",
        }
        downstream_prefixes = (
            "approval_", "approved_", "integration_", "merge_", "push_",
            "release_", "activation_", "deployment_", "production_",
        )
        unexpected_downstream = sorted(
            key for key in result
            if key.startswith(downstream_prefixes) and key not in allowed_downstream_fields
        )
        if unexpected_downstream or any(
            key in result for key in ("final_disposition", "terminal_status", "release_receipt")
        ):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_UNEXPECTED_DOWNSTREAM_FIELD")
        for field in ("approved_binding", "integration_authorization", "integration_receipt"):
            if result.get(field) not in (None, {}):
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_DOWNSTREAM_AUTHORITY")
        for field in ("merge_performed", "push_performed", "public_claim_allowed", "production_ready"):
            if result.get(field) is not False:
                raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_DOWNSTREAM_EFFECT")
        ceiling = result.get("claim_ceiling")
        if ceiling is not None and (
            not isinstance(ceiling, (list, tuple)) or any(
                any(token in str(item).upper() for token in ("APPROVED", "INTEGRATED", "MERGE", "PUSH", "PRODUCTION"))
                for item in ceiling
            )
        ):
            raise _gateway().GatewayInputError("CANDIDATE_ADOPTION_SERVICE_RESULT_CLAIM_CEILING")

    def _candidate_bind_integration(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _gateway()._require_bound_controller()
        forbidden = {"integration_authorization", "action_set", "approval_context", "shell"}
        if forbidden.intersection(arguments):
            raise _gateway().GatewayInputError("CLOSURE_SCHEMA_CLOSED")
        task_id = _gateway()._text(arguments.get("task_id"), "task_id")
        branch = str(arguments.get("integration_branch") or "nexus/integration/main").strip()
        expected_head = _gateway()._text(arguments.get("expected_canonical_head"), "expected_canonical_head")
        if not re.fullmatch(r"[0-9a-f]{40}", expected_head):
            raise _gateway().GatewayInputError("expected_canonical_head is invalid")
        if not branch or branch.startswith("-") or any(char in branch for char in "\n\r"):
            raise _gateway().GatewayInputError("integration_branch is invalid")
        raw_acceptance = arguments.get("external_acceptance")
        raw_approval = arguments.get("approval")
        if not isinstance(raw_acceptance, Mapping) or not isinstance(raw_approval, Mapping):
            raise _gateway().GatewayInputError("typed external_acceptance and approval are required")
        try:
            acceptance = ExternalAcceptanceReceipt(**dict(raw_acceptance))
        except Exception as exc:
            raise _gateway().GatewayInputError(f"EXTERNAL_ACCEPTANCE_INVALID: {exc}") from exc
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise _gateway().GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise _gateway().GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        try:
            identity = _gateway().resolve_contract_identity(state, expected_task_id=task_id, expected_head=base)
        except RuntimeError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        controller_root = Path(str(contract.get("controller_repo_root") or _gateway().CANONICAL_SOURCE_ROOT)).expanduser().resolve()  # pyright: ignore[reportOptionalMemberAccess]
        # A separate detached Controller binds the integration branch ref,
        # not its HEAD (#2230); every other shape keeps binding HEAD.
        try:
            separate_head = _gateway().ControlledIntegrationManager.separate_controller_integration_head(controller_root, branch)
        except RuntimeError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
        if separate_head is not None:
            live_head = separate_head
        else:
            live_head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_root, capture_output=True, text=True, check=False)
            live_head = live_head_result.stdout.strip()
            if live_head_result.returncode != 0:
                raise _gateway().GatewayInputError("CANDIDATE_BIND_HEAD_DRIFT")
        if live_head != expected_head:
            raise _gateway().GatewayInputError("CANDIDATE_BIND_HEAD_DRIFT")
        allowed_files = [str(path) for path in contract.get("allowed_files") or [] if str(path).strip()]  # pyright: ignore[reportOptionalMemberAccess]
        if not allowed_files:
            raise _gateway().GatewayInputError("CANDIDATE_ALLOWED_PATHS_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        action_request = {"task_id": task_id, "integration_branch": branch, "expected_canonical_head": expected_head, "external_acceptance": dict(raw_acceptance), "approval": dict(raw_approval), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),  # pyright: ignore[reportOptionalMemberAccess]
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),  # pyright: ignore[reportOptionalMemberAccess]
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE,
            request=action_request,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=expected_head,
            allowed_paths=allowed_files,
            mutation=True,
            permission_profile=PermissionProfile.INTEGRATE,
            mutation_domain=MutationDomain.LIFECYCLE_STATE,
        )
        guard_receipt = _gateway().pre_action_guard(action, request={"allowed_files": allowed_files}, current_head=live_head, tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION)
        result = self.service.bind_candidate_integration_closure(
            task_id,
            external_acceptance=acceptance,
            approval=raw_approval,
            expected_canonical_head=expected_head,
            integration_branch=branch,
            runtime_identity={
                **identity,
                "tool_manifest_hash": _gateway().TOOL_MANIFEST_REVISION,
                "full_tool_schema_hash": _gateway().FULL_TOOL_SCHEMA_HASH,
                "permission_policy_hash": _gateway().PERMISSION_POLICY_HASH,
                "lifecycle_revision": _gateway().LIFECYCLE_REVISION,
                "server_instance_id": _gateway().SERVER_INSTANCE_ID,
            },
        )
        payload = self._recovery_payload(result, operation="candidate_bind_integration", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["integration_performed"] = False
        return payload

    def _candidate_dispose(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "task_id", "disposition", "superseded_by",
            "authority_goal_id", "authority_coordination_scope_id",
        }
        unknown_keys = set(arguments) - allowed_keys
        if unknown_keys:
            raise _gateway().GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        owner_key = self._owner_effect_key(arguments)
        task_id = _gateway()._text(arguments.get("task_id"), "task_id")
        disposition = str(arguments.get("disposition") or "").strip().upper()
        if disposition not in {"REJECTED", "SUPERSEDED"}:
            raise _gateway().GatewayInputError("disposition must be REJECTED or SUPERSEDED")
        superseded_by = str(arguments.get("superseded_by") or "").strip() or None
        if disposition == "SUPERSEDED" and not superseded_by:
            raise _gateway().GatewayInputError("superseded_by is required for SUPERSEDED")
        if superseded_by is not None:
            superseded_by = self._safe_slug(superseded_by, "superseded_by")
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise _gateway().GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise _gateway().GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        try:
            contract_identity = _gateway().resolve_contract_identity(
                state,
                expected_task_id=task_id,
                expected_head=base,
            )
        except RuntimeError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
        owner_action = (
            AutonomyActionClass.CANDIDATE_REJECT
            if disposition == "REJECTED"
            else AutonomyActionClass.CANDIDATE_SUPERSEDE
        )
        owner_authority = self._require_owner_effect_authority(
            owner_action,
            candidate_dispose_effect(
                state,
                task_id=task_id,
                controller_revision=base,
                contract_identity=contract_identity,
                disposition=disposition,
                superseded_by=superseded_by,
            ),
            key=owner_key,
        )
        action_request = {**dict(arguments), "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),  # pyright: ignore[reportOptionalMemberAccess]
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),  # pyright: ignore[reportOptionalMemberAccess]
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),  # pyright: ignore[reportOptionalMemberAccess]
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_DISPOSE,
            request=action_request,
            tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=base,
            allowed_paths=[],
            mutation=True,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.CANDIDATE_REF,
        )
        guard_receipt = _gateway().pre_action_guard(action, request={}, current_head=base, tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION)
        result = self.service.dispose_candidate(task_id, disposition=disposition, superseded_by=superseded_by)
        payload = self._recovery_payload(result, operation="candidate_dispose", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["owner_authority"] = owner_authority
        return payload
    # fmt: on
