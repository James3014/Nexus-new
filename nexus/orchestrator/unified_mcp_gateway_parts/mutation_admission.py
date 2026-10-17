"""Mutation admission and project entry of ``UnifiedMCPGateway``.

Big-file split G8 (Issue #2507). ``_MutationAdmissionMixin`` holds
``_mutation_task_card_authority``, ``_mutation_admit``, ``_mutation_admission_status``,
``_project_entry``, ``_project_entry_binding_hash`` and ``_project_entry_blocker``, moved
out of ``nexus/orchestrator/unified_mcp_gateway.py``. Their source lines are verbatim,
except that every gateway-module name they load (``_git``, ``CANONICAL_SOURCE_ROOT`` and
``SERVER_INSTANCE_ID``, which tests patch on the gateway module, and the gateway-defined
``_loaded_git``, ``GatewayInputError``, ``_text``, ``_safe_relative_path``,
``_require_bound_controller``, ``TOOL_MANIFEST_REVISION``, ``FULL_TOOL_SCHEMA_HASH``,
``PERMISSION_POLICY_HASH``, ``GITHUB_REPOSITORY``, ``_SHA_RE``, ``_canonical_remote_matches``
and ``UnifiedMCPGateway``) is resolved at call time through ``_gateway()``. The owner
authority check (``_require_owner_effect_authority``) and the readiness gate
(``_gateway_execution_readiness``) stay in the gateway class and are reached through ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from typing import TYPE_CHECKING, Any, Mapping

from nexus.contracts.autonomy_goal import AutonomyActionClass
from nexus.orchestrator.mutation_admission import MutationAdmissionError

if TYPE_CHECKING:
    from nexus.orchestrator.mutation_admission import MutationAdmissionStore
    from nexus.orchestrator.standing_grant_store import StandingGrantKey

    # Typing only: the worker-candidate (and, through it, model-probe / assist) helpers.
    from nexus.orchestrator.unified_mcp_gateway_parts.worker_candidate import (
        _WorkerCandidateMixin as _MutationAdmissionBase,
    )
else:
    _MutationAdmissionBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


class _MutationAdmissionMixin(_MutationAdmissionBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway
        _github_issue_observer: Any
        _mutation_repository_observer: Any
        _mutation_admissions: MutationAdmissionStore

        @staticmethod
        def _owner_effect_key(arguments: Mapping[str, Any]) -> StandingGrantKey: ...

        @staticmethod
        def _require_owner_effect_authority(
            action: AutonomyActionClass,
            effect: Mapping[str, Any],
            *,
            key: StandingGrantKey,
        ) -> dict[str, Any]: ...

        def _gateway_execution_readiness(self, arguments: Mapping[str, Any]) -> dict[str, Any]: ...

    # fmt: off
    @staticmethod
    def _mutation_task_card_authority(
        *,
        issue_number: int,
        task_id: str,
        attempt_id: str,
        task_card_path: str,
        task_card_hash: str,
    ) -> dict[str, str]:
        _gateway()._safe_relative_path(task_card_path, "task_card_path")
        if not task_card_path.startswith("tasks/") or not task_card_path.endswith(".md"):
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_PATH_INVALID")
        root = _gateway().CANONICAL_SOURCE_ROOT.resolve()
        card = (root / task_card_path).resolve()
        try:
            relative = card.relative_to(root).as_posix()
        except ValueError as exc:
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_PATH_INVALID") from exc
        if relative != task_card_path or not card.is_file():
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_NOT_FOUND")
        try:
            raw = card.read_bytes()
            source = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_UNREADABLE") from exc
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != task_card_hash:
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_HASH_MISMATCH")

        def field(name: str) -> str:
            match = re.search(
                rf"(?m)^{re.escape(name)}:\s*`?([^`\n]+)`?\s*$",
                source,
            )
            return match.group(1).strip() if match else ""

        if field("artifact_authority") != "current" or field("status") != "ACTIVE":
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_NOT_ACTIVE")
        if field("task_id") != task_id or field("attempt_id") != attempt_id:
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_IDENTITY_MISMATCH")
        issue_marker = f"James3014/Nexus-new#{issue_number}"
        if issue_marker not in source:
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_TASK_CARD_ISSUE_MISMATCH")
        governance_source_head = _gateway()._git("rev-parse", "HEAD").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", governance_source_head):
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_GOVERNANCE_SOURCE_INVALID")
        return {
            "task_id": task_id,
            "attempt_id": attempt_id,
            "task_card_path": task_card_path,
            "task_card_hash": actual_hash,
            "governance_source_head": governance_source_head,
        }

    def _mutation_admit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _gateway()._require_bound_controller()
        if "owner_confirmation" in arguments:
            raise _gateway().GatewayInputError("MUTATION_ADMISSION_CALLER_AUTHORITY_FORBIDDEN")
        repository = _gateway()._text(arguments.get("repository"), "repository", max_length=256)
        operation_id = _gateway()._text(arguments.get("operation_id"), "operation_id", max_length=128)
        base_sha = _gateway()._text(arguments.get("base_sha"), "base_sha", max_length=40)
        lane = _gateway()._text(arguments.get("execution_lane"), "execution_lane", max_length=32).upper()
        authority_kind = _gateway()._text(arguments.get("authority_kind"), "authority_kind", max_length=32).upper()
        allowed_paths = list(
            dict.fromkeys(
                str(path).strip()
                for path in (arguments.get("allowed_paths") or [])
                if str(path).strip()
            )
        )
        issue_number = arguments.get("issue_number")
        task_id = str(arguments.get("task_id") or "").strip()
        attempt_id = str(arguments.get("attempt_id") or "").strip()
        task_card_path = str(arguments.get("task_card_path") or "").strip()
        task_card_hash = str(arguments.get("task_card_hash") or "").strip()
        ttl_minutes = arguments.get("ttl_minutes", 10080)

        observation = self._mutation_repository_observer(repository)
        if not isinstance(observation, Mapping) or observation.get("ok") is not True:
            blocker = (
                observation.get("blocker")
                if isinstance(observation, Mapping)
                else "GITHUB_OBSERVER_REQUEST_FAILED"
            )
            detail = (
                observation.get("detail")
                if isinstance(observation, Mapping)
                else "repository observation unavailable"
            )
            raise _gateway().GatewayInputError(f"MUTATION_ADMISSION_SOURCE_OBSERVER_FAILED:{blocker}:{detail}")
        observed_head = str(observation.get("head_sha") or "")
        if observed_head != base_sha:
            raise _gateway().GatewayInputError(
                f"MUTATION_ADMISSION_BASE_STALE:expected={observed_head}:requested={base_sha}"
            )

        authority_reference: Mapping[str, Any] | None = None
        governance_binding: dict[str, str] = {}
        if lane == "GOVERNED":
            if authority_kind != "TRACKED_TASK_CARD":
                raise _gateway().GatewayInputError("GOVERNED_TASK_CARD_REQUIRED")
            if (
                not isinstance(issue_number, int)
                or isinstance(issue_number, bool)
                or issue_number < 1
                or not task_id
                or not attempt_id
                or not task_card_path
                or not re.fullmatch(r"[0-9a-f]{64}", task_card_hash)
            ):
                raise _gateway().GatewayInputError("GOVERNED_TASK_CARD_REQUIRED")
            governance_binding = self._mutation_task_card_authority(
                issue_number=issue_number,
                task_id=task_id,
                attempt_id=attempt_id,
                task_card_path=task_card_path,
                task_card_hash=task_card_hash,
            )
        else:
            if authority_kind != "OWNER_INLINE":
                raise _gateway().GatewayInputError("DIRECT_OWNER_AUTHORITY_REQUIRED")
            if any((task_id, attempt_id, task_card_path, task_card_hash)):
                raise _gateway().GatewayInputError("DIRECT_TASK_CARD_INVALID")
            key = self._owner_effect_key(arguments)
            effect = {
                "operation_id": operation_id,
                "target_repository": repository,
                "base_sha": base_sha,
                "execution_lane": lane,
                "allowed_paths": allowed_paths,
                "issue_number": issue_number,
            }
            authority_reference = self._require_owner_effect_authority(
                AutonomyActionClass.TASK_SUBMIT,
                effect,
                key=key,
            )

        runtime_identity = {
            "server_instance_id": _gateway().SERVER_INSTANCE_ID,
            "tool_manifest_revision": _gateway().TOOL_MANIFEST_REVISION,
            "full_tool_schema_hash": _gateway().FULL_TOOL_SCHEMA_HASH,
            "permission_policy_hash": _gateway().PERMISSION_POLICY_HASH,
            "gateway_source_head": _gateway()._loaded_git("rev-parse", "HEAD").strip(),
            "repository_observed_at": observation.get("observed_at"),
            "default_branch": observation.get("default_branch"),
        }
        try:
            return self._mutation_admissions.admit(
                operation_id=operation_id,
                repository=repository,
                base_sha=base_sha,
                execution_lane=lane,
                authority_kind=authority_kind,
                allowed_paths=allowed_paths,
                authority_reference=authority_reference,
                issue_number=issue_number,
                task_id=governance_binding.get("task_id"),
                attempt_id=governance_binding.get("attempt_id"),
                task_card_path=governance_binding.get("task_card_path"),
                task_card_hash=governance_binding.get("task_card_hash"),
                governance_source_head=governance_binding.get("governance_source_head"),
                ttl_minutes=ttl_minutes,
                runtime_identity=runtime_identity,
            )
        except MutationAdmissionError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc

    def _mutation_admission_status(
        self, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        admission_id = _gateway()._text(
            arguments.get("admission_id"), "admission_id", max_length=64
        )
        receipt_hash = _gateway()._text(
            arguments.get("receipt_hash"), "receipt_hash", max_length=64
        )
        try:
            return self._mutation_admissions.status(
                admission_id,
                expected_receipt_hash=receipt_hash,
            )
        except MutationAdmissionError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc

    def _project_entry(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        owner = _gateway()._text(arguments.get("repository_owner"), "repository_owner", max_length=128)
        name = _gateway()._text(arguments.get("repository_name"), "repository_name", max_length=128)
        raw_issue = arguments.get("issue_number")
        if isinstance(raw_issue, bool) or not isinstance(raw_issue, int) or raw_issue <= 0:
            raise _gateway().GatewayInputError("issue_number must be a positive integer")
        repository = f"{owner}/{name}"
        if repository != _gateway().GITHUB_REPOSITORY.repository_id:
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_REPOSITORY_MISMATCH", "repository is outside canonical scope")
        try:
            origin = _gateway()._git("config", "--get", "remote.origin.url").strip()
            head = _gateway()._git("rev-parse", "HEAD").strip()
            tree = _gateway()._git("rev-parse", "HEAD^{tree}").strip()
        except RuntimeError as exc:
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_SOURCE_OBSERVER_FAILED", str(exc))
        if not _gateway()._SHA_RE.fullmatch(head) or not _gateway()._SHA_RE.fullmatch(tree):
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_SOURCE_OBSERVER_FAILED", "invalid source identity")
        if not _gateway()._canonical_remote_matches(origin, repository):
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_REPOSITORY_MISMATCH", "origin identity mismatch")
        canonical_remote = _gateway().GITHUB_REPOSITORY.canonical_remote
        observation = self._github_issue_observer(repository, raw_issue)
        if not isinstance(observation, Mapping) or observation.get("ok") is not True:
            cause_code = (
                str(observation.get("blocker"))
                if isinstance(observation, Mapping) and observation.get("blocker")
                else "GITHUB_OBSERVER_REQUEST_FAILED"
            )
            return self._project_entry_blocker(
                repository,
                raw_issue,
                "PROJECT_ENTRY_GITHUB_OBSERVER_FAILED",
                "fresh Issue observation unavailable",
                cause_code=cause_code,
            )
        issue = observation.get("issue")
        if not isinstance(issue, Mapping) or str(issue.get("number")) != str(raw_issue) or not issue.get("state"):
            return self._project_entry_blocker(
                repository,
                raw_issue,
                "PROJECT_ENTRY_GITHUB_OBSERVER_FAILED",
                "fresh Issue identity/state unavailable",
                cause_code="GITHUB_OBSERVER_MALFORMED_RESPONSE",
            )
        if str(issue.get("state")).upper() != "OPEN":
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_ISSUE_NOT_OPEN", "Issue is not open")
        try:
            matches = self.service.find_tasks_by_repository_issue(repository, raw_issue)
        except Exception as exc:
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_TASK_RESOLUTION_FAILED", str(exc))
        if len(matches) > 1:
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_AMBIGUOUS_TASK_BINDING", "multiple exact task bindings")
        readiness_args = {
            "repository_owner": owner, "repository_name": name,
            "intended_source_commit": head, "intended_source_tree": tree,
            "execution_realm": "in_process_preflight",
            "required_action_family": "project_entry_observe",
            "execution_contract_kind": "observe_only",
        }
        if not matches:
            readiness = self._gateway_execution_readiness(readiness_args)
            result = {"schema": "nexus.project_entry.v1", "status": "NO_TASK", "repository": repository,
                    "issue": dict(issue), "source": {"commit": head, "tree": tree, "canonical_remote": canonical_remote},
                    "issue_observation": dict(observation), "task_resolution": {"status": "NO_EXACT_TASK"},
                    "readiness_request": readiness_args, "readiness_result": readiness,
                    "readiness_scope": "PROJECT_ENTRY_OBSERVATION_ONLY",
                    "claim_ceiling": "PROJECT_ENTRY_OBSERVE_ONLY_NO_DOWNSTREAM_EFFECTS",
                    "claim_ceiling_excludes": ["execution", "verification", "acceptance", "merge", "release", "production"]}
            result["project_binding_hash"] = self._project_entry_binding_hash(result)
            return result
        state = matches[0]
        task_id = str(state.get("task_id") or "")
        try:
            entry = self.service.rehydrate_project_entry(
                task_id, state.get("attempt_id"), repository=repository, issue_number=raw_issue
            )
            projection = entry["continuation"]
        except Exception as exc:
            return self._project_entry_blocker(repository, raw_issue, "PROJECT_ENTRY_CONTINUATION_INVALID", str(exc), task_id=task_id)
        authority_binding = entry.get("authority_binding") if isinstance(entry, Mapping) else None
        if authority_binding is not None:
            readiness_args.update({
                "task_campaign_goal_identity": authority_binding["goal_id"],
                "durable_coordination_scope_id": authority_binding["coordination_scope_id"],
                "durable_repository_canonical_remote": authority_binding["canonical_remote"],
                "required_action_family": authority_binding["intended_action_family"],
            })
        readiness = self._gateway_execution_readiness(readiness_args)
        result = {"schema": "nexus.project_entry.v1", "status": "TASK_REHYDRATED", "repository": repository,
                "issue": dict(issue), "source": {"commit": head, "tree": tree, "canonical_remote": canonical_remote},
                "issue_observation": dict(observation), "task_resolution": {"status": "EXACT_TASK", "task_id": task_id},
                "continuation": projection, "readiness_request": readiness_args, "readiness_result": readiness,
                "readiness_scope": "PROJECT_ENTRY_OBSERVATION_ONLY",
                "claim_ceiling": "PROJECT_ENTRY_OBSERVE_ONLY_NO_DOWNSTREAM_EFFECTS",
                "claim_ceiling_excludes": ["execution", "verification", "acceptance", "merge", "release", "production"]}
        result["project_binding_hash"] = self._project_entry_binding_hash(result)
        return result

    @staticmethod
    def _project_entry_binding_hash(payload: Mapping[str, Any]) -> str:
        volatile = {"evaluated_at", "observed_at", "timestamp", "created_at", "updated_at_runtime"}
        def scrub(value: Any) -> Any:
            if isinstance(value, Mapping):
                return {str(k): scrub(v) for k, v in value.items() if k not in volatile and k != "project_binding_hash"}
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value
        stable = scrub(json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)))
        return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _project_entry_blocker(
        repository: str,
        issue: int,
        code: str,
        detail: str,
        *,
        task_id: str | None = None,
        cause_code: str | None = None,
    ) -> dict[str, Any]:
        safe_detail = f"diagnostic_class={code}; diagnostic_sha256={hashlib.sha256(str(detail).encode()).hexdigest()}"
        blocker = {"code": code, "detail": safe_detail}
        if cause_code:
            blocker["cause_code"] = cause_code
        result = {"schema": "nexus.project_entry.v1", "status": "BLOCKED", "repository": repository,
                  "issue_number": issue, "task_resolution": {"status": "NOT_RESOLVED"},
                  "blocker": blocker,
                  "claim_ceiling": "PROJECT_ENTRY_OBSERVE_ONLY_NO_DOWNSTREAM_EFFECTS",
                  "claim_ceiling_excludes": ["execution", "verification", "acceptance", "merge", "release", "production"]}
        if task_id:
            result["task_resolution"] = {"status": "INVALID_CONTINUATION", "task_id": task_id}
        result["project_binding_hash"] = _gateway().UnifiedMCPGateway._project_entry_binding_hash(result)
        return result
    # fmt: on
