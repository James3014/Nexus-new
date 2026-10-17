"""Owner standing grant and owner-effect authority of ``UnifiedMCPGateway``.

Big-file split G9b (Issue #2548). ``_OwnerAuthorityMixin`` holds the owner-effect authority
check (``_require_owner_effect_authority``, ``_owner_effect_key``, ``_standing_key``), the
Owner standing-grant issuance with its host confirmation and audit
(``_owner_standing_grant_issue``, ``_confirm_with_owner``,
``_append_owner_confirmation_audit``) and the task-card authority switch/restore
(``_task_card_authority_switch``, ``_task_card_authority_restore``), moved out of
``nexus/orchestrator/unified_mcp_gateway.py``. The task-card, mutation-admission,
candidate-operation and Learning code reach the authority check through ``self``.

Their source lines are verbatim, except that every gateway-module name they load other
than the standard library (``authorize_durable_standing_grant_effect``,
``bootstrap_agent_authority``, the standing-grant store functions,
``_standing_grant_store_module``, ``OwnerConfirmationRequest``, ``GITHUB_REPOSITORY``,
``LOADED_SOURCE_ROOT``, ``SERVER_REPO_HEAD_AT_START``, ``SERVER_INSTANCE_ID``,
``GatewayInputError``, ``_text``, ...) is resolved at call time through ``_gateway()``, so
patches on the gateway module keep reaching this code.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from nexus.contracts.autonomy_goal import AutonomyActionClass
    from nexus.orchestrator.standing_grant_store import StandingGrantKey

    # Typing only: the candidate-operation (and, through it, every other mixin) helpers,
    # including the stubs for the members the gateway class provides.
    from nexus.orchestrator.unified_mcp_gateway_parts.candidate_ops import (
        _CandidateOpsMixin as _OwnerAuthorityBase,
    )
else:
    _OwnerAuthorityBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


class _OwnerAuthorityMixin(_OwnerAuthorityBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway
        _owner_confirmation_channel: Any

    # fmt: off
    @staticmethod
    def _require_owner_effect_authority(
        action: AutonomyActionClass,
        effect: Mapping[str, Any],
        *,
        key: StandingGrantKey,
    ) -> dict[str, Any]:
        # #2270: in BOOTSTRAP with a SEPARATE Controller, Task Card binds into
        # that Controller are authorized by the agent identity under the
        # Owner's chat delegation and recorded durably. Every other effect, or
        # these outside that state, still needs the Owner standing grant.
        context = _gateway().bootstrap_agent_authority.delegation_context(
            action,
            source_root=Path(_gateway().LOADED_SOURCE_ROOT),
            controller_binding=_gateway()._current_controller_binding(),
            expected_source_head=_gateway().SERVER_REPO_HEAD_AT_START,
        )
        if context is not None:
            try:
                return _gateway().bootstrap_agent_authority.authorize_bootstrap_agent_effect(
                    repository=_gateway().GITHUB_REPOSITORY,
                    action=action,
                    effect=effect,
                    key=key,
                    context=context,
                    record_directory=_gateway()._standing_grant_store_module.DEFAULT_RECEIPT_PATH.parent,
                    server_instance_id=_gateway().SERVER_INSTANCE_ID,
                )
            except _gateway().bootstrap_agent_authority.BootstrapAgentAuthorityError as exc:
                raise _gateway().GatewayInputError(f"OWNER_AUTHORITY_REQUIRED:{exc}") from exc
        try:
            return _gateway().authorize_durable_standing_grant_effect(
                repository=_gateway().GITHUB_REPOSITORY,
                action=action,
                effect=effect,
                key=key,
            )
        except _gateway().StandingGrantReceiptError as exc:
            raise _gateway().GatewayInputError(f"OWNER_AUTHORITY_REQUIRED:{exc}") from exc

    @staticmethod
    def _owner_effect_key(arguments: Mapping[str, Any]) -> StandingGrantKey:
        """Resolve the explicit Goal/coordination scope for durable effects."""
        try:
            goal_id = _gateway()._text(arguments.get("authority_goal_id"), "authority_goal_id", max_length=128)
            scope_id = _gateway()._text(
                arguments.get("authority_coordination_scope_id"),
                "authority_coordination_scope_id",
                max_length=128,
            )
            return _gateway().StandingGrantKey(_gateway().GITHUB_REPOSITORY, goal_id, scope_id)
        except (_gateway().GatewayInputError, TypeError, ValueError) as exc:
            raise _gateway().GatewayInputError(f"OWNER_AUTHORITY_KEY_REQUIRED:{exc}") from exc

    @staticmethod
    def _standing_key(goal_id: str, thread_id: str) -> StandingGrantKey:
        try:
            return _gateway().StandingGrantKey(_gateway().GITHUB_REPOSITORY, goal_id, thread_id)
        except (TypeError, ValueError) as exc:
            raise _gateway().GatewayInputError(f"OWNER_AUTHORITY_KEY_REQUIRED:{exc}") from exc

    def _owner_standing_grant_issue(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Materialize one explicit Owner-issued keyed standing grant via canonical CAS.

        This public surface is intentionally a thin adapter over the existing
        standing-grant contract/store. It does not evaluate downstream effects,
        execute GitHub actions, or create another grant authority.
        """
        allowed_keys = {
            "repository",
            "coordinatorId",
            "goalId",
            "coordinationScopeId",
            "allowedActions",
            "ttlMinutes",
            "issuedAt",
            "expectedCurrentReceiptHash",
        }
        if "ownerConfirmation" in arguments:
            # A model-supplied Boolean is not Owner consent (#1750).
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_PARAMETER_REMOVED")
        unknown_keys = set(arguments.keys()) - allowed_keys
        if unknown_keys:
            raise _gateway().GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        if str(arguments.get("repository") or "").strip() != _gateway().GITHUB_REPOSITORY.repository_id:
            raise _gateway().GatewayInputError("STANDING_GRANT_REPOSITORY_MISMATCH")

        coordinator_id = _gateway()._text(arguments.get("coordinatorId"), "coordinatorId", max_length=128)
        goal_id = _gateway()._text(arguments.get("goalId"), "goalId", max_length=128)
        coordination_scope_id = _gateway()._text(
            arguments.get("coordinationScopeId"),
            "coordinationScopeId",
            max_length=128,
        )

        raw_actions = arguments.get("allowedActions")
        if not isinstance(raw_actions, list) or not raw_actions or len(raw_actions) > 8:
            raise _gateway().GatewayInputError("allowedActions must contain between 1 and 8 actions")
        parsed_actions: list[AutonomyActionClass] = []
        for raw_action in raw_actions:
            try:
                action = _gateway().AutonomyActionClass(str(raw_action))
            except ValueError as exc:
                raise _gateway().GatewayInputError(f"STANDING_GRANT_ACTION_INVALID:{raw_action}") from exc
            if action in parsed_actions:
                raise _gateway().GatewayInputError("STANDING_GRANT_ACTION_DUPLICATE")
            if action in _gateway()._SCOPE_ENFORCEMENT_REQUIRED_ACTIONS:
                raise _gateway().GatewayInputError(
                    f"STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:{action.value}"
                )
            parsed_actions.append(action)
        parsed_actions.sort(key=lambda action: action.value)

        raw_ttl = arguments.get("ttlMinutes")
        if isinstance(raw_ttl, bool) or not isinstance(raw_ttl, int) or not 1 <= raw_ttl <= 60:
            raise _gateway().GatewayInputError("ttlMinutes must be an integer between 1 and 60")

        issued_raw = _gateway()._text(arguments.get("issuedAt"), "issuedAt", max_length=64)
        try:
            issued_at = datetime.fromisoformat(issued_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _gateway().GatewayInputError("STANDING_GRANT_ISSUED_AT_INVALID") from exc
        if issued_at.tzinfo is None:
            raise _gateway().GatewayInputError("STANDING_GRANT_ISSUED_AT_TIMEZONE_REQUIRED")
        issued_at = issued_at.astimezone(timezone.utc)
        expires_at = issued_at + timedelta(minutes=raw_ttl)
        now = datetime.now(timezone.utc)
        if issued_at > now + timedelta(minutes=1):
            raise _gateway().GatewayInputError("STANDING_GRANT_ISSUED_AT_FUTURE")
        if now >= expires_at:
            raise _gateway().GatewayInputError("STANDING_GRANT_REQUEST_EXPIRED")

        expected_current = arguments.get("expectedCurrentReceiptHash")
        if expected_current is not None:
            expected_current = _gateway()._text(
                expected_current,
                "expectedCurrentReceiptHash",
                max_length=64,
            ).lower()
            if not _gateway()._SHA64_RE.fullmatch(expected_current):
                raise _gateway().GatewayInputError(
                    "expectedCurrentReceiptHash must be a lowercase 64-hex SHA-256"
                )

        context = _gateway().StandingGrantContext.issue(
            owner_id="James3014",
            coordinator_id=coordinator_id,
            repository=_gateway().GITHUB_REPOSITORY,
            thread_id=coordination_scope_id,
            goal_id=goal_id,
            allowed_actions=tuple(parsed_actions),
            issued_at=issued_at,
            expires_at=expires_at,
        )
        request_identity = {
            "repository": _gateway().GITHUB_REPOSITORY.repository_id,
            "coordinatorId": coordinator_id,
            "goalId": goal_id,
            "coordinationScopeId": coordination_scope_id,
            "allowedActions": [action.value for action in parsed_actions],
            "issuedAt": issued_at.isoformat(),
            "expiresAt": expires_at.isoformat(),
            "expectedCurrentReceiptHash": expected_current,
        }
        request_hash = hashlib.sha256(
            json.dumps(
                request_identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        receipt = _gateway().StandingGrantReceipt.issue(
            grant_id=f"owner-{request_hash[:24]}",
            context=context,
            supersedes_grant_hash=expected_current,
        )
        def ask_owner() -> dict[str, Any]:
            return self._confirm_with_owner(
                tool="nexus_owner_standing_grant_issue",
                draft={**request_identity, "ownerId": context.owner_id, "receiptHash": receipt.receipt_hash},
                summary_lines=(
                    f"Repository: {_gateway().GITHUB_REPOSITORY.repository_id}",
                    f"Goal: {goal_id}",
                    f"Coordination scope: {coordination_scope_id}",
                    f"Coordinator: {coordinator_id}",
                    f"Allowed actions: {', '.join(action.value for action in parsed_actions)}",
                    f"Valid: {issued_at.isoformat()} -> {expires_at.isoformat()}",
                    f"Supersedes: {expected_current or 'none'}",
                ),
                now=now,
                not_after=expires_at,
            )

        confirmation: dict[str, Any] | None = None
        key = _gateway().StandingGrantKey(
            _gateway().GITHUB_REPOSITORY,
            goal_id,
            coordination_scope_id,
        )

        try:
            current = _gateway().load_keyed_standing_grant_receipt_structural(key)
            if current is None:
                current_hash = None
            else:
                if current.context.revoked_at is not None:
                    raise _gateway().StandingGrantReceiptError("REVOKED")
                if now < current.context.issued_at:
                    raise _gateway().StandingGrantReceiptError("NOT_YET_VALID")
                current_hash = current.receipt_hash

            if current_hash == receipt.receipt_hash:
                status = "REPLAYED"
            else:
                if current_hash is None and expected_current is not None:
                    raise _gateway().StandingGrantReceiptError("EXPECTED_PREDECESSOR_MISSING")
                if current_hash is not None and expected_current is None:
                    raise _gateway().StandingGrantReceiptError("CURRENT_RECEIPT_EXISTS_CAS_REQUIRED")
                if (
                    current_hash is not None
                    and expected_current is not None
                    and current_hash != expected_current
                ):
                    raise _gateway().StandingGrantReceiptError("CAS_MISMATCH")
                # Ask only once the write is otherwise admissible; the store
                # re-checks the predecessor (CAS) when the write happens.
                confirmation = ask_owner()
                _gateway().write_keyed_standing_grant_receipt(
                    receipt,
                    expected_receipt_hash=expected_current,
                )
                rebound = _gateway().load_keyed_standing_grant_receipt(key, now=now)
                if rebound is None or rebound.receipt_hash != receipt.receipt_hash:
                    raise _gateway().StandingGrantReceiptError("ISSUANCE_READBACK_MISMATCH")
                status = "ISSUED"
                self._append_owner_confirmation_audit(
                    {
                        "schema": "nexus.owner_confirmation_outcome.v1",
                        "evidence_hash": confirmation["evidence_hash"],
                        "outcome": status,
                        "receipt_hash": receipt.receipt_hash,
                    }
                )
        except _gateway().StandingGrantReceiptError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc

        return {
            "schema": "nexus.owner_standing_grant_issuance.v1",
            "status": status,
            "repository": _gateway().GITHUB_REPOSITORY.repository_id,
            "grant_id": receipt.grant_id,
            "receipt_hash": receipt.receipt_hash,
            "key_digest": key.digest,
            "goal_id": goal_id,
            "coordination_scope_id": coordination_scope_id,
            "coordinator_id": coordinator_id,
            "allowed_actions": [action.value for action in parsed_actions],
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "supersedes_grant_hash": expected_current,
            "request_hash": request_hash,
            "idempotent_replay": status == "REPLAYED",
            "merge_performed": False,
            "claim_ceiling": "STANDING_GRANT_ISSUED_ONLY",
            "owner_confirmation": confirmation,
        }

    def _confirm_with_owner(
        self,
        *,
        tool: str,
        draft: Mapping[str, Any],
        summary_lines: tuple[str, ...],
        now: datetime,
        not_after: datetime,
    ) -> dict[str, Any]:
        """Ask the Owner through the host and record the answer before any write."""
        request = _gateway().OwnerConfirmationRequest.build(
            tool=tool,
            draft=draft,
            summary_lines=summary_lines,
            now=now,
            not_after=not_after,
        )
        try:
            evidence = self._owner_confirmation_channel.confirm(request)
        except _gateway().OwnerConfirmationError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
        if evidence.draft_hash != request.draft_hash or evidence.request_id != request.request_id:
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_BINDING_MISMATCH")
        record = {
            **evidence.to_dict(),
            "evidence_hash": evidence.evidence_hash,
            # The draft carries the receipt hash, so the record names the exact
            # grant the Owner was shown.
            "draft": dict(request.draft),
        }
        self._append_owner_confirmation_audit(record)
        return record

    @staticmethod
    def _append_owner_confirmation_audit(record: Mapping[str, Any]) -> None:
        directory = _gateway()._standing_grant_store_module.DEFAULT_RECEIPT_PATH.parent
        try:
            _gateway()._standing_grant_store_module._assert_dir_chain_safe(directory, create=True)
            fd = os.open(
                str(directory / "owner-confirmations.jsonl"),
                os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
            )
            try:
                os.write(
                    fd,
                    (json.dumps(dict(record), sort_keys=True, ensure_ascii=False) + "\n").encode(
                        "utf-8"
                    ),
                )
            finally:
                os.close(fd)
        except (OSError, _gateway()._standing_grant_store_module.StandingGrantReceiptError) as exc:
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_AUDIT_WRITE_FAILED") from exc

    def _task_card_authority_switch(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "attemptKey",
            "expectedCurrentReceiptHash",
            "expectedCurrentGoalId",
            "expectedCurrentThreadId",
            "successorGoalId",
            "successorThreadId",
            "ttlMinutes",
        }
        if "ownerConfirmation" in arguments:
            # A switch writes a new grant at a new key, so it needs the same
            # host-mediated Owner confirmation as issuance (#1750).
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_PARAMETER_REMOVED")
        unknown_keys = set(arguments.keys()) - allowed_keys
        if unknown_keys:
            raise _gateway().GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        attempt_key = _gateway()._text(arguments.get("attemptKey"), "attemptKey", max_length=128)
        expected_current_receipt_hash = _gateway()._text(
            arguments.get("expectedCurrentReceiptHash"),
            "expectedCurrentReceiptHash",
            max_length=64,
        ).lower()
        if not _gateway()._SHA64_RE.fullmatch(expected_current_receipt_hash):
            raise _gateway().GatewayInputError("expectedCurrentReceiptHash must be a lowercase 64-hex SHA-256")
        expected_current_goal_id = _gateway()._text(
            arguments.get("expectedCurrentGoalId"),
            "expectedCurrentGoalId",
            max_length=128,
        )
        expected_current_thread_id = _gateway()._text(
            arguments.get("expectedCurrentThreadId"),
            "expectedCurrentThreadId",
            max_length=128,
        )
        successor_goal_id = _gateway()._text(
            arguments.get("successorGoalId"),
            "successorGoalId",
            max_length=128,
        )
        successor_thread_id = _gateway()._text(
            arguments.get("successorThreadId"),
            "successorThreadId",
            max_length=128,
        )
        raw_ttl = arguments.get("ttlMinutes")
        if raw_ttl is None:
            raise _gateway().GatewayInputError("ttlMinutes is required")
        if isinstance(raw_ttl, bool) or not isinstance(raw_ttl, int) or raw_ttl < 1 or raw_ttl > 30:
            raise _gateway().GatewayInputError("ttlMinutes must be an integer between 1 and 30")
        ttl_minutes = raw_ttl
        now = datetime.now(timezone.utc)
        self._confirm_with_owner(
            tool="nexus_task_card_authority_switch",
            draft={
                "repository": _gateway().GITHUB_REPOSITORY.repository_id,
                "attemptKey": attempt_key,
                "expectedCurrentReceiptHash": expected_current_receipt_hash,
                "expectedCurrentGoalId": expected_current_goal_id,
                "expectedCurrentThreadId": expected_current_thread_id,
                "successorGoalId": successor_goal_id,
                "successorThreadId": successor_thread_id,
                "allowedActions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
                "ttlMinutes": ttl_minutes,
            },
            summary_lines=(
                f"Repository: {_gateway().GITHUB_REPOSITORY.repository_id}",
                f"From grant: {expected_current_receipt_hash} (goal {expected_current_goal_id})",
                f"New task-card scope: goal {successor_goal_id}, thread {successor_thread_id}",
                "Allowed actions: TASK_CARD_COMMIT, TASK_CARD_CREATE",
                f"Valid for: {ttl_minutes} minutes (never beyond the current grant)",
            ),
            now=now,
            not_after=now + timedelta(minutes=ttl_minutes),
        )

        try:
            return _gateway().switch_task_card_authority(
                current_key=self._standing_key(
                    expected_current_goal_id, expected_current_thread_id
                ),
                attempt_key=attempt_key,
                expected_current_receipt_hash=expected_current_receipt_hash,
                expected_current_goal_id=expected_current_goal_id,
                successor_goal_id=successor_goal_id,
                successor_thread_id=successor_thread_id,
                ttl_minutes=ttl_minutes,
                owner_confirmation=True,
            )
        except _gateway().StandingGrantReceiptError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc

    def _task_card_authority_restore(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "ownerConfirmation",
            "attemptKey",
            "switchOperationId",
            "expectedTemporaryReceiptHash",
            "expectedCurrentGoalId",
            "expectedCurrentThreadId",
        }
        unknown_keys = set(arguments.keys()) - allowed_keys
        if unknown_keys:
            raise _gateway().GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        owner_confirmation = arguments.get("ownerConfirmation")
        if owner_confirmation is not True:
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        attempt_key = _gateway()._text(arguments.get("attemptKey"), "attemptKey", max_length=128)
        switch_operation_id = _gateway()._text(
            arguments.get("switchOperationId"),
            "switchOperationId",
            max_length=128,
        )
        expected_temporary_receipt_hash = _gateway()._text(
            arguments.get("expectedTemporaryReceiptHash"),
            "expectedTemporaryReceiptHash",
            max_length=64,
        ).lower()
        expected_current_goal_id = _gateway()._text(
            arguments.get("expectedCurrentGoalId"), "expectedCurrentGoalId", max_length=128
        )
        expected_current_thread_id = _gateway()._text(
            arguments.get("expectedCurrentThreadId"), "expectedCurrentThreadId", max_length=128
        )
        if not _gateway()._SHA64_RE.fullmatch(expected_temporary_receipt_hash):
            raise _gateway().GatewayInputError(
                "expectedTemporaryReceiptHash must be a lowercase 64-hex SHA-256"
            )

        try:
            return _gateway().restore_task_card_authority(
                current_key=self._standing_key(
                    expected_current_goal_id, expected_current_thread_id
                ),
                attempt_key=attempt_key,
                switch_operation_id=switch_operation_id,
                expected_temporary_receipt_hash=expected_temporary_receipt_hash,
                owner_confirmation=True,
            )
        except _gateway().StandingGrantReceiptError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
    # fmt: on
