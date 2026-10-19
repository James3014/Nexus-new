"""Durable, restartable service facade for the self-hosted MCP surface."""

from __future__ import annotations

import base64
import hashlib
import inspect  # noqa: F401 - facade surface, late-bound by parts/worker_dispatch.py
import json
import logging  # noqa: F401 - facade surface (its only user moved to parts/checkpoint.py)
import os
import re
import shlex
import shutil  # noqa: F401 - facade surface, late-bound by parts/finalize_runtime.py
import signal  # noqa: F401 - facade surface, late-bound by parts/finalize_runtime.py
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import (
    contextmanager,  # noqa: F401 - facade surface (its users moved to parts/state_store.py)
)
from dataclasses import (
    asdict,
    is_dataclass,
    replace,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py, parts/finalize_runtime.py
)
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import (
    SimpleNamespace,  # noqa: F401 - facade surface (its only user moved to parts/finalize_runtime.py)
)
from typing import (
    Any,
    Callable,
    Iterable,  # noqa: F401 - facade surface, used by parts/events.py
    Iterator,  # noqa: F401 - facade surface (its users moved to parts/state_store.py)
    Mapping,
    Optional,
    Sequence,  # noqa: F401 - facade surface (its only users moved to parts/worker_dispatch.py)
    cast,  # noqa: F401 - facade surface (its only user moved to parts/finalize_runtime.py)
)
from uuid import uuid4

from nexus_runtime.execution_state import (
    ExecutionStateStore,  # noqa: F401 - facade surface, used by parts/state_store.py
)
from nexus_runtime.task_lifecycle import (
    ACTIVE_EXECUTION_STATUSES,  # noqa: F401 - facade surface, used by parts/action_envelope.py
    DURABLE_SELF_HOSTED_STATUSES,  # noqa: F401 - facade surface, used by parts/action_envelope.py and parts/state_store.py
    INVALID_STATE_STATUSES,  # noqa: F401 - facade surface, used by parts/action_envelope.py
    PENDING_CANDIDATE_STATUSES,
    RESUMABLE_STATUSES,
    RETRYABLE_TASK_STATUSES,
    TERMINAL_STATUSES,
)
from nexus_runtime.task_lifecycle import (
    DIRECT_EXECUTION_STATUSES as DIRECT_EXECUTION_STATUSES,
)
from nexus_runtime.task_lifecycle import (
    INTEGRATION_INTERMEDIATE_STATUSES as INTEGRATION_INTERMEDIATE_STATUSES,
)
from nexus_runtime.task_lifecycle import (
    KNOWN_SELF_HOSTED_STATUSES as KNOWN_SELF_HOSTED_STATUSES,
)
from nexus_runtime.task_retry import (
    DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK as DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK,
)
from nexus_runtime.task_retry import (
    mint_retry_identity,  # noqa: F401 - facade surface, used by parts/retry_helpers.py
)

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,  # noqa: F401 - facade surface, used by parts/dispatch_binding.py
    AutonomyGoalGrant,
)
from nexus.contracts.collaboration_realm import (
    CollaborationExecutionRealm,  # noqa: F401 - facade surface, used by parts/task_build.py
)
from nexus.contracts.lifecycle_action import (
    ContractKind,
    ExternalCandidateAdoptionRequest,
    LifecycleActionEnvelope,  # noqa: F401 - facade surface, used by parts/retry_helpers.py
    LifecycleActionType,
    canonical_request_hash,
    parse_historical_epb_task_card,
    validate_owner_inline_contract,
)
from nexus.contracts.operator_outcome_receipt import (
    OperatorOutcomeReceipt,  # noqa: F401 - facade surface (its users moved to parts/operator_outcome.py)
    validate_operator_outcome_receipt,  # noqa: F401 - facade surface, used by parts/operator_outcome.py
)
from nexus.contracts.self_hosted_state_root import LEGACY_PRESENT_CODE, raise_if_legacy_state
from nexus.contracts.target_integration_lifecycle import (
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.contracts.unified_runtime_receipt import (
    build_runtime_development_mapping,  # noqa: F401 - facade surface, used by parts/checkpoint.py
)
from nexus.contracts.workforce_admission import WorkforceDemand
from nexus.core.task_continuity import (
    build_rehydration_projection,  # noqa: F401 - facade surface, used by parts/events.py
    events_from_attempt_records,  # noqa: F401 - facade surface, used by parts/events.py
    project,  # noqa: F401 - facade surface, used by parts/events.py
)
from nexus.engine.canonical_task_seam import (
    CanonicalDispatchEnvelope,
    build_canonical_dispatch_envelope,  # noqa: F401 - facade surface, used by parts/dispatch_binding.py
)
from nexus.events.contracts import (
    build_attempt_transition_event,  # noqa: F401 - facade surface, used by parts/events.py
)
from nexus.events.transport import (
    NexusEventBus,  # noqa: F401 - facade surface, used by parts/events.py
)
from nexus.executors.cli_worker import (
    CliWorkerStatus,  # noqa: F401 - facade surface, late-bound by parts/finalize_runtime.py
)
from nexus.executors.worker_contract import (
    SUPPORTED_WORKER_PROVIDERS,  # noqa: F401 - facade surface, used by parts/task_build.py
    AttemptResolutionVerdict,  # noqa: F401 - facade surface, late-bound by parts/finalize_runtime.py
    WorkerExecutionReceipt,  # noqa: F401 - facade surface, late-bound by parts/task_build.py
    admitted_worker_providers,  # noqa: F401 - facade surface, used by parts/task_build.py
    resolve_attempt,  # noqa: F401 - facade surface, late-bound by parts/finalize_runtime.py
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.acceptance_loop import (
    CandidateAcceptanceRequest,  # noqa: F401 - facade surface, used by parts/read_projection.py
    CandidateAcceptanceResult,  # noqa: F401 - facade surface, used by parts/read_projection.py
    IndependentReviewReceipt,  # noqa: F401 - facade surface, used by parts/read_projection.py
    reduce_candidate_acceptance,  # noqa: F401 - facade surface, used by parts/read_projection.py
)
from nexus.orchestrator.ambient_core import (
    AmbientCoreControlPort,
    AmbientCoreVerdictBlocked,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py, parts/finalize_runtime.py
    ambient_core_required,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py
    build_core_verdict,  # noqa: F401 - facade surface, late-bound by parts/checkpoint.py, parts/ambient_track1.py
    normalize_preparation,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py
    normalize_verification_projection,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py
    projection_hash,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py
)
from nexus.orchestrator.autonomy_policy import (
    AutonomySubmissionBinding,
    project_autonomy_submission,
)
from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import CandidateVerifier, VerifiedCandidateReceipt
from nexus.orchestrator.canonical_source_root import CANONICAL_SOURCE_ROOT
from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,
    IntegrationExecutionError,
)
from nexus.orchestrator.lifecycle_guards import (
    pre_action_guard,
    require_bound_approval_grant,
    trusted_runtime_manifest_hash,
    validate_approval_grant,
    validate_architecture_approval,
)
from nexus.orchestrator.repository_contract_gate import RepositoryContractGate
from nexus.orchestrator.runtime_retry_bridge import (
    project_candidate_acceptance_for_runtime_repair,  # noqa: F401 - facade surface, used by parts/read_projection.py
    retry_task_via_runtime,
)
from nexus.orchestrator.runtime_state_bridge import RuntimeStateBridge
from nexus.orchestrator.self_hosted_controller import (
    SelfHostedDevelopmentController,  # noqa: F401 - facade surface, late-bound by parts/finalize_runtime.py, runtime_coordination_bridge.py
)
from nexus.orchestrator.self_hosted_task_service_parts.action_envelope import (
    _ActionEnvelopeMixin as _ActionEnvelopeMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.ambient_track1 import (
    _AmbientTrack1Mixin as _AmbientTrack1Mixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.checkpoint import (
    _CheckpointMixin as _CheckpointMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.claims import _ClaimsMixin as _ClaimsMixin
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _recover_pre_provider_cli_envelope_drift as _recover_pre_provider_cli_envelope_drift,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _reject_unbound_project_entry_authority_hints as _reject_unbound_project_entry_authority_hints,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _tracked_dispatch_required as _tracked_dispatch_required,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _validate_project_entry_authority_binding as _validate_project_entry_authority_binding,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _validated_action_request as _validated_action_request,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _workforce_admission_readback_matches as _workforce_admission_readback_matches,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    _workforce_dispatch_inputs as _workforce_dispatch_inputs,
)
from nexus.orchestrator.self_hosted_task_service_parts.dispatch_binding import (
    validate_workforce_dispatch_binding as validate_workforce_dispatch_binding,
)
from nexus.orchestrator.self_hosted_task_service_parts.events import _EventsMixin as _EventsMixin
from nexus.orchestrator.self_hosted_task_service_parts.finalize_runtime import (
    _FinalizeRuntimeMixin as _FinalizeRuntimeMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.inventory import (
    _InventoryMixin as _InventoryMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.operator_outcome import (
    _OperatorOutcomeMixin as _OperatorOutcomeMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.read_projection import (
    _ReadProjectionMixin as _ReadProjectionMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.reconcile_recovery import (
    _ReconcileRecoveryMixin as _ReconcileRecoveryMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _retry_request as _retry_request,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _retry_semantic_payload as _retry_semantic_payload,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _terminal_retry_inherited_worktree_time_allowed as _terminal_retry_inherited_worktree_time_allowed,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _terminal_retry_pre_provider_state_allowed as _terminal_retry_pre_provider_state_allowed,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _terminal_retry_released_lease_proof as _terminal_retry_released_lease_proof,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _terminal_retry_semantic_payload as _terminal_retry_semantic_payload,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _terminal_retry_verifier_static_failure_allowed as _terminal_retry_verifier_static_failure_allowed,
)
from nexus.orchestrator.self_hosted_task_service_parts.retry_helpers import (
    _validate_retry_predecessor as _validate_retry_predecessor,
)
from nexus.orchestrator.self_hosted_task_service_parts.state_store import (
    _StateStoreMixin as _StateStoreMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.task_build import (
    _TaskBuildMixin as _TaskBuildMixin,
)
from nexus.orchestrator.self_hosted_task_service_parts.worker_dispatch import (
    _WorkerDispatchMixin as _WorkerDispatchMixin,
)
from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,  # noqa: F401 - facade surface, used by parts/task_build.py
    ArchitectTaskContract,
    ArchitectureDecision,  # noqa: F401 - facade surface, used by parts/task_build.py
    DevelopmentGoal,  # noqa: F401 - facade surface, used by parts/task_build.py
    HumanApprovalPolicy,  # noqa: F401 - facade surface, used by parts/task_build.py
    MutationMode,  # noqa: F401 - facade surface, used by parts/task_build.py
    parse_task_card_expected_evidence,  # noqa: F401 - facade surface, late-bound by parts/ambient_track1.py
)
from nexus.orchestrator.worker_escalation import (
    WorkerEscalationPolicy,  # noqa: F401 - facade surface, late-bound by parts/task_build.py
)
from nexus.orchestrator.worktree_manager import (
    TargetWorktreeLease,
    WorktreeManager,
    _source_identity,
    mutation_domains_conflict,
)
from nexus.services.model_workforce_policy import (
    WorkforcePolicyLoader,  # noqa: F401 - facade surface, used by parts/dispatch_binding.py
)
from nexus.services.runtime_workforce_admission import (
    _binding_payload,
    _sha256_json,
    evaluate_runtime_workforce_admission,  # noqa: F401 - facade surface, used by parts/dispatch_binding.py
)

Runner = Callable[
    [ArchitectTaskContract, Mapping[str, Any], Callable[[str, dict[str, Any]], None]],
    dict[str, Any],
]
_LEGACY_V1_NEGATIVE_OMISSION_SET = frozenset(
    {
        "candidate_status",
        "promotion_packet",
        "integration_authorization",
        "integration_receipt",
        "promotion_receipt",
        "candidate_created",
        "candidate_commit_created",
        "authority_change_required",
    }
)
_PROJECT_ENTRY_AUTHORITY_HINTS = frozenset(
    {
        "authority_goal_id",
        "authority_coordination_scope_id",
        "standing_grant_id",
        "autonomy_goal_id",
        "autonomy_submission_binding",
        "autonomy_goal_grant",
        "governed",
        "governed_task",
        "intended_action_family",
        "required_action_family",
    }
)
_EXTERNAL_ADOPTION_CLAIM_CEILING = ("CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY",)


def _temporary_state_roots() -> tuple[Path, ...]:
    """Return trusted ephemeral roots, including process-provided CI roots.

    GitHub-hosted runners expose their isolated scratch directory through
    ``RUNNER_TEMP`` (and some runners use ``TMPDIR``).  These roots are
    temporary execution surfaces only; they do not alter the canonical state
    root or grant production/promotion authority.
    """
    roots = [Path("/tmp"), Path("/private/tmp"), Path("/private/var/folders")]
    for variable in ("TMPDIR", "RUNNER_TEMP"):
        configured = os.getenv(variable, "").strip()
        if not configured:
            continue
        candidate = Path(configured).expanduser()
        if (
            not candidate.is_absolute()
            or candidate == Path("/")
            or any(part.is_symlink() for part in _path_components(candidate))
        ):
            continue
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if resolved != Path("/"):
            roots.append(resolved)
    return tuple(dict.fromkeys(roots))


def _path_components(path: Path) -> tuple[Path, ...]:
    """Return lexical path components so configured symlink parents are rejected."""
    current = Path(path.anchor or ".")
    components = [current]
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current /= part
        components.append(current)
    return tuple(components)


def resolve_contract_identity(
    state: Mapping[str, Any],
    *,
    expected_task_id: str,
    expected_head: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve the approval identity while preserving the service contract hash."""
    contract_kind = str(state.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value)
    task_card_hash = str(state.get("task_card_hash") or "").strip() or None
    contract_hash = str(state.get("contract_hash") or "").strip() or task_card_hash
    owner_inline_contract = (
        state.get("owner_inline_contract")
        if isinstance(state.get("owner_inline_contract"), Mapping)
        else None
    )
    if contract_kind == ContractKind.OWNER_INLINE.value:
        try:
            owner_inline_contract = validate_owner_inline_contract(
                owner_inline_contract or {},
                expected_task_id=expected_task_id,
                expected_head=expected_head,
            )
        except ValueError as exc:
            raise RuntimeError(
                "CONTRACT_HASH_MISMATCH: persisted Owner Inline contract is invalid"
            ) from exc
        contract_hash = owner_inline_contract["contract_hash"]
        task_card_hash = None
    elif contract_kind != ContractKind.TRACKED_TASK_CARD.value:
        raise RuntimeError("APPROVAL_CONTRACT_KIND_UNSUPPORTED")
    return {
        "contract_kind": contract_kind,
        "contract_hash": contract_hash,
        "task_card_hash": task_card_hash,
        "owner_inline_contract": owner_inline_contract,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return value


def _validate_existing_autonomy_binding(
    state: Mapping[str, Any],
    grant: Optional[AutonomyGoalGrant],
) -> None:
    """Reject any attempt to add or replace autonomy after task creation."""
    raw_binding = state.get("autonomy_submission_binding")
    if grant is None:
        if raw_binding is not None:
            raise ValueError("AUTONOMY_GOAL_GRANT_REQUIRED")
        return
    if raw_binding is None:
        raise ValueError("POST_SUBMISSION_GRANT_INJECTION")
    try:
        binding = AutonomySubmissionBinding.model_validate(raw_binding)
    except Exception as exc:
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_INVALID") from exc
    if binding.task_id != state.get("task_id"):
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_DRIFT")
    if binding.goal_id != grant.goal_id or binding.grant_hash != grant.grant_hash:
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_DRIFT")
    if not project_autonomy_submission(state).get("eligible"):
        raise ValueError("AUTONOMY_SUBMISSION_BINDING_DRIFT")


FAIL_TO_PASS_EVIDENCE_TOKEN = "fail_to_pass_base_verifier"
FAIL_TO_PASS_PROBE_SCHEMA = "nexus.fail_to_pass_probe.v1"
_FAIL_TO_PASS_BLOCKED_STATUSES = frozenset({"BASE_ALREADY_PASS", "BASE_NOT_PHYSICAL_FAIL"})


_PYTEST_VALUE_OPTIONS = frozenset({
    "-k", "-m", "-c", "-p", "-o", "--rootdir", "--ignore", "--deselect", "--junitxml",
    "--confcutdir", "--basetemp", "--ignore-glob", "--maxfail", "-n",
})
_PYTEST_TEST_PATH = re.compile(r"^[\w./-]+\.py(::.*)?$")


_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _pytest_argv_tail(argv: list[str]) -> list[str] | None:
    """Arguments after pytest when argv is pytest-shaped, else None."""
    while argv and _ENV_ASSIGNMENT.match(argv[0]):
        argv = argv[1:]
    if argv[:2] == ["uv", "run"]:
        argv = argv[2:]
        while argv and argv[0].startswith("-") and argv[0] != "-m":
            argv = argv[1:]
    if not argv:
        return None
    try:
        program = Path(argv[0]).name
    except ValueError:
        return None
    if program in {"pytest", "py.test"}:
        return argv[1:]
    for index, token in enumerate(argv[:-1]):
        if token == "-m" and argv[index + 1] == "pytest":
            return argv[index + 2 :]
    for index, token in enumerate(argv):
        if token == "-mpytest":
            return argv[index + 1 :]
    return None


def _pytest_named_paths(command: str) -> list[str] | None:
    """Test paths named by a pytest-shaped command; None when it is not pytest-shaped."""
    try:
        rest = _pytest_argv_tail(shlex.split(command))
    except ValueError:
        return None
    if rest is None:
        return None
    paths: list[str] = []
    for index, token in enumerate(rest):
        if token.startswith("-") or not _PYTEST_TEST_PATH.match(token):
            continue
        if index and rest[index - 1] in _PYTEST_VALUE_OPTIONS:
            continue
        paths.append(token.split("::", 1)[0])
    return paths


def _base_run_collected_nothing(evidence, checkout: Path) -> str | None:
    """Reason when a pytest-shaped base run proves nothing ran, else None (#2387).

    pytest exit 4 (usage error / file not found) or 5 (no tests collected), a
    named test path absent from the base checkout, or one that is absolute or
    escapes the checkout (could point into the worker tree), is not a real base
    failure: the worker may add that very test file, so base never exercised the
    oracle.  Non-pytest verifiers keep the plain exit-code meaning.
    """
    root = checkout.resolve()
    for item in evidence:
        paths = _pytest_named_paths(item.command)
        if paths is None:
            continue
        for path in paths:
            if Path(path).is_absolute() or not (checkout / path).resolve().is_relative_to(root):
                return "base_test_path_outside_checkout"
        if any(not (checkout / path).exists() for path in paths):
            return "base_test_path_missing"
        if item.exit_code in (4, 5):
            return "base_collected_no_tests"
    return None


def _fail_to_pass_blocked(state: Mapping[str, Any]) -> bool:
    """True when a candidate must not be committed or recovered as verified.

    A required probe blocks until it has durably recorded VERIFIED, so a crash
    between the VERIFIED checkpoint and the probe cannot be recovered into a
    commit that skipped the gate.
    """
    if not isinstance(state, Mapping):
        return False
    probe = state.get("fail_to_pass")
    contract = state.get("contract")
    profile = contract.get("acceptance_profile") if isinstance(contract, Mapping) else None
    evidence = profile.get("required_evidence") if isinstance(profile, Mapping) else None
    # The durable contract, not the probe record, decides whether the gate applies.
    contract_requires = isinstance(evidence, (list, tuple)) and FAIL_TO_PASS_EVIDENCE_TOKEN in evidence
    if not isinstance(probe, Mapping):
        return contract_requires
    if probe.get("status") in _FAIL_TO_PASS_BLOCKED_STATUSES:
        return True
    required = contract_requires or probe.get("required") is True
    return required and probe.get("status") != "VERIFIED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_failure_text(value: Any, *, limit: int = 512) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _task_deadline(contract: ArchitectTaskContract, submitted_at: Optional[str]) -> Optional[float]:
    """Return one absolute wall-clock deadline shared by all attempts."""
    started = _parse_time(submitted_at)
    budget = float(getattr(contract, "maximum_wall_time_seconds", 0) or 0)
    return started + budget if started is not None and budget > 0 else None


_CODEINTEL_LOOKUP_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _codeintel_lookup_context(raw: Any, workspace_root: Any) -> dict[str, Any]:
    """Codeintel executor inputs from ``codeintel_lookup`` (#1579), or nothing.

    Re-validated here against the leased target worktree whatever the caller:
    a dotted identifier (max 128) and 1-4 ``.py`` paths that are relative, contain
    no symlink component, resolve inside the worktree and are existing regular
    files.  Any doubt yields no lookup inputs, so the executor keeps refusing
    instead of reading outside the worktree or "looking up" in zero files.
    """
    if not isinstance(raw, Mapping) or not workspace_root:
        return {}
    symbol = raw.get("target_symbol")
    if (
        not isinstance(symbol, str)
        or len(symbol) > 128
        or not _CODEINTEL_LOOKUP_SYMBOL.fullmatch(symbol)
    ):
        return {}
    paths = raw.get("search_paths")
    if not isinstance(paths, list) or not 1 <= len(paths) <= 4:
        return {}
    try:
        root = Path(str(workspace_root)).resolve(strict=True)
    except (OSError, RuntimeError):
        return {}
    for rel in paths:
        if not isinstance(rel, str) or not rel.endswith(".py"):
            return {}
        parts = Path(rel).parts
        if not parts or Path(rel).is_absolute() or any(part in ("", ".", "..") for part in parts):
            return {}
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                return {}
        try:
            resolved = current.resolve(strict=True)
        except (OSError, RuntimeError):
            return {}
        if root not in resolved.parents or not resolved.is_file():
            return {}
    return {"target_symbol": symbol, "search_paths": tuple(paths)}


def resolve_canonical_target_roots(
    task_id: str,
    campaign_id: Optional[str] = None,
    requested_target_worktree_root: Optional[str] = None,
    requested_target_repo_root: Optional[str] = None,
) -> tuple[Path, Path]:
    disabled_parts = {"nexus-worktrees"}
    for requested_root in (requested_target_worktree_root, requested_target_repo_root):
        if requested_root and disabled_parts.intersection(Path(requested_root).expanduser().parts):
            raise ValueError("DISABLED_TARGET_ROOT: nexus-worktrees is retired; use /Users/jameschen/Workspace/nexus-runtime-targets")

    override = os.getenv("NEXUS_TARGET_ROOT_OVERRIDE", "").strip()
    if override:
        base_worktree_root = Path(override).expanduser().resolve()
    elif requested_target_worktree_root and "/private/tmp" not in requested_target_worktree_root and "/tmp" not in requested_target_worktree_root:
        base_worktree_root = Path(requested_target_worktree_root).expanduser().resolve()
    else:
        workspace_root = Path.cwd().resolve()
        if workspace_root == CANONICAL_SOURCE_ROOT:
            base_worktree_root = CANONICAL_SOURCE_ROOT.parent / "nexus-runtime-targets"
        elif "nexus-runtime-targets" in workspace_root.parts:
            idx = workspace_root.parts.index("nexus-runtime-targets")
            base_worktree_root = Path(*workspace_root.parts[:idx + 1])
        else:
            base_worktree_root = workspace_root.parent / "nexus-runtime-targets"
        if campaign_id:
            base_worktree_root = base_worktree_root / campaign_id

    if requested_target_repo_root and "/private/tmp" not in requested_target_repo_root and "/tmp" not in requested_target_repo_root:
        target_repo_root = Path(requested_target_repo_root).expanduser().resolve()
    else:
        target_repo_root = base_worktree_root / task_id

    if disabled_parts.intersection(base_worktree_root.parts) or disabled_parts.intersection(target_repo_root.parts):
        raise ValueError("DISABLED_TARGET_ROOT: nexus-worktrees is retired; use /Users/jameschen/Workspace/nexus-runtime-targets")
    return base_worktree_root, target_repo_root


def validate_task_card_binding(contract: ArchitectTaskContract, request: Mapping[str, Any], *, is_ephemeral: bool = False) -> None:
    if request.get("allow_unbound_test_identity") is True and not is_ephemeral:
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True")

    allow_unbound = (
        is_ephemeral
        and not request.get("task_card_required")
        and not request.get("lifecycle_identity_required")
        and request.get("allow_unbound_test_identity") is not False
    )

    if str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
        inline = request.get("owner_inline_contract")
        try:
            validate_owner_inline_contract(
                inline if isinstance(inline, Mapping) else {},
                expected_task_id=contract.task_id,
                expected_head=str(contract.controller_revision or ""),
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return

    task_id = contract.task_id
    card_path_str = request.get("task_card_path")
    card_path = None
    if card_path_str:
        card_path = _resolve_task_card_path(card_path_str)
    else:
        possible = Path.cwd() / f"tasks/{task_id}.md"
        if possible.exists():
            card_path = possible
        else:
            matches = list(Path.cwd().glob(f"tasks/*/{task_id}.md")) + list(Path.cwd().glob(f"tasks/*/*{task_id}*.md"))
            card_path = matches[0] if matches else None

    if not card_path or not card_path.exists():
        if not allow_unbound:
            raise RuntimeError(f"TASK_CARD_BINDING_MISMATCH: task card does not exist for task_id '{task_id}'")
        return

    content = card_path.read_text(encoding="utf-8")
    if f"task_id: `{task_id}`" not in content and f"task_id: {task_id}" not in content and f"`{task_id}`" not in content and f"task_id: '{task_id}'" not in content:
        raise RuntimeError(f"TASK_CARD_BINDING_MISMATCH: task card task_id does not match lifecycle task_id '{task_id}'")

    if "AUTO_CHAIN: true" in content or "AUTO_CHAIN=true" in content:
        raise RuntimeError("TASK_CARD_BINDING_MISMATCH: AUTO_CHAIN must be false")


def resolve_lifecycle_identity(contract: ArchitectTaskContract, request: Mapping[str, Any], *, is_ephemeral: bool = False) -> dict[str, Any]:
    if request.get("allow_unbound_test_identity") is True and not is_ephemeral:
        raise RuntimeError("LIFECYCLE_REVISION_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True")

    allow_unbound = (
        is_ephemeral
        and not request.get("lifecycle_identity_required")
        and not request.get("task_card_required")
        and request.get("allow_unbound_test_identity") is not False
    )

    source_root = Path(__file__).resolve().parents[2]
    current_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source_root, capture_output=True, text=True
    ).stdout.strip()
    req_rev = request.get("required_lifecycle_revision")
    if req_rev:
        if current_rev != req_rev and not current_rev.startswith(req_rev):
            raise RuntimeError(f"LIFECYCLE_REVISION_MISMATCH: current revision {current_rev} does not match required {req_rev}")

    if str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
        inline = request.get("owner_inline_contract")
        try:
            validated = validate_owner_inline_contract(
                inline if isinstance(inline, Mapping) else {},
                expected_task_id=contract.task_id,
                expected_head=str(contract.controller_revision or ""),
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        return {
            "lifecycle_revision": current_rev,
            "lifecycle_executable_path": str(Path(sys.executable).resolve()),
            "worker_module_path": str(Path(__file__).resolve()),
            "controller_revision": contract.controller_revision,
            "contract_kind": ContractKind.OWNER_INLINE.value,
            "contract_hash": validated["contract_hash"],
            "owner_inline_contract": validated,
            "task_card_path": None,
            "task_card_hash": None,
        }

    card_path_str = request.get("task_card_path")
    card_path = None
    if card_path_str:
        card_path = _resolve_task_card_path(card_path_str)
    else:
        task_id = contract.task_id
        possible = Path.cwd() / f"tasks/{task_id}.md"
        if possible.exists():
            card_path = possible
        else:
            matches = list(Path.cwd().glob(f"tasks/*/{task_id}.md")) + list(Path.cwd().glob(f"tasks/*/*{task_id}*.md"))
            card_path = matches[0] if matches else None

    card_path_res = str(card_path.resolve()) if card_path and card_path.exists() else None
    card_hash = None
    if card_path and card_path.exists():
        card_hash = hashlib.sha256(card_path.read_bytes()).hexdigest()

    if not allow_unbound:
        if not current_rev or not card_path_res or not card_hash or not contract.controller_revision:
            raise RuntimeError("LIFECYCLE_REVISION_MISMATCH: missing required lifecycle identity binding fields")

    return {
        "lifecycle_revision": current_rev,
        "lifecycle_executable_path": str(Path(sys.executable).resolve()),
        "worker_module_path": str(Path(__file__).resolve()),
        "controller_revision": contract.controller_revision,
        "contract_kind": ContractKind.TRACKED_TASK_CARD.value if card_hash else ContractKind.NONE.value,
        "contract_hash": None,
        "task_card_path": card_path_res,
        "task_card_hash": card_hash,
    }


def _resolve_task_card_path(value: str | Path) -> Path:
    """Resolve a repository-relative card independent of the Gateway cwd."""
    raw = Path(value).expanduser()
    if raw.is_absolute():
        return raw.resolve()
    direct = raw.resolve()
    if direct.exists():
        return direct
    return (CANONICAL_SOURCE_ROOT / raw).resolve()


def validate_lifecycle_revision(contract: ArchitectTaskContract, request: Mapping[str, Any]) -> None:
    resolve_lifecycle_identity(contract, request)


def check_fast_lane_eligible(contract: ArchitectTaskContract, request: Optional[Mapping[str, Any]] = None) -> bool:
    req = request or {}
    allowed_files = getattr(contract, "allowed_files", ()) or ()
    verifier_commands = getattr(contract, "verifier_commands", ()) or ()
    max_provider_calls = getattr(contract, "maximum_provider_calls", 1)
    max_deleted = getattr(contract, "maximum_deleted_files", 0)

    if len(allowed_files) > 4:
        return False
    if max_provider_calls > 1:
        return False
    if not verifier_commands:
        return False
    if getattr(contract, "deletion_allowed", False) or max_deleted > 0:
        return False
    if req.get("migration_authority") or req.get("schema_authority"):
        return False
    if req.get("route_authority_mutation"):
        return False
    if req.get("security_policy_weakening"):
        return False
    if getattr(contract, "public_claim_allowed", False) or getattr(contract, "production_ready", False):
        return False
    if getattr(contract, "controller_clean", None) is False or getattr(contract, "target_isolated", None) is False:
        return False

    return True


CANONICAL_SOURCE_BRANCH = "nexus/integration/main"


def _controller_is_separate() -> bool:
    from nexus.orchestrator import canonical_source_root

    return bool(
        canonical_source_root.CONTROLLER_IS_SEPARATE
        or canonical_source_root.CONTROLLER_BINDING_PROBLEM is not None
    )


def resolve_execution_lane(
    request: Mapping[str, Any],
    *,
    active_mutation_tasks: int = 0,
) -> dict[str, Any]:
    """Classify ordinary primary-agent work without allocating a Target."""
    # Ordinary primary-agent work is Direct by default; callers opt into an
    # isolated Target when they need delegation, parallelism, or risk fencing.
    requested = str(request.get("execution_lane", "DIRECT_CANONICAL")).strip().upper()
    if requested not in {"DIRECT_CANONICAL", "ISOLATED_TARGET"}:
        raise ValueError("execution_lane must be DIRECT_CANONICAL or ISOLATED_TARGET")
    if requested == "ISOLATED_TARGET":
        return {
            "execution_lane": "ISOLATED_TARGET",
            "eligible": True,
            "blockers": [],
            "next_action": "prepare_governed_target",
        }

    blockers: list[str] = []
    controller = Path(str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
    if controller != CANONICAL_SOURCE_ROOT:
        blockers.append("controller_is_not_canonical_source")
    if _controller_is_separate():
        # #2230: Direct edits would put non-tasks/ changes into the Controller.
        blockers.append("separate_controller_direct_forbidden")
    if request.get("primary_agent") is not True:
        blockers.append("primary_agent_attestation_required")
    worker = str(request.get("worker", "primary")).strip().lower()
    if worker not in {"", "primary", "codex"}:
        blockers.append("delegated_worker_forbidden")
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if branch != CANONICAL_SOURCE_BRANCH:
            blockers.append("canonical_branch_mismatch")
        dirty = subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if dirty:
            blockers.append("canonical_checkout_dirty")
    except OSError:
        blockers.append("canonical_git_probe_failed")
    if len(request.get("allowed_files") or []) > 4:
        blockers.append("allowed_file_limit_exceeded")
    if active_mutation_tasks > 0:
        blockers.append("another_mutation_task_is_active")
    if request.get("authorized_deletions"):
        blockers.append("deletions_forbidden")
    if request.get("generated_change") or request.get("large_change"):
        blockers.append("generated_or_large_change_forbidden")
    lockfile_names = {
        "uv.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml",
        "yarn.lock", "Cargo.lock", "Gemfile.lock",
    }
    for raw_path in request.get("allowed_files") or []:
        path = str(raw_path).strip().rstrip("/")
        name = Path(path).name
        if name in lockfile_names:
            blockers.append("lockfile_change_forbidden")
        if path.startswith(("generated/", "dist/", "build/", ".next/")) or name.endswith(".generated.json"):
            blockers.append("generated_or_large_change_forbidden")
    for flag in ("migration_authority", "schema_authority", "route_authority_mutation", "security_policy_weakening", "public_claim_allowed", "production_ready"):
        if request.get(flag):
            blockers.append(f"{flag}_forbidden")
    return {
        "execution_lane": "DIRECT_CANONICAL" if not blockers else "ISOLATED_TARGET",
        "eligible": not blockers,
        "blockers": blockers,
        "next_action": "edit_canonical_checkout" if not blockers else "prepare_governed_target",
    }




def _require_verified_receipt_binding(receipt: Any, packet: Mapping[str, Any]) -> None:
    """Consumers recompute the verified receipt hash instead of trusting the packet."""
    if not isinstance(receipt, Mapping) or receipt.get("verified") is not True:
        raise RuntimeError("APPROVAL_UNVERIFIED_CANDIDATE: verified receipt is missing or not verified")
    canonical = json.dumps(
        _jsonable(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != str(packet.get("verified_receipt_hash") or ""):
        raise RuntimeError("APPROVAL_VERIFIED_RECEIPT_HASH_MISMATCH")


def _repository_root_from_git() -> Path | None:
    """The repository root named by the git common dir, or None when unresolvable."""
    source_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=source_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve().parent


def _default_state_dir_for_repository(repository_root: Path) -> Path:
    """Default durable-state root: ``~/.local/state``, never inside the workspace (#1539).

    Pure: never raises. Fixed (no XDG override) so it equals the root the
    auto-deployed Gateway exports; ``NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR``
    stays the only override.
    """
    name = f"{repository_root.name}-self-hosted-state"
    return (Path.home() / ".local" / "state" / name).resolve()


def require_no_legacy_self_hosted_state(repository_root: Path) -> None:
    """Refuse the default root while the legacy sibling tree still holds state."""
    name = f"{repository_root.name}-self-hosted-state"
    legacy = repository_root.parent / name
    new_root = _default_state_dir_for_repository(repository_root)
    # A symlinked default root could redirect writes anywhere, the workspace
    # included (#1539); refuse it like legacy state.
    if (Path.home() / ".local" / "state" / name).is_symlink():
        raise RuntimeError(
            f"{LEGACY_PRESENT_CODE}: default state root ~/.local/state/{name} is a symlink"
        )
    raise_if_legacy_state(legacy, new_root)


def _require_no_legacy_default_state() -> None:
    repository_root = _repository_root_from_git()
    if repository_root is not None:
        require_no_legacy_self_hosted_state(repository_root)


class SelfHostedTaskService(
    _ReconcileRecoveryMixin,
    _FinalizeRuntimeMixin,
    _AmbientTrack1Mixin,
    _WorkerDispatchMixin,
    _TaskBuildMixin,
    _CheckpointMixin,
    _OperatorOutcomeMixin,
    _StateStoreMixin,
    _ActionEnvelopeMixin,
    _EventsMixin,
    _ReadProjectionMixin,
    _InventoryMixin,
    _ClaimsMixin,
):
    _CUSTOM_RUNNER_FORBIDDEN_EVIDENCE_FIELDS = frozenset(
        {
            "admission_binding",
            "canonical_dispatch_envelope",
            "execution",
            "executions",
            "execution_outcome",
            "verified_receipt",
            "verified_receipt_hash",
            "worker_preflight",
            "workforce_admission",
            "workforce_aggregate_binding_hash",
            "workforce_binding_hash",
            "workforce_dispatch",
            "workforce_policy_hash",
        }
    )

    @staticmethod
    def canonical_state_dir() -> Path:
        configured = os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        repository_root = _repository_root_from_git()
        if repository_root is not None:
            return _default_state_dir_for_repository(repository_root)
        source_root = Path(__file__).resolve().parents[2]
        return (source_root / ".nexus/self_hosted_tasks").resolve()

    def __init__(
        self,
        state_dir: str | Path | None = None,
        runner: Optional[Runner] = None,
        *,
        stale_after_seconds: float = 30.0,
        auto_reconcile: bool = True,
        worker_registry: Optional[WorkerRegistry] = None,
        ephemeral: bool = False,
        ambient_core_port: Optional[AmbientCoreControlPort] = None,
    ):
        # The legacy guard applies whenever a production service adopts the
        # default root, whether implicitly or by naming it explicitly (#1539).
        if not ephemeral and not os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip():
            if state_dir is None or (
                Path(state_dir).expanduser().resolve() == self.canonical_state_dir()
            ):
                _require_no_legacy_default_state()
        canonical = self.canonical_state_dir()
        raw_state_dir = Path(state_dir).expanduser() if state_dir is not None else canonical
        self.state_dir = raw_state_dir.resolve()
        temporary_roots = _temporary_state_roots()
        # An explicitly configured canonical root remains production even when
        # tests place it below the system temporary directory.
        is_temporary = self.state_dir != canonical and any(
            root in self.state_dir.parents for root in temporary_roots
        )
        if self.state_dir != canonical and not ephemeral and not is_temporary:
            raise ValueError(f"production tasks must use canonical state root: {canonical}")
        self.ephemeral = ephemeral or is_temporary
        if runner is not None and not self.ephemeral:
            raise RuntimeError("CUSTOM_RUNNER_REQUIRES_EPHEMERAL_STATE")
        self._custom_runner = runner
        self.runner = runner or self._run_default
        self.stale_after_seconds = stale_after_seconds
        self.worker_registry = worker_registry or WorkerRegistry.default()
        self.ambient_core_port = ambient_core_port
        self._threads: dict[str, threading.Thread] = {}
        self._bound_attempt_claims: dict[tuple[str, str], dict[str, Any]] = {}
        self._runtime_state_bridge = RuntimeStateBridge(
            self.state_dir,
            validator=lambda task_id, payload, path: self._validate_state_payload(
                task_id, payload, path
            ),
            error_receipt=self._state_error_receipt,
            before_write=self._normalize_state_write,
        )
        if auto_reconcile:
            self.reconcile_tasks()

    @classmethod
    def _bound_custom_runner_values(cls, values: Mapping[str, Any]) -> dict[str, Any]:
        bounded = {
            key: value
            for key, value in values.items()
            if key not in cls._CUSTOM_RUNNER_FORBIDDEN_EVIDENCE_FIELDS
        }
        bounded.update({
            "execution_authority": "EPHEMERAL_TEST_RUNNER",
            "provider_receipt_authoritative": False,
            "workforce_admission_authoritative": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "promotion_eligible": False,
        })
        return bounded

    def reconcile_task(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return state
        if state.get("state_valid") is False:
            return state
        # External adoption reserves its durable state before touching the
        # Target.  A crash can therefore leave an ADOPTING record which is
        # safe to replay, but must not be treated as a lost worker execution
        # (the generic tail below would otherwise FINAL_BLOCK it).  Rebuild
        # the request from the immutable evidence artifacts and let the
        # adoption path re-check every physical binding.  Missing or corrupt
        # artifacts fail closed rather than guessing a lifecycle outcome.
        if state.get("status") == "ADOPTING":
            return self._resume_external_adoption(task_id, state)
        if state.get("status") == "DIRECT_RECONCILE_REQUIRED":
            return self._reconcile_direct_failure(task_id)
        if state.get("status") in {"DIRECT_STARTED", "DIRECT_APPLIED", "DIRECT_VERIFIED", "DIRECT_COMMITTED"}:
            return self._reconcile_direct_action(task_id)
        projected_pre_apply = self._projected_pre_apply_recovery_evidence(state)
        if projected_pre_apply is not None:
            return self._reconcile_projected_pre_apply_failure(
                task_id,
                projected_pre_apply,
            )
        if (
            state.get("status") == "INTEGRATION_FAILED_PRE_APPLY"
            and state.get("promotion_status") == "INTEGRATION_FAILED_PRE_APPLY"
            and state.get("terminal_status") == "INTEGRATION_FAILED_PRE_APPLY"
        ):
            return state
        if state.get("status") in TERMINAL_STATUSES:
            return state
        if state.get("status") in PENDING_CANDIDATE_STATUSES:
            return state
        if state.get("status") in {"CANDIDATE_COMMITTED", "CANDIDATE_REF_PROTECTED", "TARGET_CLEANED"}:
            owner_pid = state.get("worker_pid")
            owner_heartbeat = _parse_time(state.get("heartbeat_at"))
            owner_fresh = owner_heartbeat is not None and time.time() - owner_heartbeat <= self.stale_after_seconds
            if owner_pid and self._pid_alive(int(owner_pid)) and owner_fresh:
                return state
            if owner_pid and self._pid_alive(int(owner_pid)):
                self._terminate_owned_processes(task_id)
            packet = state.get("promotion_packet") or {}
            candidate_commit = packet.get("candidate_commit_sha")
            if not candidate_commit:
                return self._checkpoint(
                    task_id, "FINAL_BLOCK",
                    {
                        "error": "candidate checkpoint is missing its promotion packet",
                        "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                        "cleanup_blocker": "candidate commit is missing",
                        "cleanup_performed": False,
                        "terminal_status": "FINAL_BLOCK",
                    },
                    attempt_id=state.get("attempt_id"),
                )
            if state.get("status") != "TARGET_CLEANED":
                contract = self._contract_from_state(state)
                lease = self._lease_from_state(state)
                manager = WorktreeManager(root_dir=contract.target_worktree_root)
                candidate_ref = state.get("candidate_ref")
                if not candidate_ref:
                    candidate_ref = manager.protect_candidate(contract, lease, candidate_commit)
                    state = self._checkpoint(
                        task_id, "CANDIDATE_REF_PROTECTED",
                        {"candidate_ref": candidate_ref},
                        attempt_id=state.get("attempt_id"),
                    ) or state
                cleanup = manager.cleanup_terminal_target(
                    contract, lease,
                    candidate_commit=candidate_commit,
                    candidate_ref=str(candidate_ref),
                )
                if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                    terminal = "RETAINED_FOR_REVIEW" if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES" else "FINAL_BLOCK"
                    return self._checkpoint(task_id, terminal, {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_eligible": cleanup.eligible,
                        "terminal_status": terminal,
                    }, attempt_id=state.get("attempt_id"))
                state = self._checkpoint(task_id, "TARGET_CLEANED", {
                    "cleanup_decision": cleanup.decision,
                    "cleanup_blocker": cleanup.blocker,
                    "cleanup_performed": cleanup.performed,
                    "cleanup_eligible": cleanup.eligible,
                    "cleanup_performed_at": _utc_now() if cleanup.performed else state.get("cleanup_performed_at"),
                }, attempt_id=state.get("attempt_id")) or state
            return self._checkpoint(task_id, "PENDING_HUMAN_APPROVAL", {
                "promotion_status": "PENDING_HUMAN_APPROVAL",
                "candidate_status": "PENDING_HUMAN_APPROVAL",
                "terminal_status": "PENDING_HUMAN_APPROVAL",
                "state_retention_status": "ACTIVE",
                "archive_eligible": False,
            }, attempt_id=state.get("attempt_id"))
        pid = state.get("worker_pid")
        heartbeat_at = _parse_time(state.get("heartbeat_at"))
        stale = heartbeat_at is not None and time.time() - heartbeat_at > self.stale_after_seconds
        if pid and self._pid_alive(int(pid)) and not stale:
            return state
        if pid and self._pid_alive(int(pid)) and stale:
            self._terminate_owned_processes(task_id)
            return self._checkpoint(
                task_id,
                "FINAL_BLOCK",
                {"error": "stale task heartbeat; owned process group terminated", "promotion_status": "NOT_CREATED"},
                attempt_id=state.get("attempt_id"),
            )
        if state.get("status") == "TARGET_LEASED":
            contract = state.get("contract") or {}
            target = Path(str(contract.get("target_repo_root", ""))).expanduser().resolve()
            controller = Path(str(contract.get("controller_repo_root", ""))).expanduser().resolve()
            target_exists = target.is_dir()
            manager = WorktreeManager(root_dir=str(contract.get("target_worktree_root") or target.parent))
            entry = manager._worktree_entry(controller, target) if target_exists and controller.is_dir() else None
            head = manager._run_git(["rev-parse", "HEAD"], cwd=target) if entry else None
            dirty = bool(manager._status_bytes(target)) if entry else None
            evidence = {
                "worker_alive": False,
                "heartbeat_fresh": False,
                "target_exists": target_exists,
                "target_registered": entry is not None,
                "target_clean": not dirty if dirty is not None else None,
                "target_head": head,
                "candidate_exists": bool(head and head != contract.get("target_base_revision")),
            }
            if entry and dirty:
                return self._checkpoint(task_id, "RETAINED_FOR_REVIEW", {
                    **evidence,
                    "reconcile_decision": "RETAINED_FOR_REVIEW",
                    "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                    "cleanup_blocker": "dirty target has no durable snapshot",
                    "cleanup_performed": False,
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "TERMINAL",
                }, attempt_id=state.get("attempt_id"))
            if entry and head != contract.get("target_base_revision"):
                if state.get("candidate") and state.get("execution"):
                    resumed = self._checkpoint(
                        task_id, "CANDIDATE_CAPTURED",
                        {**evidence, "reconcile_decision": "RESUME_CANDIDATE_VERIFICATION"},
                        attempt_id=state.get("attempt_id"),
                    )
                    return self._launch_worker(task_id, str(state.get("attempt_id"))) or resumed
                return self._checkpoint(task_id, "RETAINED_FOR_REVIEW", {
                    **evidence,
                    "reconcile_decision": "RETAINED_FOR_REVIEW",
                    "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                    "cleanup_blocker": "candidate HEAD lacks recoverable receipt evidence",
                    "cleanup_performed": False,
                    "terminal_status": "RETAINED_FOR_REVIEW",
                    "state_retention_status": "TERMINAL",
                }, attempt_id=state.get("attempt_id"))
            cleanup_decision = "ALREADY_REMOVED"
            cleanup_performed = entry is None
            cleanup_blocker = None
            cleanup_eligible = True
            if entry:
                lease_data = state.get("lease") or {
                    "schema": "nexus.target_worktree_lease.v1",
                    "lease_id": manager._lease_id(
                        self._contract_from_state(state),
                        target,
                        f"nexus/task/{task_id}",
                    ),
                    "task_id": task_id,
                    "controller_revision": contract.get("controller_revision"),
                    "target_base_revision": contract.get("target_base_revision"),
                    "target_worktree": str(target),
                    "target_branch": f"nexus/task/{task_id}",
                    "initial_head": contract.get("target_base_revision"),
                    "initial_status_sha256": hashlib.sha256(b"").hexdigest(),
                    "controller_status_sha256": hashlib.sha256(b"").hexdigest(),
                    "created_from_exact_revision": True,
                    "commit_created": False,
                    "merge_performed": False,
                }
                cleanup = manager.cleanup_terminal_target(
                    self._contract_from_state(state),
                    TargetWorktreeLease(**lease_data),
                )
                cleanup_decision = cleanup.decision
                cleanup_performed = cleanup.performed
                cleanup_blocker = cleanup.blocker
                cleanup_eligible = cleanup.eligible
            return self._checkpoint(task_id, "FINAL_BLOCK", {
                **evidence,
                "reconcile_decision": cleanup_decision,
                "cleanup_decision": cleanup_decision,
                "cleanup_blocker": cleanup_blocker,
                "cleanup_eligible": cleanup_eligible,
                "cleanup_performed": cleanup_performed,
                "cleanup_performed_at": _utc_now() if cleanup_performed else None,
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
            }, attempt_id=state.get("attempt_id"))
        if state.get("status") == "SUBMITTED" or state.get("status") in RESUMABLE_STATUSES:
            return {
                **self._with_task_action(state),
                "reconciliation_required": True,
                "reconciliation_decision": "EXPLICIT_RESUME_REQUIRED",
                "mutation_replayed": False,
                "route_replanned": False,
                "task_card_created": False,
            }
        self._terminate_owned_processes(task_id)
        return self._checkpoint(
            task_id,
            "FINAL_BLOCK",
            {"error": "worker lost before recoverable execution evidence", "promotion_status": "NOT_CREATED"},
            attempt_id=state.get("attempt_id"),
        )

    def recover_retained_candidate(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") != "RETAINED_FOR_REVIEW":
            raise RuntimeError("only a retained candidate can enter recovery")
        packet = state.get("promotion_packet") or {}
        verified = state.get("verified_receipt") or {}
        candidate_commit = str(packet.get("candidate_commit_sha") or "")
        candidate_tree = str(packet.get("candidate_tree_sha") or "")
        if not candidate_commit or not candidate_tree or not verified:
            raise RuntimeError("retained candidate lacks verified durable recovery evidence")
        contract = self._contract_from_state(state)
        lease = self._lease_from_state(state)
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        target = Path(lease.target_worktree).resolve()
        controller = Path(contract.controller_repo_root).resolve()
        if manager._worktree_entry(controller, target) is None:
            raise RuntimeError("retained candidate Target is not a registered worktree")
        if manager.process_checker(target):
            raise RuntimeError("active process uses retained candidate Target")
        if manager._status_bytes(target):
            raise RuntimeError("retained candidate Target has unsaved working-tree changes")
        if manager._run_git(["rev-parse", "HEAD"], cwd=target) != candidate_commit:
            raise RuntimeError("retained candidate HEAD does not match promotion packet")
        if manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=target) != candidate_tree:
            raise RuntimeError("retained candidate tree does not match promotion packet")
        self._checkpoint(task_id, "CANDIDATE_COMMITTED", {
            "error": None,
            "promotion_status": str(packet.get("promotion_status") or "PENDING_HUMAN_APPROVAL"),
            "cleanup_decision": None,
            "cleanup_blocker": None,
            "cleanup_performed": False,
            "terminal_status": None,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
        }, attempt_id=state.get("attempt_id"))
        recovered = self.reconcile_task(task_id)
        if recovered is None:
            raise RuntimeError("retained candidate recovery lost task state")
        return recovered

    def reconcile_tasks(self) -> list[dict[str, Any]]:
        if not self.state_dir.exists():
            return []
        states = []
        for path in sorted(self.state_dir.glob("*.json")):
            state = self.reconcile_task(path.stem)
            if state is not None:
                states.append(state)
        return states

    def resume_task(self, task_id: str) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return None
        if state.get("status") == "SUBMITTED" or state.get("status") in RESUMABLE_STATUSES:
            attempt_id = str(state.get("attempt_id") or "")
            if not attempt_id:
                return {
                    **self._with_task_action(state),
                    "reconciliation_required": True,
                    "reconciliation_decision": "BLOCKED_MISSING_ATTEMPT_ID",
                    "mutation_replayed": False,
                    "route_replanned": False,
                    "task_card_created": False,
                }
            self._bridge_validate_claim(task_id, attempt_id, operation="RESUME_TASK")
            return self._launch_worker(task_id, attempt_id) or self._with_task_action(state)
        return self.reconcile_task(task_id)

    def _submit_direct_canonical(self, request: Mapping[str, Any], task_id: str) -> dict[str, Any]:
        """Record a Target-free canonical mutation intent exactly once."""
        inline_contract = None
        if str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
            try:
                inline_contract = validate_owner_inline_contract(
                    request.get("owner_inline_contract") if isinstance(request.get("owner_inline_contract"), Mapping) else {},
                    expected_task_id=task_id,
                    expected_head=str(request.get("controller_revision") or ""),
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        action = request.get("action") if isinstance(request.get("action"), Mapping) else {}
        action_id = str(request.get("action_id") or action.get("action_id") or f"action-{uuid4().hex}")
        attempt_id = str(request.get("attempt_id") or action.get("attempt_id") or f"attempt-{uuid4().hex}")
        idempotency_key = str(request.get("idempotency_key") or action.get("idempotency_key") or f"{task_id}:{self._request_hash(request)}")
        request_hash = str(request.get("action_request_hash") or action.get("request_hash") or self._request_hash(request))
        canonical_execution = (
            _jsonable(dict(request["canonical_execution_identity"]))
            if isinstance(request.get("canonical_execution_identity"), Mapping)
            else None
        )
        canonical_execution_hashes = (
            {
                name: str(canonical_execution.get(name) or "")
                for name in (
                    "context_hash",
                    "plan_hash",
                    "decision_hash",
                    "projection_hash",
                )
            }
            if canonical_execution is not None
            else None
        )
        if idempotency_key and self.state_dir.exists():
            for current in self._submission_task_states().values():
                if str(current.get("idempotency_key") or "") != idempotency_key:
                    continue
                current_hash = str(current.get("action_request_hash") or current.get("request_hash") or "")
                if current_hash and current_hash != request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return {
                    "schema": "nexus.self_hosted_direct_handoff.v1",
                    "task_id": current.get("task_id"),
                    "status": "DIRECT_CANONICAL_READY",
                    "durable_status": current.get("status"),
                    "execution_lane": "DIRECT_CANONICAL",
                    "target_created": False,
                    "state_created": False,
                    "duplicate": True,
                    "action_id": current.get("action_id"),
                    "attempt_id": current.get("attempt_id"),
                    "idempotency_key": current.get("idempotency_key"),
                    "action_request_hash": current.get("action_request_hash"),
                    "canonical_execution_identity": current.get(
                        "canonical_execution_identity"
                    ),
                    "task_action": current.get("task_action") or self._task_action_envelope(current),
                    "next_action": (current.get("task_action") or {}).get("next_action", "nexus_task_finish"),
                }
        state = self._read_state_snapshot(task_id)
        if state is not None:
            existing_key = str(state.get("idempotency_key") or "")
            existing_hash = str(state.get("action_request_hash") or state.get("request_hash") or "")
            if existing_key == idempotency_key and existing_hash and existing_hash != request_hash:
                raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
            if existing_key and existing_key != idempotency_key and existing_hash and existing_hash != request_hash:
                raise ValueError("DIRECT_TASK_ID_REUSED_WITH_DIFFERENT_REQUEST")
            return {
                "schema": "nexus.self_hosted_direct_handoff.v1",
                "task_id": task_id,
                "status": "DIRECT_CANONICAL_READY",
                "durable_status": state.get("status"),
                "execution_lane": "DIRECT_CANONICAL",
                "target_created": False,
                "state_created": False,
                "duplicate": True,
                "action_id": state.get("action_id"),
                "attempt_id": state.get("attempt_id"),
                "idempotency_key": state.get("idempotency_key"),
                "action_request_hash": state.get("action_request_hash"),
                "canonical_execution_identity": state.get(
                    "canonical_execution_identity"
                ),
                "task_action": state.get("task_action") or self._task_action_envelope(state),
                "next_action": (state.get("task_action") or {}).get("next_action", "nexus_task_finish"),
            }
        now = _utc_now()
        base = str(request.get("controller_revision") or "")
        canonical_action = {
            "schema": "nexus.canonical_action.v1",
            "action_id": action_id,
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "canonical_execution_identity": canonical_execution,
            "canonical_execution_hashes": canonical_execution_hashes,
            "execution_lane": "DIRECT_CANONICAL",
            "intent": {
                "status": "RECORDED",
                "at": now,
                "base_sha": base,
                "allowed_paths": list(request.get("allowed_files") or ()),
            },
            "application": {"status": "PENDING"},
            "verification": {"status": "PENDING"},
            "commit": {"status": "PENDING"},
            "reconciliation": {"status": "PENDING"},
        }
        durable_state = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": task_id,
            "status": "DIRECT_INTENT_RECORDED",
            "submitted_at": now,
            "updated_at": now,
            "heartbeat_at": now,
            "status_history": [{"status": "DIRECT_INTENT_RECORDED", "at": now}],
            "request": _jsonable(dict(request)),
            "action": _jsonable(dict(action)) if action else None,
            "action_id": action_id,
            "attempt_id": attempt_id,
            "attempts": [{
                "attempt_id": attempt_id,
                "action_id": action_id or None,
                "idempotency_key": idempotency_key or None,
                "action_request_hash": request_hash or None,
                "started_at": now,
            }],
            "idempotency_key": idempotency_key,
            "action_request_hash": request_hash,
            "request_hash": request_hash,
            "canonical_execution_identity": canonical_execution,
            "canonical_execution_hashes": canonical_execution_hashes,
            "controller_worktree": str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT),
            "controller_revision": base,
            "contract_kind": str(request.get("contract_kind") or ContractKind.NONE.value),
            "contract_hash": str(request.get("contract_hash") or "") or None,
            "owner_inline_contract": _jsonable(inline_contract),
            "execution_lane": "DIRECT_CANONICAL",
            "target_worktree": None,
            "target_created_at": None,
            "canonical_action": canonical_action,
            "direct_receipt": None,
            "reconciliation_required": False,
            "promotion_status": "NOT_CREATED",
            "candidate_created": False,
            "cleanup_eligible": False,
            "cleanup_decision": None,
            "cleanup_performed": False,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
            "archive_location": None,
            "worker_pid": None,
            "worker_pgid": None,
            "push_performed": False,
        }
        created_state, created = self._create_state(task_id, durable_state)
        return {
            "schema": "nexus.self_hosted_direct_handoff.v1",
            "task_id": task_id,
            "status": "DIRECT_CANONICAL_READY",
            "durable_status": created_state.get("status"),
            "execution_lane": "DIRECT_CANONICAL",
            "controller_repo_root": str(request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT),
            "controller_branch": CANONICAL_SOURCE_BRANCH,
            "target_created": False,
            "state_created": created,
            "duplicate": not created,
            "action_id": created_state.get("action_id"),
            "attempt_id": created_state.get("attempt_id"),
            "idempotency_key": created_state.get("idempotency_key"),
            "action_request_hash": created_state.get("action_request_hash"),
            "canonical_execution_identity": created_state.get(
                "canonical_execution_identity"
            ),
            "next_action": "nexus_task_finish",
            "required_surface": "nexus_self_hosted_direct_complete",
            "required_gate": ["scoped_verifiers", "git_diff_check", "staged_review", "scoped_commit"],
            "task_action": created_state.get("task_action") or self._task_action_envelope(created_state),
        }

    def complete_direct_canonical(
        self,
        request: Mapping[str, Any],
        *,
        expected_commit_sha: Optional[str] = None,
    ) -> dict[str, Any]:
        """Complete one durable Target-free canonical action idempotently."""
        task_id = str(request.get("task_id") or "")
        if not task_id:
            raise RuntimeError("DIRECT_ACTION_ID_REQUIRED")
        state = self._read_state_snapshot(task_id)
        if state is None:
            raise RuntimeError("DIRECT_ACTION_NOT_FOUND_RECONCILE_REQUIRED")
        if state.get("status") == "DIRECT_COMPLETED":
            receipt = dict(state.get("direct_receipt") or {})
            if expected_commit_sha and receipt.get("commit_sha") != expected_commit_sha:
                raise RuntimeError("DIRECT_CANONICAL_COMMIT_MISMATCH: duplicate finish commit differs")
            receipt.update({"duplicate": True, "state_created": True, "target_created": False})
            return receipt
        if state.get("status") == "DIRECT_RECONCILE_REQUIRED":
            raise RuntimeError("DIRECT_RECONCILE_REQUIRED: reconcile before retry")
        stored_request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        effective_request = dict(stored_request)
        effective_request.update(dict(request))
        action = dict(state.get("canonical_action") or {})
        now = _utc_now()
        self._mutate_state(task_id, lambda current: (
            current.update({
                "status": "DIRECT_STARTED",
                "updated_at": now,
                "heartbeat_at": now,
                "canonical_action": {
                    **dict(current.get("canonical_action") or {}),
                    "application": {"status": "STARTED", "at": now},
                },
            }),
            current.setdefault("status_history", []).append({"status": "DIRECT_STARTED", "at": now}),
        ))
        try:
            receipt = dict(self._complete_direct_canonical_physical(effective_request, expected_commit_sha=expected_commit_sha))
        except Exception as exc:
            self._record_direct_failure(task_id, "DIRECT_CANONICAL_FAILED", str(exc))
            raise
        commit_sha = str(receipt.get("commit_sha") or "")
        controller = Path(str(effective_request.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).resolve()
        tree_sha = ""
        if commit_sha:
            tree_sha = subprocess.run(
                ["git", "rev-parse", f"{commit_sha}^{{tree}}"], cwd=controller,
                capture_output=True, text=True, check=False,
            ).stdout.strip()
        completed_at = _utc_now()
        action = dict(state.get("canonical_action") or action)
        action.update({
            "application": {"status": "APPLIED", "at": completed_at},
            "verification": {
                "status": "PASSED",
                "at": completed_at,
                "evidence": receipt.get("verifier_evidence") or {},
            },
            "commit": {"status": "COMMITTED", "at": completed_at, "sha": commit_sha, "tree_sha": tree_sha},
            "reconciliation": {"status": "RECONCILED", "at": completed_at},
        })
        receipt.update({
            "state_created": True,
            "target_created": False,
            "duplicate": False,
            "action_id": state.get("action_id"),
            "attempt_id": state.get("attempt_id"),
            "idempotency_key": state.get("idempotency_key"),
            "action_request_hash": state.get("action_request_hash"),
            "base_sha": state.get("controller_revision"),
            "candidate_tree_sha": tree_sha,
            "reconciliation_status": "RECONCILED",
        })
        self._mutate_state(task_id, lambda current: (
            current.update({
                "status": "DIRECT_COMPLETED",
                "updated_at": completed_at,
                "heartbeat_at": completed_at,
                "canonical_action": action,
                "direct_receipt": receipt,
                "commit_sha": commit_sha,
                "candidate_tree_sha": tree_sha,
                "reconciliation_required": False,
                "terminal_status": "DIRECT_COMPLETED",
            }),
            current.setdefault("status_history", []).append({"status": "DIRECT_COMPLETED", "at": completed_at}),
        ))
        return receipt

    def _complete_direct_canonical_physical(
        self,
        request: Mapping[str, Any],
        *,
        expected_commit_sha: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify a primary-agent commit already made on the canonical checkout.

        This is the physical post-commit gate. The public wrapper records the
        durable action state before and after this method; this helper only
        proves the commit and verifiers.
        """
        current_task_id = str(request.get("task_id") or "")
        active = sum(
            1
            for state in self._workspace_task_states().values()
            if state.get("task_id") != current_task_id
            if state.get("status") not in TERMINAL_STATUSES
            and state.get("status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}
        )
        lane = resolve_execution_lane(request, active_mutation_tasks=active)
        if str(request.get("execution_lane", "")).strip().upper() != "DIRECT_CANONICAL":
            raise RuntimeError("DIRECT_CANONICAL completion requires explicit execution_lane")
        if not lane["eligible"]:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: " + ",".join(lane["blockers"]))
        controller = CANONICAL_SOURCE_ROOT
        started = time.perf_counter()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1"], cwd=controller,
            capture_output=True, text=True, check=False,
        )
        if status.returncode != 0 or status.stdout.strip():
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: canonical checkout must be clean after commit")
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if branch != CANONICAL_SOURCE_BRANCH:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: canonical branch drift")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if expected_commit_sha and head != expected_commit_sha:
            raise RuntimeError("DIRECT_CANONICAL_COMMIT_MISMATCH: HEAD differs from expected commit")
        worktree_manager = WorktreeManager(
            root_dir=str(controller.parent / "nexus-runtime-targets"),
            create_root=False,
        )
        worktree_audit = worktree_manager.audit_direct_completion(
            controller_root=controller,
            expected_head=head,
            expected_branch=CANONICAL_SOURCE_BRANCH,
            allowed_files=request.get("allowed_files") or (),
            task_states=self._workspace_task_states(),
        )
        if worktree_audit["blockers"]:
            raise RuntimeError(
                "DIRECT_CANONICAL_BLOCKED: "
                + ",".join(worktree_audit["blockers"])
            )
        base = str(request.get("controller_revision") or "").strip()
        if len(base) != 40:
            raise RuntimeError("DIRECT_CANONICAL_REVISION_REQUIRED: controller_revision must be an exact SHA")
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head], cwd=controller,
            capture_output=True, check=False,
        )
        if ancestry.returncode != 0:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: commit is not descended from controller_revision")
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..{head}"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.splitlines()
        deleted = subprocess.run(
            ["git", "diff", "--diff-filter=D", "--name-only", f"{base}..{head}"], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.splitlines()
        allowed = tuple(str(path).rstrip("/") for path in request.get("allowed_files") or ())
        if not changed:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: commit has no scoped changes")
        if deleted or any(
            not any(path == boundary or boundary.endswith("/") and path.startswith(boundary) for boundary in allowed)
            for path in changed
        ):
            raise RuntimeError("DIRECT_CANONICAL_SCOPE_MISMATCH: commit changed files outside allowed scope")
        diff_check = subprocess.run(
            ["git", "diff", "--check", f"{base}..{head}"], cwd=controller,
            capture_output=True, text=True, check=False,
        )
        if diff_check.returncode != 0:
            raise RuntimeError("DIRECT_CANONICAL_DIFF_CHECK_FAILED: " + diff_check.stdout.strip())
        commit_shape = subprocess.run(
            ["git", "rev-list", "--parents", "-n", "1", head], cwd=controller,
            capture_output=True, text=True, check=False,
        ).stdout.split()
        if len(commit_shape) != 2:
            raise RuntimeError("DIRECT_CANONICAL_BLOCKED: merge commit is not allowed")
        verifier_started = time.perf_counter()
        verifier_contract = type("DirectVerifierContract", (), {
            "verifier_commands": tuple(str(command) for command in request.get("verifier_commands") or ())
        })()
        direct_candidate = type(
            "DirectCandidatePaths",
            (),
            {
                "changed_files": changed,
                "untracked_files": [],
                "deleted_files": deleted,
            },
        )()
        passed, evidence, failures = CandidateVerifier._run_verifiers(
            verifier_contract,
            str(controller),
            direct_candidate,
        )
        verifier_time_ms = max(0, int((time.perf_counter() - verifier_started) * 1000))
        if not passed:
            raise RuntimeError("DIRECT_CANONICAL_VERIFIER_FAILED: " + ",".join(failures))
        total_time_ms = max(0, int((time.perf_counter() - started) * 1000))
        telemetry = {
            "wall_time_ms": total_time_ms,
            "provider_time_ms": 0,
            "verifier_time_ms": verifier_time_ms,
            "worktree_time_ms": 0,
            "commit_hook_time_ms": 0,
            "cleanup_time_ms": 0,
            "overhead_ms": max(0, total_time_ms - verifier_time_ms),
        }
        receipt = {
            "schema": "nexus.self_hosted_direct_receipt.v1",
            "task_id": str(request.get("task_id") or f"direct-{head[:12]}"),
            "execution_lane": "DIRECT_CANONICAL",
            "status": "DIRECT_CANONICAL_COMPLETED",
            "controller_repo_root": str(controller),
            "controller_branch": branch,
            "commit_sha": head,
            "changed_files": changed,
            "candidate_created": False,
            "target_created": False,
            "state_created": False,
            "worktree_audit": worktree_audit,
            "verifier_evidence": _jsonable(evidence),
            "telemetry": telemetry,
        }
        receipt["receipt_hash"] = hashlib.sha256(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return receipt

    @staticmethod
    def _resolve_current_execution_task_id(request: Mapping[str, Any]) -> str:
        """Resolve durable identity before any route or Target decision."""
        requested_task_id = str(request.get("task_id") or "").strip()
        canonical_identity = request.get("canonical_execution_identity")
        if canonical_identity is not None:
            if not isinstance(canonical_identity, Mapping):
                raise RuntimeError("CURRENT_EXECUTION_IDENTITY_INVALID")
            from nexus.contracts.canonical_execution import (
                validate_canonical_execution_identity,
            )

            try:
                validate_canonical_execution_identity(canonical_identity)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"CURRENT_EXECUTION_IDENTITY_INVALID:{exc}") from exc
            identity_task_id = str(canonical_identity.get("task_id") or "").strip()
            if requested_task_id and requested_task_id != identity_task_id:
                raise RuntimeError("CURRENT_EXECUTION_TASK_ID_MISMATCH")
            return identity_task_id
        if requested_task_id:
            return requested_task_id
        raise RuntimeError("CURRENT_EXECUTION_IDENTITY_REQUIRED")

    def submit_task(self, request: Mapping[str, Any]) -> dict[str, Any]:
        original_request = dict(request)
        original_binding = original_request.get("project_entry_authority_binding")
        request, _ = _validated_action_request(request)
        binding = _validate_project_entry_authority_binding(request)
        if original_binding is not None:
            for key in ("issue", "issue_number"):
                if key in original_request and original_request[key] != int(binding["issue_number"]):
                    raise ValueError("PROJECT_ENTRY_AUTHORITY_ISSUE_MISMATCH")
            if "repository" in original_request and original_request["repository"] != binding["repository"]:
                raise ValueError("PROJECT_ENTRY_AUTHORITY_REPOSITORY_MISMATCH")
            if not isinstance(original_request.get("action"), Mapping):
                outer_hash = str(original_request.get("action_request_hash") or "")
                hash_input = dict(original_request)
                hash_input.pop("action_request_hash", None)
                if not outer_hash:
                    raise ValueError("PROJECT_ENTRY_REQUEST_HASH_MISSING")
                if outer_hash != canonical_request_hash(hash_input):
                    raise ValueError("PROJECT_ENTRY_REQUEST_HASH_MISMATCH")
        task_id = self._resolve_current_execution_task_id(request)
        raw_autonomy_grant = request.get("autonomy_goal_grant")
        autonomy_grant: Optional[AutonomyGoalGrant] = None
        if raw_autonomy_grant is not None:
            if not isinstance(raw_autonomy_grant, Mapping):
                raise ValueError("AUTONOMY_GOAL_GRANT_INVALID")
            try:
                autonomy_grant = AutonomyGoalGrant.model_validate(raw_autonomy_grant)
            except Exception as exc:
                raise ValueError("AUTONOMY_GOAL_GRANT_INVALID") from exc
            now = datetime.now(timezone.utc)
            if autonomy_grant.issued_at > now:
                raise ValueError("AUTONOMY_GOAL_GRANT_NOT_YET_VALID")
            if autonomy_grant.expires_at <= now:
                raise ValueError("AUTONOMY_GOAL_GRANT_EXPIRED")
        action = request.get("action") if isinstance(request.get("action"), Mapping) else {}
        if action and not self.ephemeral:
            # The service remains lifecycle authority; this synchronous guard
            # only validates the caller's already-built envelope before any
            # state, Target, or worker mutation is allowed.
            trusted_manifest = trusted_runtime_manifest_hash()
            if trusted_manifest is None:
                raise RuntimeError("TOOL_MANIFEST_UNAVAILABLE: service cannot accept an unbound runtime manifest")
            pre_action_guard(
                action,
                request=request,
                canonical_root=CANONICAL_SOURCE_ROOT,
                tool_manifest_hash=trusted_manifest,
            )
        action_id = str(request.get("action_id") or action.get("action_id") or "")
        attempt_id_hint = str(request.get("attempt_id") or action.get("attempt_id") or "")
        idempotency_key = str(request.get("idempotency_key") or action.get("idempotency_key") or "")
        action_request_hash = str(
            request.get("action_request_hash")
            or action.get("request_hash")
            or self._request_hash(request)
        )
        states = self._submission_task_states()
        for current in states.values():
            if current.get("task_id") != task_id:
                continue
            _validate_existing_autonomy_binding(current, autonomy_grant)
        if request.get("worker_candidate_ingress") and str(request.get("contract_kind") or "") == ContractKind.OWNER_INLINE.value:
            semantic_fields = (
                "what", "why", "allowed_files", "verifier_commands", "worker", "worker_id",
                "provider", "model", "controller_revision", "target_base_revision",
                "controller_repo_root", "target_repo_root", "target_worktree_root",
                "collaboration_realm", "authority_change_candidate_confirmation",
                "fail_to_pass_required", "protected_contracts",
                "provider_probe_evidence_hash", "provider_binary_path",
                "provider_binary_sha256", "provider_cli_version_sha256",
                "provider_probe_expires_at", "provider_authentication_evidence",
            )
            for current in states.values():
                if current.get("task_id") != task_id or not current.get("request"):
                    continue
                prior = current.get("request") if isinstance(current.get("request"), Mapping) else {}
                if prior.get("worker_candidate_ingress") is not True or str(prior.get("contract_kind") or "") != ContractKind.OWNER_INLINE.value:
                    raise ValueError("WORKER_CANDIDATE_TASK_ID_CONFLICT")
                if all(
                    (bool(prior.get(field)) == bool(request.get(field)))
                    if field in {"authority_change_candidate_confirmation", "fail_to_pass_required"}
                    else prior.get(field) == request.get(field)
                    for field in semantic_fields
                ):
                    return {**self._with_task_action(current), "duplicate": True, "duplicate_action_id": current.get("action_id"), "idempotency_key": current.get("idempotency_key")}
                raise ValueError("WORKER_CANDIDATE_TASK_ID_CONFLICT")
        if action and idempotency_key:
            for current in states.values():
                if str(current.get("idempotency_key") or "") != idempotency_key:
                    continue
                current_hash = str(current.get("action_request_hash") or "")
                if current_hash and action_request_hash and current_hash != action_request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return {
                    **self._with_task_action(current),
                    "duplicate": True,
                    "duplicate_action_id": current.get("action_id"),
                    "idempotency_key": idempotency_key,
                }
        if action.get("action_type") == LifecycleActionType.TASK_RETRY.value:
            _validate_retry_predecessor(request, self._read_state_snapshot(task_id))
        active_mutations = sum(
            1 for state in states.values()
            if state.get("task_id") != task_id
            if not idempotency_key or str(state.get("idempotency_key") or "") != idempotency_key
            if (
                state.get("status") not in TERMINAL_STATUSES
                or (
                    state.get("status") in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW"}
                    and state.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
                )
            )
            and state.get("status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}
        )
        lane = resolve_execution_lane(request, active_mutation_tasks=active_mutations)
        requested_lane = str(request.get("execution_lane") or "").strip().upper()
        if requested_lane in {"", "DIRECT_CANONICAL"}:
            if lane["eligible"] and self._direct_lane_claims_evidence(request):
                # The direct lane has no Core seam; an evidence task must not
                # use it to skip coverage (#2181).
                raise ValueError("EXPECTED_EVIDENCE_REQUIRES_ISOLATED_TARGET")
            if lane["eligible"]:
                if request.get("collaboration_realm") is not None:
                    raise ValueError("COLLABORATION_REALM_DIRECT_CANONICAL_UNSUPPORTED")
                if autonomy_grant is not None:
                    raise ValueError("AUTONOMY_DIRECT_CANONICAL_UNSUPPORTED")
                return self._submit_direct_canonical(request, task_id)
            if requested_lane == "DIRECT_CANONICAL" and str(request.get("worker", "primary")).strip().lower() in {"", "primary", "codex"}:
                raise RuntimeError("DIRECT_CANONICAL_BLOCKED: " + ",".join(lane["blockers"]))
        contract = self.build_contract(request)
        dispatch_binding = validate_workforce_dispatch_binding(request)
        tracked_dispatch_required = _tracked_dispatch_required(request)
        if dispatch_binding is not None and not isinstance(
            dispatch_binding.get("canonical_dispatch_envelope"), Mapping
        ):
            raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_MISSING")
        state_request = dict(request)
        if dispatch_binding is not None:
            state_request.update({
                "worker": dispatch_binding["provider"],
                "provider": dispatch_binding["provider"],
                "model": dispatch_binding["model"],
                "worker_id": dispatch_binding["worker_id"],
                "worker_order": [dispatch_binding["provider"]],
            })
        validate_task_card_binding(contract, request, is_ephemeral=self.ephemeral)
        evidence_error = self._card_evidence_binding_error(contract, request)
        if evidence_error is not None:
            raise ValueError(f"TASK_CARD_EVIDENCE_BINDING_INVALID:{evidence_error}")
        identity = resolve_lifecycle_identity(contract, request, is_ephemeral=self.ephemeral)
        if (
            request.get("worker_candidate_ingress")
            and str(request.get("contract_kind") or "") == ContractKind.TRACKED_TASK_CARD.value
        ):
            requested_card_path = request.get("task_card_path")
            if not requested_card_path or not request.get("task_card_hash"):
                raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked path/hash pair required")
            if (
                identity.get("contract_kind") != ContractKind.TRACKED_TASK_CARD.value
                or identity.get("task_card_path") != str(_resolve_task_card_path(requested_card_path))
                or identity.get("task_card_hash") != request.get("task_card_hash")
            ):
                raise RuntimeError("TASK_CARD_BINDING_MISMATCH: tracked identity drifted")
        collaboration_provenance = CollaborationRealmVerifier.verify_submission(contract)
        if autonomy_grant is not None:
            if autonomy_grant.collaboration_base.head_sha != contract.controller_revision:
                raise ValueError("AUTONOMY_COLLABORATION_BASE_MISMATCH")
            try:
                scope_allowed = all(
                    autonomy_grant.path_policy.allows(str(path).rstrip("/"))
                    for path in contract.allowed_files
                )
            except ValueError as exc:
                raise ValueError("AUTONOMY_TASK_SCOPE_INVALID") from exc
            if not scope_allowed:
                raise ValueError("AUTONOMY_TASK_SCOPE_EXCEEDED")
            if contract.collaboration_realm is not None:
                collaboration = contract.collaboration_realm.collaboration
                if autonomy_grant.repository != collaboration.repository:
                    raise ValueError("AUTONOMY_COLLABORATION_REPOSITORY_MISMATCH")
                if autonomy_grant.collaboration_base != collaboration.base:
                    raise ValueError("AUTONOMY_COLLABORATION_BASE_MISMATCH")
        existing_states = list(self._submission_task_states().values())
        for current in existing_states:
            current_key = str(current.get("idempotency_key") or "")
            if idempotency_key and current_key == idempotency_key:
                current_hash = str(current.get("action_request_hash") or "")
                if current_hash and action_request_hash and current_hash != action_request_hash:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                return {
                    **self._with_task_action(current),
                    "duplicate": True,
                    "duplicate_action_id": current.get("action_id"),
                    "idempotency_key": idempotency_key,
                }
            if (
                current.get("task_id") != contract.task_id
                and identity.get("task_card_hash")
                and current.get("task_card_hash") == identity["task_card_hash"]
                and current.get("status") not in {"SUPERSEDED", "CANCELLED"}
            ):
                existing = self._with_task_action(current)
                return {
                    **existing,
                    "duplicate": {
                        "code": "DUPLICATE_LOGICAL_TASK",
                        "existing_task_id": current.get("task_id"),
                        "next_action": (existing.get("task_action") or {}).get("next_action"),
                        "recommended_tool": (existing.get("task_action") or {}).get("recommended_tool"),
                    },
                }
            if current.get("status") in TERMINAL_STATUSES:
                if current.get("status") not in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW"}:
                    continue
                if current.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
                    continue
            current_controller = (current.get("contract") or {}).get("controller_repo_root")
            if (
                current_controller
                and current.get("status") != "PENDING_HUMAN_APPROVAL"
                and Path(current_controller).resolve() != Path(contract.controller_repo_root).resolve()
            ):
                raise RuntimeError("active Controller lease belongs to a different controller worktree")
            if (
                current.get("task_id") != contract.task_id
                and (
                    current.get("status") in {
                        "TARGET_LEASED", "WORKER_RUNNING", "WORKER_COMPLETED", "CANDIDATE_CAPTURED", "VERIFIED",
                        "FINAL_BLOCK", "RETAINED_FOR_REVIEW",
                    }
                )
            ):
                try:
                    conflict = mutation_domains_conflict(current, contract)
                except ValueError as exc:
                    raise RuntimeError(
                        "serial Target budget exceeded: active Target identity or scope is ambiguous"
                    ) from exc
                if conflict:
                    raise RuntimeError("serial Target budget exceeded: another task owns the overlapping Target")
        controller_path = Path(contract.controller_repo_root).resolve()
        if controller_path.exists() and (controller_path / ".git").exists():
            manager = WorktreeManager(root_dir=contract.target_worktree_root, create_root=False)
            if manager.target_conflict(contract, task_states=self._submission_task_states()):
                raise RuntimeError("serial Target budget exceeded: another task owns the overlapping Target")
        dispatch_envelope = (
            dispatch_binding.get("canonical_dispatch_envelope")
            if isinstance(dispatch_binding, Mapping)
            else None
        )
        effect_authorization_requested = bool(
            request.get("effect_authorization_required")
            or "effect_authorization" in request
            or "tool_projection_requests" in request
        )
        if action:
            attempt_id = attempt_id_hint
        elif isinstance(dispatch_envelope, Mapping):
            bound_attempt_id = str(dispatch_envelope.get("attempt_id") or "")
            if not bound_attempt_id or attempt_id_hint != bound_attempt_id:
                raise RuntimeError("WORKFORCE_DISPATCH_ENVELOPE_IDENTITY_DRIFT")
            attempt_id = bound_attempt_id
        elif effect_authorization_requested:
            if not attempt_id_hint:
                raise RuntimeError("EFFECT_AUTHORIZATION_ATTEMPT_ID_REQUIRED")
            attempt_id = attempt_id_hint
        else:
            attempt_id = uuid4().hex
        now = _utc_now()
        state: dict[str, Any] = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": contract.task_id,
            "status": "SUBMITTED",
            "submitted_at": now,
            "lifecycle_revision": identity["lifecycle_revision"],
            "lifecycle_executable_path": identity["lifecycle_executable_path"],
            "worker_module_path": identity["worker_module_path"],
            "controller_revision": identity["controller_revision"],
            "contract_kind": identity.get("contract_kind", ContractKind.NONE.value),
            "contract_hash": identity.get("contract_hash"),
            "owner_inline_contract": identity.get("owner_inline_contract"),
            "task_card_path": (
                request.get("task_card_path")
                if request.get("worker_candidate_ingress")
                and identity.get("contract_kind") == ContractKind.TRACKED_TASK_CARD.value
                else identity["task_card_path"]
            ),
            "task_card_hash": identity["task_card_hash"],
            "status_history": [{"status": "SUBMITTED", "at": now}],
            "request": _jsonable(state_request),
            "action": _jsonable(dict(action)) if action else None,
            "action_id": action_id or None,
            "attempt_id_hint": attempt_id_hint or None,
            "idempotency_key": idempotency_key or None,
            "action_request_hash": action_request_hash or None,
            "contract": contract.model_dump(mode="json"),
            "contract_hash": contract.contract_hash,
            "controller_worktree": contract.controller_repo_root,
            "controller_revision": contract.controller_revision,
            "controller_status_sha256": None,
            "target_worktree": contract.target_repo_root,
            "target_initial_revision": contract.target_base_revision,
            "target_branch": f"nexus/task/{contract.task_id}",
            "target_created_at": None,
            "worker_provider": (
                None
                if tracked_dispatch_required and dispatch_binding is None
                else contract.preferred_provider
            ),
            "selected_worker_id": (
                dispatch_binding["worker_id"]
                if dispatch_binding
                else None if tracked_dispatch_required else request.get("worker_id")
            ),
            "selected_provider": (
                dispatch_binding["provider"]
                if dispatch_binding
                else None if tracked_dispatch_required else contract.preferred_provider
            ),
            "selected_model": (
                dispatch_binding["model"]
                if dispatch_binding
                else None if tracked_dispatch_required else str(request.get("model") or "")
            ),
            "provider_order": (
                []
                if tracked_dispatch_required and dispatch_binding is None
                else list(contract.provider_order)
            ),
            "workforce_dispatch": dispatch_binding,
            "canonical_dispatch_envelope": (
                dispatch_binding.get("canonical_dispatch_envelope")
                if dispatch_binding else None
            ),
            "workforce_policy_hash": dispatch_binding["policy_hash"] if dispatch_binding else None,
            "workforce_binding_hash": dispatch_binding["binding_hash"] if dispatch_binding else None,
            "workforce_aggregate_binding_hash": dispatch_binding["aggregate_binding_hash"] if dispatch_binding else None,
            "fallback_lineage": [],
            "execution_lane": lane["execution_lane"],
            "execution_lane_blockers": lane["blockers"],
            "worker_selection_mode": str(
                request.get(
                    "worker_selection_mode",
                    "auto" if str(request.get("worker", "codex")).strip().lower() == "auto" else "explicit",
                )
            ),
            "attempt_id": attempt_id,
            "attempts": [{
                "attempt_id": attempt_id,
                "action_id": action_id or None,
                "idempotency_key": idempotency_key or None,
                "action_request_hash": action_request_hash or None,
                "started_at": now,
            }],
            "worker_pid": None,
            "worker_pgid": None,
            "worker_child_pgid": None,
            "worker_started_at": None,
            "worker_finished_at": None,
            "heartbeat_at": now,
            "updated_at": now,
            "promotion_status": "NOT_CREATED",
            "execution_authority": (
                "EPHEMERAL_TEST_RUNNER"
                if self._custom_runner is not None
                else "WORKER_REGISTRY"
            ),
            "source_identity": _source_identity(
                str(Path(contract.controller_repo_root).resolve()),
                contract.controller_revision,
                contract.contract_hash,
                execution_authority=(
                    "EPHEMERAL_TEST_RUNNER"
                    if self._custom_runner is not None
                    else "WORKER_REGISTRY"
                ),
                worker_id=(
                    dispatch_binding["worker_id"]
                    if dispatch_binding
                    else None if tracked_dispatch_required else request.get("worker_id")
                ),
                provider=(
                    dispatch_binding["provider"]
                    if dispatch_binding
                    else None if tracked_dispatch_required else contract.preferred_provider
                ),
                lifecycle_revision=identity.get("lifecycle_revision"),
            ),
            "provider_receipt_authoritative": self._custom_runner is None,
            "workforce_admission_authoritative": self._custom_runner is None,
            "public_claim_allowed": False,
            "production_ready": False,
            "execution_outcome": None,
            "verification_verdict": None,
            "candidate_commit_sha": None,
            "candidate_tree_sha": None,
            "candidate_ref": None,
            "candidate_state_hash": None,
            "verified_receipt_hash": None,
            "salvage_commit_sha": None,
            "salvage_ref": None,
            "salvage_only": False,
            "promotion_eligible": False,
            "approved_binding": None,
            "integration_branch": None,
            "integration_base_sha": None,
            "integration_result_sha": None,
            "terminal_status": None,
            "cleanup_eligible": False,
            "cleanup_decision": None,
            "cleanup_blocker": None,
            "cleanup_performed": False,
            "cleanup_performed_at": None,
            "state_retention_status": "ACTIVE",
            "archive_eligible": False,
            "archive_location": None,
            "merge_performed": False,
            "push_performed": False,
            "collaboration_realm": (
                contract.collaboration_realm.model_dump(mode="json")
                if contract.collaboration_realm is not None else None
            ),
            "submission_collaboration_provenance": collaboration_provenance or None,
            "collaboration_provenance": collaboration_provenance or None,
        }
        if autonomy_grant is not None:
            autonomy_binding = AutonomySubmissionBinding.issue(
                task_id=contract.task_id,
                initial_attempt_id=attempt_id,
                action_request_hash=action_request_hash,
                contract_hash=contract.contract_hash,
                controller_revision=contract.controller_revision,
                repository=autonomy_grant.repository,
                collaboration_base=autonomy_grant.collaboration_base,
                allowed_paths=tuple(
                    str(path).rstrip("/") for path in contract.allowed_files
                ),
                goal_id=autonomy_grant.goal_id,
                grant_hash=autonomy_grant.grant_hash,
            )
            state.update({
                "autonomy_goal_id": autonomy_grant.goal_id,
                "autonomy_goal_grant_hash": autonomy_grant.grant_hash,
                "autonomy_mode": "SHADOW",
                "autonomy_submission_binding": autonomy_binding.model_dump(
                    mode="json"
                ),
            })
        existing, created = self._create_state(contract.task_id, state)
        if not created:
            _validate_existing_autonomy_binding(existing, autonomy_grant)
            existing_status = str(existing.get("status") or "")
            terminal_retry = existing_status in RETRYABLE_TASK_STATUSES
            contract_refreshed = existing.get("contract_hash") != contract.contract_hash
            if contract_refreshed and not (
                terminal_retry
                and existing.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
                and self._terminal_retry_revision_refresh_allowed(existing, request, contract)
            ):
                raise ValueError("task_id already exists with a different contract")
            if existing.get("status") in PENDING_CANDIDATE_STATUSES or existing.get("promotion_status") in {"PENDING_HUMAN_APPROVAL", "APPROVED"}:
                return existing
            if terminal_retry:
                if existing.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}:
                    raise RuntimeError("terminal retry blocked until previous Target disposition")
                predecessor_snapshot = json.loads(json.dumps(existing))
                bound_revision_refresh = isinstance(predecessor_snapshot.get("request"), Mapping) and (
                    "action" in predecessor_snapshot["request"]
                    or "bound_action_request" in predecessor_snapshot["request"]
                ) and contract_refreshed
                predecessor_contract_hash = predecessor_snapshot.get("contract_hash")
                predecessor_request_hash = (
                    canonical_request_hash(
                        _terminal_retry_semantic_payload(predecessor_snapshot["request"])
                    )
                    if bound_revision_refresh
                    else None
                )
                existing = self._reactivate_archived_state(contract.task_id, existing)
                attempt_id = attempt_id_hint or uuid4().hex
                def retry(current: dict[str, Any]) -> None:
                    if bound_revision_refresh:
                        if (
                            current.get("attempt_id") != predecessor_snapshot.get("attempt_id")
                            or current.get("contract_hash") != predecessor_contract_hash
                            or current.get("status") != predecessor_snapshot.get("status")
                            or current.get("cleanup_decision") != predecessor_snapshot.get("cleanup_decision")
                            or canonical_request_hash(
                                _terminal_retry_semantic_payload(current.get("request") or {})
                            ) != predecessor_request_hash
                            or not (
                                _terminal_retry_pre_provider_state_allowed(current)
                                or _terminal_retry_verifier_static_failure_allowed(current)
                            )
                        ):
                            raise RuntimeError("RETRY_PREDECESSOR_CHANGED")
                    packet = current.get("promotion_packet") or {}
                    if packet.get("candidate_commit_sha") or current.get("candidate_ref"):
                        current.setdefault("candidate_history", []).append({
                            "candidate_commit": packet.get("candidate_commit_sha"),
                            "candidate_ref": current.get("candidate_ref"),
                            "candidate_state_hash": packet.get("candidate_state_hash"),
                            "verified_receipt_hash": packet.get("verified_receipt_hash"),
                            "approval_binding": current.get("approved_binding"),
                            "integration_branch": current.get("integration_branch"),
                            "integration_commit": current.get("integration_result_sha"),
                            "final_disposition": current.get("final_disposition") or current.get("status"),
                        })
                    if contract_refreshed:
                        previous_contract = current.get("contract") or {}
                        retry_collaboration_provenance = (
                            CollaborationRealmVerifier.verify_submission(contract) or None
                        )
                        current.setdefault("contract_history", []).append({
                            "attempt_id": current.get("attempt_id"),
                            "contract_hash": current.get("contract_hash"),
                            "controller_revision": previous_contract.get("controller_revision"),
                            "target_base_revision": previous_contract.get("target_base_revision"),
                            "final_disposition": current.get("final_disposition") or current.get("status"),
                        })
                        current.update({
                            "request": _jsonable(dict(request)),
                            "contract": contract.model_dump(mode="json"),
                            "contract_hash": contract.contract_hash,
                            "controller_worktree": contract.controller_repo_root,
                            "controller_revision": contract.controller_revision,
                            "controller_status_sha256": None,
                            "target_worktree": contract.target_repo_root,
                            "target_initial_revision": contract.target_base_revision,
                            "target_branch": f"nexus/task/{contract.task_id}",
                            "target_created_at": None,
                            "worker_provider": contract.preferred_provider,
                            "collaboration_realm": (
                                contract.collaboration_realm.model_dump(mode="json")
                                if contract.collaboration_realm is not None else None
                            ),
                            "submission_collaboration_provenance": retry_collaboration_provenance,
                            "collaboration_provenance": retry_collaboration_provenance,
                        })
                    current.update({
                        "request": _jsonable(state_request),
                        "action": _jsonable(dict(action)) if action else None,
                        "action_id": action_id or None,
                        "attempt_id_hint": attempt_id_hint or None,
                        "idempotency_key": idempotency_key or None,
                        "action_request_hash": action_request_hash or None,
                    })
                    if dispatch_binding is not None:
                        current.update({
                            "worker_provider": dispatch_binding["provider"],
                            "selected_worker_id": dispatch_binding["worker_id"],
                            "selected_provider": dispatch_binding["provider"],
                            "selected_model": dispatch_binding["model"],
                            "provider_order": [dispatch_binding["provider"]],
                            "workforce_dispatch": _jsonable(dispatch_binding),
                            "canonical_dispatch_envelope": _jsonable(
                                dispatch_binding.get("canonical_dispatch_envelope")
                            ),
                            "workforce_policy_hash": dispatch_binding["policy_hash"],
                            "workforce_binding_hash": dispatch_binding["binding_hash"],
                            "workforce_aggregate_binding_hash": dispatch_binding[
                                "aggregate_binding_hash"
                            ],
                        })
                    # Enforce the task-scoped attempt ceiling before mutating
                    # durable lineage.  A rejected retry must not append a
                    # phantom attempt or reset any aggregate budgets.
                    max_attempts = int(getattr(contract, "maximum_attempts_per_task", 1) or 1)
                    if len(current.get("attempts") or ()) >= max_attempts:
                        raise RuntimeError("ATTEMPT_BUDGET_EXHAUSTED")
                    current["attempt_id"] = attempt_id
                    current.setdefault("attempts", []).append({
                        "attempt_id": attempt_id,
                        "action_id": action_id or None,
                        "idempotency_key": idempotency_key or None,
                        "action_request_hash": action_request_hash or None,
                        "canonical_dispatch_envelope": _jsonable(
                            dispatch_binding.get("canonical_dispatch_envelope")
                        )
                        if dispatch_binding is not None
                        else None,
                        "workforce_dispatch": _jsonable(dispatch_binding),
                        "started_at": now,
                    })
                    current["status"] = "SUBMITTED"
                    current.setdefault("status_history", []).append({"status": "ATTEMPT_INCREMENTED", "at": now})
                    current["lease"] = None
                    current["worker_pid"] = None
                    current["worker_pgid"] = None
                    current["worker_child_pgid"] = None
                    current["worker_started_at"] = None
                    current["worker_finished_at"] = None
                    current["worker_preflight"] = None
                    current["heartbeat_at"] = now
                    current["error"] = None
                    current["active_provider"] = None
                    current["execution"] = None
                    # Keep immutable execution history across retries so
                    # aggregate provider calls/attempts cannot be reset.
                    # ``execution`` below is the current attempt only.
                    current["execution_outcome"] = None
                    current["attempt_resolution"] = None
                    current["verification_verdict"] = None
                    current["promotion_status"] = "NOT_CREATED"
                    current["candidate_status"] = None
                    current["candidate"] = None
                    current["candidate_commit_sha"] = None
                    current["candidate_tree_sha"] = None
                    current["candidate_ref"] = None
                    current["candidate_state_hash"] = None
                    current["verified_receipt_hash"] = None
                    current["salvage_commit_sha"] = None
                    current["salvage_ref"] = None
                    current["salvage_only"] = False
                    current["promotion_eligible"] = False
                    current["verified_receipt"] = None
                    current["promotion_packet"] = None
                    current["approved_binding"] = None
                    current["integration_branch"] = None
                    current["integration_base_sha"] = None
                    current["integration_result_sha"] = None
                    current["integration_receipt"] = None
                    current["final_disposition"] = None
                    current["terminal_status"] = None
                    current["cleanup_eligible"] = False
                    current["cleanup_decision"] = None
                    current["cleanup_blocker"] = None
                    current["cleanup_performed"] = False
                    current["cleanup_performed_at"] = None
                    current["state_retention_status"] = "ACTIVE"
                    current["archive_eligible"] = False
                    current["archive_location"] = None
                    current["merge_performed"] = False
                    current["push_performed"] = False
                if existing.get("work_claim"):
                    old_claim = existing["work_claim"]
                    old_ident = old_claim.get("identity") or {}
                    claim_req = {
                        **old_ident,
                        "task_id": contract.task_id,
                        "claim_id": old_claim["claim_id"],
                        "generation": old_claim["generation"],
                        "fencing_token": old_claim["fencing_token"],
                    }
                    recovered = self.recover_work_claim(claim_req, reason="TERMINAL_RETRY")
                    new_claim = dict(recovered["claim"])
                    new_ident = dict(old_ident)
                    new_ident["attempt_id"] = attempt_id
                    new_claim["identity"] = new_ident
                    new_claim["identity_hash"] = self._claim_hash(new_ident)
                    with self._state_lock():
                        retry_state = json.loads(self._state_path(contract.task_id).read_text(encoding="utf-8"))
                        retry_state["work_claim"] = new_claim
                        retry_bindings = self._bindings_of(retry_state)
                        retry_bindings[attempt_id] = self._attempt_binding(
                            new_claim, contract.task_id, attempt_id
                        )
                        retry_state["attempt_claim_bindings"] = retry_bindings
                        self._write_state_locked(contract.task_id, retry_state)
                self._mutate_state(contract.task_id, retry)
                return self._launch_worker(contract.task_id, attempt_id) or self._with_task_action(existing)
            return self.reconcile_task(contract.task_id) or existing
        is_issue_task = bool(
            binding is not None
            or original_binding is not None
            or request.get("issue")
            or request.get("issue_number")
            or request.get("claim_required")
            or getattr(contract, "issue_number", None)
        )
        if is_issue_task:
            claim_req = {
                "task_id": contract.task_id,
                "attempt_id": attempt_id,
                "action_id": action_id or None,
                "repository": (
                    binding.get("repository")
                    if binding
                    else request.get("repository") or getattr(contract, "repository", "")
                ),
                "issue": (
                    binding.get("issue_number")
                    if binding
                    else request.get("issue")
                    or request.get("issue_number")
                    or getattr(contract, "issue_number", "")
                ),
                "worker_id": (
                    dispatch_binding.get("worker_id")
                    if dispatch_binding
                    else request.get("worker_id") or request.get("worker") or ""
                ),
                "provider": (
                    dispatch_binding.get("provider")
                    if dispatch_binding
                    else request.get("provider") or contract.preferred_provider or ""
                ),
                "model": (
                    dispatch_binding.get("model")
                    if dispatch_binding
                    else request.get("model") or ""
                ),
                "role": request.get("role")
                or request.get("worker_role")
                or "bounded_code_candidate",
                "claim_ceiling": request.get("claim_ceiling")
                or "CLAIM_PROTOCOL_CANDIDATE_PR_ONLY",
                "base_revision": contract.target_base_revision,
                "source_hash": (
                    request.get("source_hash")
                    or request.get("source_revision")
                    or contract.controller_revision
                    or ""
                ),
                "task_card_path": (
                    request.get("task_card_path")
                    or getattr(contract, "task_card_path", "")
                    or ""
                ),
                "allowed_files": list(contract.allowed_files),
                "workforce_admission": (
                    dispatch_binding.get("workforce_admission")
                    if dispatch_binding
                    else request.get("workforce_admission")
                    or request.get("admission_binding")
                ),
                "provider_preflight": (
                    request.get("provider_preflight") or request.get("realm_preflight")
                ),
            }
            claim_result = self.acquire_work_claim(claim_req, enforce_issue_uniqueness=True)
            if claim_result.get("status") == "BLOCKED":
                with self._state_lock():
                    path = self._state_path(contract.task_id)
                    if path.exists():
                        path.unlink()
                raise RuntimeError(
                    f"WORK_CLAIM_BLOCKED:{claim_result.get('reason')}"
                )
        return self._launch_worker(contract.task_id, attempt_id) or self._with_task_action(state)

    def retry_task(self, task_id: str) -> dict[str, Any]:
        return retry_task_via_runtime(self, task_id)

    @staticmethod
    def _pre_apply_rejection_evidence(
        state: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Return exact evidence permitting rejection of a stale pre-apply Candidate.

        A failed pre-apply integration is not a normal pending Candidate.  It
        may be rejected only after the durable record proves that no apply,
        result, or integration receipt exists, the owned Target was removed,
        and every Candidate identity remains bound across the packet and the
        consumed approval.  This helper is deliberately narrow: it never
        authorizes SUPERSEDED or any post-apply disposition.
        """
        if (
            state.get("status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("promotion_status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("terminal_status") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("final_disposition") != "INTEGRATION_FAILED_PRE_APPLY"
            or state.get("integration_status") != "NOT_APPLIED"
            or state.get("merge_performed") is not False
            or state.get("integration_result_sha")
            or state.get("integration_receipt")
            or state.get("cleanup_decision") not in {"REMOVED", "ALREADY_REMOVED", "TARGET_CLEANED"}
            or state.get("cleanup_performed") is not True
            or state.get("reconciliation_status") != "RECONCILED"
            or state.get("reconciliation_decision") != "RESTORE_NATIVE_PRE_APPLY_STATUS"
        ):
            return None
        reconciliation_history = state.get("integration_reconciliation_history")
        status_history = state.get("status_history")
        if (
            not isinstance(reconciliation_history, list)
            or not reconciliation_history
            or not isinstance(reconciliation_history[-1], Mapping)
            or not isinstance(status_history, list)
            or not status_history
            or not isinstance(status_history[-1], Mapping)
            or status_history[-1].get("status") != "INTEGRATION_FAILED_PRE_APPLY"
            or status_history[-1].get("reason") != "projected_pre_apply_reconciled"
            or not str(state.get("integration_error") or "").strip()
        ):
            return None
        # Reuse the strict legacy projection validator as the evidence oracle:
        # a reconciled native state must still prove the exact projection that
        # was restored, including closure, acceptance, preview, authorization,
        # consumed grant, history, and execution bindings.
        projected = dict(state)
        projected_history = list(status_history)
        projected_history.pop()
        projected.update({
            "status": "FINAL_BLOCK",
            "promotion_status": "NOT_CREATED",
            "status_history": projected_history,
        })
        projection = SelfHostedTaskService._projected_pre_apply_recovery_evidence(projected)
        if projection is None:
            return None
        recorded = reconciliation_history[-1]
        if (
            recorded.get("decision") != "RESTORE_NATIVE_PRE_APPLY_STATUS"
            or recorded.get("projection_sha256") != projection.get("projection_sha256")
            or any(recorded.get(key) != value for key, value in projection.items())
        ):
            return None
        execution = state.get("integration_execution")
        packet = state.get("promotion_packet")
        approved = state.get("approved_binding")
        if not all(isinstance(value, Mapping) and value for value in (execution, packet, approved)):
            return None
        if (
            execution.get("stage") != "PRE_APPLY"
            or execution.get("merge_performed") is not False
            or execution.get("post_apply_verified") is not False
            or execution.get("branch_head_before") != execution.get("branch_head_after")
        ):
            return None
        identity = {
            "task_id": str(state.get("task_id") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "candidate_commit_sha": str(packet.get("candidate_commit_sha") or ""),
            "candidate_tree_sha": str(packet.get("candidate_tree_sha") or ""),
            "candidate_state_hash": str(packet.get("candidate_state_hash") or ""),
            "verified_receipt_hash": str(packet.get("verified_receipt_hash") or ""),
        }
        candidate_ref = str(state.get("candidate_ref") or "")
        if (
            not all(identity.values())
            or not re.fullmatch(
                rf"refs/nexus-candidates/{re.escape(identity['task_id'])}/{re.escape(identity['candidate_commit_sha'])}",
                candidate_ref,
            )
        ):
            return None
        for key in (
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
        ):
            if str(approved.get(key) or "") != identity[key]:
                return None
        if (
            str(approved.get("bound_task_id") or identity["task_id"]) != identity["task_id"]
            or str(approved.get("bound_attempt_id") or identity["attempt_id"]) != identity["attempt_id"]
        ):
            return None
        return {
            **identity,
            "candidate_ref": candidate_ref,
            "cleanup_decision": str(state["cleanup_decision"]),
            "cleanup_performed": True,
            "stage": "PRE_APPLY",
            "merge_performed": False,
            "integration_status": "NOT_APPLIED",
        }

    def dispose_candidate(
        self,
        task_id: str,
        *,
        disposition: str,
        superseded_by: Optional[str] = None,
    ) -> dict[str, Any]:
        disposition = disposition.upper()
        if disposition not in {"REJECTED", "SUPERSEDED"}:
            raise ValueError("candidate disposition must be REJECTED or SUPERSEDED")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if str(state.get("task_id") or "") != task_id:
            raise RuntimeError("CLOSURE_TASK_ID_DRIFT")
        if disposition == "REJECTED" and state.get("status") == "REJECTED":
            history = state.get("candidate_history") or []
            if history and isinstance(history[-1], Mapping) and history[-1].get("pre_apply_disposition_basis"):
                return {**state, "duplicate": True}
        pre_apply_basis = None
        if disposition == "REJECTED" and state.get("status") == "INTEGRATION_FAILED_PRE_APPLY":
            pre_apply_basis = self._pre_apply_rejection_evidence(state)
            if pre_apply_basis is None:
                raise RuntimeError("PRE_APPLY_REJECTION_EVIDENCE_REQUIRED")
        if state.get("promotion_status") not in {"PENDING_HUMAN_APPROVAL", "APPROVED"}:
            if pre_apply_basis is None:
                raise RuntimeError("candidate is not pending disposition")
        candidate_record = {
            "candidate_commit": (state.get("promotion_packet") or {}).get("candidate_commit_sha"),
            "candidate_ref": state.get("candidate_ref"),
            "candidate_state_hash": (state.get("promotion_packet") or {}).get("candidate_state_hash"),
            "verified_receipt_hash": (state.get("promotion_packet") or {}).get("verified_receipt_hash"),
            "approval_binding": state.get("approved_binding"),
            "final_disposition": disposition,
            "supersedes": state.get("supersedes"),
            "superseded_by": superseded_by if disposition == "SUPERSEDED" else None,
        }
        if pre_apply_basis is not None:
            candidate_record["pre_apply_disposition_basis"] = pre_apply_basis
        return self._checkpoint(task_id, disposition, {
            "promotion_status": disposition,
            "candidate_status": disposition,
            "final_disposition": disposition,
            "superseded_by": superseded_by if disposition == "SUPERSEDED" else None,
            "candidate_history": [*state.get("candidate_history", []), candidate_record],
            "terminal_status": disposition,
            "cleanup_decision": state.get("cleanup_decision", "REMOVED"),
            "cleanup_performed": state.get("cleanup_performed", True),
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
        }, attempt_id=state.get("attempt_id")) or state

    def freeze_retained_forensic_target(
        self,
        task_id: str,
        *,
        authority_confirmation: bool = False,
    ) -> dict[str, Any]:
        """Release one retained Target only after preserving its exact negative evidence."""
        def canonical_hash(value: Any) -> str:
            return hashlib.sha256(json.dumps(
                _jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest()

        if authority_confirmation is not True:
            raise RuntimeError("forensic Target release requires explicit Owner authority")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError("forensic Target release requires terminal retained state")
        if (
            state.get("promotion_status") != "NOT_CREATED"
            or state.get("state_retention_status") != "TERMINAL"
        ):
            raise RuntimeError("forensic Target is not terminal evidence-only state")
        if self._retained_state_has_candidate_authority(state):
            raise RuntimeError("forensic Target has Candidate authority")
        for field in ("worker_pid", "worker_pgid", "worker_child_pgid"):
            raw_pid = state.get(field)
            if raw_pid and self._pid_alive(int(raw_pid)):
                raise RuntimeError("forensic Target still has an active process")
        if (
            state.get("forensic_target_released") is True
            and state.get("cleanup_decision") in {"REMOVED", "ALREADY_REMOVED"}
            and state.get("salvage_commit_sha")
            and state.get("salvage_ref")
        ):
            proof = state.get("forensic_negative_proof")
            if (
                not isinstance(proof, Mapping)
                or state.get("forensic_negative_proof_hash") != canonical_hash(proof)
            ):
                raise RuntimeError("forensic negative proof integrity mismatch")
            return state

        stored_contract = state.get("contract")
        if not isinstance(stored_contract, Mapping):
            raise RuntimeError("forensic Target contract is unavailable")
        contract_payload = dict(stored_contract)
        contract_payload.pop("contract_hash", None)
        contract = ArchitectTaskContract.model_validate(contract_payload)
        if state.get("contract_hash") != contract.contract_hash:
            raise RuntimeError("forensic Target contract hash mismatch")
        lease = self._lease_from_state(state)
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        if self._retained_state_has_complete_negative_evidence(state):
            negative_proof = {
                "schema": "nexus.legacy_forensic_compatibility_receipt.v1",
                "negative_proof_mode": "STRICT_CURRENT_COMPLETE_NEGATIVE",
                "synthetic_fields_created": False,
            }
        else:
            negative_proof = self._build_legacy_v1_negative_compatibility_proof(
                task_id, state, contract, lease, manager,
            )
            if negative_proof is None:
                raise RuntimeError("forensic Target negative evidence is incomplete or ambiguous")
        negative_proof_hash = canonical_hash(negative_proof)
        state = self._checkpoint(
            task_id,
            str(state.get("status")),
            {
                "forensic_negative_proof": negative_proof,
                "forensic_negative_proof_hash": negative_proof_hash,
                "forensic_negative_proof_checkpointed": True,
            },
            attempt_id=state.get("attempt_id"),
        ) or state
        if (
            state.get("forensic_negative_proof") != negative_proof
            or state.get("forensic_negative_proof_hash") != negative_proof_hash
        ):
            raise RuntimeError("forensic negative proof checkpoint mismatch")
        salvage = {
            "salvage_commit_sha": state.get("salvage_commit_sha"),
            "salvage_ref": state.get("salvage_ref"),
            "salvage_only": state.get("salvage_only"),
            "promotion_eligible": state.get("promotion_eligible"),
        }
        if not salvage["salvage_commit_sha"] or not salvage["salvage_ref"]:
            salvage = manager.protect_salvage_head(
                contract,
                lease,
                str(state.get("attempt_id") or lease.attempt_id or ""),
            )
            state = self._checkpoint(
                task_id,
                str(state.get("status")),
                {
                    **salvage,
                    "forensic_negative_proof": negative_proof,
                    "forensic_negative_proof_hash": negative_proof_hash,
                    "promotion_status": "NOT_CREATED",
                    "cleanup_decision": "SALVAGED",
                    "cleanup_blocker": None,
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "forensic_target_released": False,
                    "state_retention_status": "TERMINAL",
                    "archive_eligible": False,
                },
                attempt_id=state.get("attempt_id"),
            ) or state
        elif salvage["salvage_only"] is not True or salvage["promotion_eligible"] is not False:
            raise RuntimeError("forensic salvage metadata is invalid")

        cleanup = manager.cleanup_terminal_target(
            contract,
            lease,
            salvage_commit=str(salvage["salvage_commit_sha"]),
            salvage_ref=str(salvage["salvage_ref"]),
        )
        if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
            self._checkpoint(
                task_id,
                str(state.get("status")),
                {
                    **salvage,
                    "forensic_negative_proof": negative_proof,
                    "forensic_negative_proof_hash": negative_proof_hash,
                    "cleanup_decision": cleanup.decision,
                    "cleanup_blocker": cleanup.blocker,
                    "cleanup_performed": cleanup.performed,
                    "cleanup_eligible": cleanup.eligible,
                    "forensic_target_released": False,
                },
                attempt_id=state.get("attempt_id"),
            )
            raise RuntimeError(cleanup.blocker or cleanup.decision)
        return self._checkpoint(
            task_id,
            str(state.get("status")),
            {
                **salvage,
                "forensic_negative_proof": negative_proof,
                "forensic_negative_proof_hash": negative_proof_hash,
                "promotion_status": "NOT_CREATED",
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": None,
                "cleanup_performed": cleanup.performed,
                "cleanup_performed_at": _utc_now() if cleanup.performed else state.get("cleanup_performed_at"),
                "cleanup_eligible": cleanup.eligible,
                "forensic_target_released": True,
                "state_retention_status": "TERMINAL",
                "archive_eligible": False,
                "merge_performed": False,
                "push_performed": False,
            },
            attempt_id=state.get("attempt_id"),
        ) or state

    @staticmethod
    def _retained_state_has_candidate_authority(state: Mapping[str, Any]) -> bool:
        """Return whether retained state contains any positive authority evidence.

        Retained forensic state may preserve explicit negative observations (for
        example ``candidate_created=False`` and ``candidate_commit_allowed=False``),
        but no Candidate, verification, approval, promotion, or integration
        authority may be carried into the salvage path.  Keep this semantic
        check centralized so newly persisted authority fields cannot silently
        bypass a finite denylist.
        """
        negative_boolean_fields = {"candidate_created", "candidate_commit_allowed"}
        authority_prefixes = ("candidate_", "approval_", "integration_")
        authority_fields = {
            "candidate",
            "promotion_packet",
            "verified_receipt",
            "verified_receipt_hash",
            "durable_candidate_receipt",
            "approved_binding",
            "integration_authorization",
            "integration_receipt",
            "promotion_receipt",
            "candidate_receipt",
        }
        for key, value in state.items():
            if key == "candidate" and SelfHostedTaskService._is_negative_candidate_record(value):
                continue
            if key == "verified_receipt" and SelfHostedTaskService._is_negative_verified_record(value):
                continue
            if key in negative_boolean_fields:
                if value not in (None, False):
                    return True
                continue
            if key == "candidate_status":
                # A status is a Candidate lifecycle claim even when it is a
                # terminal-looking value; the forensic path must not infer it.
                if value not in (None, ""):
                    return True
                continue
            if key in authority_fields:
                if value not in (None, {}, [], "", False):
                    return True
                continue
            if key.startswith(authority_prefixes):
                if value not in (None, {}, [], "", False):
                    return True
        return False

    @staticmethod
    def _is_negative_candidate_record(value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and value.get("allowed_scope_passed") is False
            and value.get("commit_created") is False
            and value.get("approval_status") == "PENDING"
            and value.get("public_claim_allowed") is False
            and value.get("production_ready") is False
            and value.get("merge_performed") is False
            and isinstance(value.get("out_of_scope_paths"), (list, tuple))
            and bool(value.get("out_of_scope_paths"))
            and all(isinstance(item, str) and item.strip() for item in value["out_of_scope_paths"])
        )

    @staticmethod
    def _is_negative_verified_record(value: Any) -> bool:
        return (
            isinstance(value, Mapping)
            and value.get("verified") is False
            and value.get("candidate_commit_allowed") is False
            and value.get("candidate_commit_created") is False
            and value.get("public_claim_allowed") is False
            and value.get("production_ready") is False
            and value.get("merge_performed") is False
            and value.get("authority_change_required") is False
            and isinstance(value.get("failure_reasons"), (list, tuple))
            and bool(value.get("failure_reasons"))
            and all(isinstance(item, str) and item.strip() for item in value["failure_reasons"])
            and (
                value.get("scope_gate") is False
                or value.get("scope_gate_passed") is False
                or value.get("verifier_gate") is False
                or value.get("verifier_gate_passed") is False
            )
        )

    @staticmethod
    def _retained_state_has_complete_negative_evidence(state: Mapping[str, Any]) -> bool:
        """Require the exact negative evidence shape before forensic release.

        A retained Target is releasable only when both producer-side records
        explicitly prove that no Candidate authority was created.  Missing,
        malformed, or ambiguous values are deliberately rejected rather than
        interpreted as negative evidence.
        """
        candidate = state.get("candidate")
        verified = state.get("verified_receipt")
        if not isinstance(candidate, Mapping) or not isinstance(verified, Mapping):
            return False

        required_candidate = (
            "allowed_scope_passed",
            "commit_created",
            "approval_status",
            "public_claim_allowed",
            "production_ready",
            "merge_performed",
            "out_of_scope_paths",
        )
        if any(field not in candidate for field in required_candidate):
            return False
        if not SelfHostedTaskService._is_negative_candidate_record(candidate):
            return False

        required_verified = (
            "verified",
            "candidate_commit_allowed",
            "candidate_commit_created",
            "failure_reasons",
            "public_claim_allowed",
            "production_ready",
            "merge_performed",
            "authority_change_required",
        )
        if any(field not in verified for field in required_verified):
            return False
        if not SelfHostedTaskService._is_negative_verified_record(verified):
            return False

        top_level_null_fields = (
            "candidate_commit_sha",
            "candidate_tree_sha",
            "candidate_state_hash",
            "verified_receipt_hash",
            "candidate_ref",
            "approved_binding",
            "promotion_packet",
            "integration_authorization",
            "integration_receipt",
            "promotion_receipt",
        )
        if any(state.get(field) not in (None, {}, [], "") for field in top_level_null_fields):
            return False
        top_level_false_fields = (
            "candidate_created",
            "candidate_commit_created",
            "public_claim_allowed",
            "production_ready",
            "merge_performed",
            "push_performed",
            "authority_change_required",
        )
        required_top_level_fields = (
            "promotion_status",
            "candidate_status",
            *top_level_null_fields,
            *top_level_false_fields,
        )
        if any(field not in state for field in required_top_level_fields):
            return False
        if any(state.get(field) not in (None, False) for field in top_level_false_fields):
            return False
        if state.get("candidate_status") not in (None, ""):
            return False
        return state.get("promotion_status") == "NOT_CREATED"

    def _build_legacy_v1_negative_compatibility_proof(
        self,
        task_id: str,
        state: Mapping[str, Any],
        contract: ArchitectTaskContract,
        lease: TargetWorktreeLease,
        manager: WorktreeManager,
    ) -> dict[str, Any] | None:
        """Re-prove one exact legacy-v1 negative state without synthesizing fields."""
        required_current_fields = {
            "promotion_status", "candidate_status", "candidate_commit_sha",
            "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash",
            "candidate_ref", "approved_binding", "promotion_packet",
            "integration_authorization", "integration_receipt", "promotion_receipt",
            "candidate_created", "candidate_commit_created", "public_claim_allowed",
            "production_ready", "merge_performed", "push_performed",
            "authority_change_required",
        }
        if (
            state.get("schema") != "nexus.self_hosted_task_state.v1"
            or state.get("task_id") != task_id
            or state.get("status") not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}
            or state.get("state_retention_status") != "TERMINAL"
            or not self._legacy_v1_omission_set_matches(state, required_current_fields)
            or not self._is_negative_candidate_record(state.get("candidate"))
            or not self._is_negative_verified_record(state.get("verified_receipt"))
        ):
            return None
        for field in (
            "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash",
            "verified_receipt_hash", "candidate_ref", "approved_binding",
        ):
            if field not in state or state.get(field) is not None:
                return None
        for field in (
            "public_claim_allowed", "production_ready", "merge_performed", "push_performed",
        ):
            if field not in state or state.get(field) is not False:
                return None
        if state.get("promotion_status") != "NOT_CREATED":
            return None

        state_path = self._state_path(task_id)
        try:
            before = os.lstat(state_path)
            if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
                return None
            fd = os.open(state_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    return None
                state_bytes = b""
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    state_bytes += chunk
            finally:
                os.close(fd)
        except OSError:
            return None
        try:
            persisted_state = json.loads(state_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(persisted_state, Mapping) or dict(persisted_state) != dict(state):
            return None

        manager.validate_lease_identity(contract, lease)
        controller_root = Path(contract.controller_repo_root).resolve()
        target = Path(lease.target_worktree).resolve()
        if (
            target != Path(contract.target_repo_root).resolve()
            or str(state.get("target_worktree") or "") != str(target)
            or state.get("attempt_id") != lease.attempt_id
        ):
            return None
        entry = manager._worktree_entry(controller_root, target)
        if entry is None:
            return None
        ownership = manager._read_target_ownership(
            controller_root, entry, task_id, task_state=state,
        )
        if not isinstance(ownership, Mapping):
            return None
        status_bytes = manager._status_bytes(target)
        if status_bytes:
            return None
        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
        target_tree = manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=target)
        candidate = state.get("candidate") or {}
        if (
            entry.get("HEAD") != target_head
            or entry.get("branch") != f"refs/heads/{lease.target_branch}"
            or candidate.get("target_head") != target_head
            or ownership.get("task_id") != task_id
            or ownership.get("attempt_id") != state.get("attempt_id")
            or ownership.get("lease_id") != lease.lease_id
        ):
            return None
        candidate_refs = manager._run_git(
            ["for-each-ref", "--format=%(refname)", f"refs/nexus-candidates/{task_id}/"],
            cwd=controller_root,
        ).splitlines()
        candidate_commit_refs = manager._run_git(
            ["for-each-ref", "--format=%(refname)", f"refs/nexus-candidate-commits/{task_id}/"],
            cwd=controller_root,
        ).splitlines()
        try:
            manager._run_git(
                ["rev-parse", f"refs/nexus-candidates/{task_id}^{{commit}}"],
                cwd=controller_root,
            )
            legacy_candidate_ref = True
        except RuntimeError:
            legacy_candidate_ref = False
        if candidate_refs or candidate_commit_refs or legacy_candidate_ref:
            return None

        def canonical(value: Any) -> str:
            return hashlib.sha256(json.dumps(
                _jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest()
        pre_checkpoint_state_hash = hashlib.sha256(state_bytes).hexdigest()
        legacy_state_origin_hash = pre_checkpoint_state_hash
        existing_proof = state.get("forensic_negative_proof")
        if (
            isinstance(existing_proof, Mapping)
            and state.get("forensic_negative_proof_hash") == canonical(existing_proof)
            and existing_proof.get("task_id") == task_id
            and existing_proof.get("negative_proof_mode")
            == "LEGACY_V1_EXPLICIT_NEGATIVE_COMPATIBILITY"
            and re.fullmatch(
                r"[0-9a-f]{64}", str(existing_proof.get("legacy_state_origin_sha256") or ""),
            )
        ):
            legacy_state_origin_hash = str(existing_proof["legacy_state_origin_sha256"])
        return {
            "schema": "nexus.legacy_forensic_compatibility_receipt.v1",
            "negative_proof_mode": "LEGACY_V1_EXPLICIT_NEGATIVE_COMPATIBILITY",
            "task_id": task_id,
            "attempt_id": state.get("attempt_id"),
            "lease_id": lease.lease_id,
            "state_schema": state.get("schema"),
            "legacy_state_origin_sha256": legacy_state_origin_hash,
            "pre_checkpoint_state_file_sha256": pre_checkpoint_state_hash,
            "state_hash_semantics": "HASH_OF_EXACT_INPUT_BYTES_BEFORE_PROOF_CHECKPOINT",
            "legacy_omitted_fields": sorted(_LEGACY_V1_NEGATIVE_OMISSION_SET),
            "synthetic_fields_created": False,
            "serialized_negative_evidence": {
                "candidate_receipt_sha256": canonical(state.get("candidate")),
                "verified_receipt_sha256": canonical(state.get("verified_receipt")),
                "promotion_status": state.get("promotion_status"),
                "approved_binding": state.get("approved_binding"),
            },
            "physical_negative_evidence": {
                "controller_root": str(controller_root),
                "target_root": str(target),
                "target_head": target_head,
                "target_tree": target_tree,
                "target_status_sha256": hashlib.sha256(status_bytes).hexdigest(),
                "ownership_record_sha256": canonical(ownership),
                "candidate_refs": [],
                "worker_processes_alive": False,
            },
        }

    @staticmethod
    def _legacy_v1_omission_set_matches(
        state: Mapping[str, Any],
        required_current_fields: set[str] | None = None,
    ) -> bool:
        required = required_current_fields or {
            "promotion_status", "candidate_status", "candidate_commit_sha",
            "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash",
            "candidate_ref", "approved_binding", "promotion_packet",
            "integration_authorization", "integration_receipt", "promotion_receipt",
            "candidate_created", "candidate_commit_created", "public_claim_allowed",
            "production_ready", "merge_performed", "push_performed",
            "authority_change_required",
        }
        return required.difference(state.keys()) == _LEGACY_V1_NEGATIVE_OMISSION_SET

    def _store_adoption_artifact(
        self,
        task_id: str,
        digest: str,
        content: bytes,
        kind: str,
    ) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(content).hexdigest() != digest:
            raise RuntimeError(f"{kind} receipt hash mismatch")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", task_id):
            raise RuntimeError("adoption artifact task id is unsafe")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", kind):
            raise RuntimeError("adoption artifact kind is unsafe")

        self.state_dir.mkdir(parents=True, exist_ok=True)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory_flags |= nofollow
        state_fd = os.open(self.state_dir, directory_flags)
        try:
            try:
                os.mkdir("adoption-artifacts", 0o700, dir_fd=state_fd)
            except FileExistsError:
                pass
            try:
                artifact_fd = os.open(
                    "adoption-artifacts", directory_flags, dir_fd=state_fd,
                )
            except OSError as exc:
                raise RuntimeError(
                    "adoption artifact root is not a service-owned directory"
                ) from exc
            try:
                try:
                    os.mkdir(task_id, 0o700, dir_fd=artifact_fd)
                except FileExistsError:
                    pass
                try:
                    task_fd = os.open(task_id, directory_flags, dir_fd=artifact_fd)
                except OSError as exc:
                    raise RuntimeError(
                        "adoption artifact task directory is a symlink or not service-owned"
                    ) from exc
                try:
                    filename = f"{kind}-{digest}.json"
                    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow
                    try:
                        fd = os.open(filename, write_flags, 0o600, dir_fd=task_fd)
                    except FileExistsError:
                        pass
                    else:
                        try:
                            with os.fdopen(fd, "wb") as handle:
                                handle.write(content)
                                handle.flush()
                                os.fsync(handle.fileno())
                            os.fsync(task_fd)
                        except Exception:
                            try:
                                os.unlink(filename, dir_fd=task_fd)
                            except FileNotFoundError:
                                pass
                            raise

                    read_flags = os.O_RDONLY | nofollow
                    try:
                        read_fd = os.open(filename, read_flags, dir_fd=task_fd)
                    except OSError as exc:
                        raise RuntimeError(
                            "adoption artifact is a symlink or unreadable"
                        ) from exc
                    try:
                        if not stat.S_ISREG(os.fstat(read_fd).st_mode):
                            raise RuntimeError("adoption artifact is not a regular file")
                        chunks: list[bytes] = []
                        while True:
                            chunk = os.read(read_fd, 65536)
                            if not chunk:
                                break
                            chunks.append(chunk)
                    finally:
                        os.close(read_fd)
                    if b"".join(chunks) != content:
                        raise RuntimeError("adoption artifact overwrite conflict")
                finally:
                    os.close(task_fd)
            finally:
                os.close(artifact_fd)
        finally:
            os.close(state_fd)
        return str(self.state_dir / "adoption-artifacts" / task_id / filename)

    def adopt_external_candidate(
        self,
        raw_request: ExternalCandidateAdoptionRequest | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Physically verify one immutable Candidate and stop at pending approval."""
        if isinstance(raw_request, ExternalCandidateAdoptionRequest):
            request = ExternalCandidateAdoptionRequest.model_validate(
                raw_request.model_dump(mode="json")
            )
        else:
            request = ExternalCandidateAdoptionRequest.model_validate(dict(raw_request))
        semantic_hash = request.semantic_hash()
        controller_root = Path(CANONICAL_SOURCE_ROOT).resolve()
        manager_probe = WorktreeManager(root_dir=str(controller_root.parent / "nexus-runtime-targets"), create_root=False)
        controller_head = manager_probe._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        if controller_head != request.controller_revision or manager_probe._status_bytes(controller_root):
            raise RuntimeError("external adoption controller revision or clean state mismatch")
        if not self.ephemeral:
            if request.repository != "James3014/Nexus-new":
                raise RuntimeError("external adoption repository identity mismatch")
            try:
                remote = manager_probe._run_git(["remote", "get-url", "origin"], cwd=controller_root)
            except RuntimeError as exc:
                raise RuntimeError("external adoption canonical remote is unavailable") from exc
            normalized_remote = remote.removesuffix(".git").replace("git@github.com:", "https://github.com/")
            if normalized_remote != "https://github.com/James3014/Nexus-new":
                raise RuntimeError("external adoption canonical remote mismatch")
        elif request.repository not in {"LOCAL_TEST", "James3014/Nexus-new"}:
            raise RuntimeError("external adoption repository identity mismatch")

        card_lexical = controller_root / request.task_card_path
        try:
            card_parts = card_lexical.relative_to(controller_root).parts
        except ValueError as exc:
            raise RuntimeError("external adoption Task Card escaped controller root") from exc
        current_card_part = controller_root
        for part in card_parts:
            current_card_part /= part
            if current_card_part.is_symlink():
                raise RuntimeError("external adoption Task Card is unavailable")
        card = card_lexical.resolve()
        try:
            card.relative_to(controller_root)
        except ValueError as exc:
            raise RuntimeError("external adoption Task Card escaped controller root") from exc
        if card.is_symlink() or not card.is_file():
            raise RuntimeError("external adoption Task Card is unavailable")
        card_bytes = card.read_bytes()
        if hashlib.sha256(card_bytes).hexdigest() != request.task_card_hash:
            raise RuntimeError("external adoption Task Card hash mismatch")
        card_text = card_bytes.decode("utf-8")
        if f"task_id: `{request.task_id}`" not in card_text or "AUTO_CHAIN" not in card_text:
            raise RuntimeError("external adoption Task Card identity mismatch")

        validation_bytes = base64.b64decode(request.validation_receipt_b64, validate=True)
        acceptance_bytes = base64.b64decode(request.acceptance_receipt_b64, validate=True)
        if hashlib.sha256(validation_bytes).hexdigest() != request.validation_receipt_sha256:
            raise RuntimeError("validation receipt hash mismatch")
        if hashlib.sha256(acceptance_bytes).hexdigest() != request.acceptance_receipt_sha256:
            raise RuntimeError("acceptance receipt hash mismatch")
        try:
            validation = json.loads(validation_bytes)
            acceptance = json.loads(acceptance_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeError("external adoption evidence must be JSON") from exc
        if not isinstance(validation, Mapping) or not isinstance(acceptance, Mapping):
            raise RuntimeError("external adoption evidence must be JSON objects")

        try:
            projection = parse_historical_epb_task_card(card_bytes)
        except ValueError as exc:
            raise RuntimeError("external adoption Task Card contract is unresolvable") from exc
        raw_derived_candidate = validation.get("candidate")
        if not isinstance(raw_derived_candidate, Mapping):
            raise RuntimeError("external validation receipt candidate binding mismatch")
        validation_candidate: Mapping[str, Any] = dict(raw_derived_candidate)
        derived = {
            "target_base_revision": str(validation_candidate.get("base_commit") or ""),
            "allowed_files": tuple(projection.allowed_repository_paths),
            "forbidden_files": tuple(projection.forbidden_repository_paths),
            "authorized_deletions": (),
            "verifier_commands": tuple(projection.exact_verification_commands),
            "protected_contracts": tuple(projection.protected_contracts),
        }
        derived_projection = {
            "allowed_repository_paths": list(projection.allowed_repository_paths),
            "forbidden_repository_paths": list(projection.forbidden_repository_paths),
            "forbidden_repository_patterns": list(projection.forbidden_repository_patterns),
            "forbidden_scope": list(projection.forbidden_scope),
            "exact_verification_commands": list(projection.exact_verification_commands),
            "authorized_deletions": [],
            "protected_contracts": list(projection.protected_contracts),
            "repository_contract_policy_revision_hash": "",
        }
        for field, expected in derived.items():
            actual = getattr(request, field)
            value = actual if field == "target_base_revision" else tuple(actual)
            if value != expected:
                raise RuntimeError(f"ADOPTION_REQUEST_BINDING_MISMATCH:{field}")
        if tuple(request.action.allowed_paths) != derived["allowed_files"]:
            raise RuntimeError("ADOPTION_REQUEST_BINDING_MISMATCH:action.allowed_paths")

        resolved_base = manager_probe._run_git(
            ["rev-parse", f"{request.target_base_revision}^{{commit}}"], cwd=controller_root,
        )
        resolved_candidate = manager_probe._run_git(
            ["rev-parse", f"{request.candidate_commit_sha}^{{commit}}"], cwd=controller_root,
        )
        if resolved_base != request.target_base_revision or resolved_candidate != request.candidate_commit_sha:
            raise RuntimeError("external adoption base or Candidate identity mismatch")
        try:
            manager_probe._run_git(
                ["merge-base", "--is-ancestor", request.target_base_revision, request.candidate_commit_sha],
                cwd=controller_root,
            )
        except RuntimeError as exc:
            raise RuntimeError("external adoption Candidate ancestry mismatch") from exc
        physical_tree = manager_probe._run_git(
            ["rev-parse", f"{request.candidate_commit_sha}^{{tree}}"], cwd=controller_root,
        )
        if physical_tree != request.candidate_tree_sha:
            raise RuntimeError("external adoption Candidate tree mismatch")
        diff_bytes = manager_probe._run_git_bytes(
            ["diff", "--binary", f"{request.target_base_revision}..{request.candidate_commit_sha}", "--"],
            cwd=controller_root,
        )
        if hashlib.sha256(diff_bytes).hexdigest() != request.candidate_diff_sha256:
            raise RuntimeError("external adoption Candidate diff mismatch")
        changed_paths = sorted(manager_probe._run_git(
            ["diff", "--name-only", request.target_base_revision, request.candidate_commit_sha],
            cwd=controller_root,
        ).splitlines())
        deleted_paths = sorted(manager_probe._run_git(
            ["diff", "--name-only", "--diff-filter=D", request.target_base_revision, request.candidate_commit_sha],
            cwd=controller_root,
        ).splitlines())
        allowed_boundaries = tuple(str(path) for path in request.allowed_files if str(path).strip())
        if not changed_paths or any(
            not any(
                path == boundary
                or (boundary.endswith("/") and path.startswith(boundary))
                for boundary in allowed_boundaries
            )
            for path in (*changed_paths, *deleted_paths)
        ):
            raise RuntimeError("external adoption changed paths differ from contract")
        if sorted(set(deleted_paths) - set(request.authorized_deletions)):
            raise RuntimeError("external adoption contains unauthorized deletions")

        def forbidden_pattern_matches(pattern: str, path: str) -> bool:
            if pattern.endswith("/**"):
                return path.startswith(pattern[:-3] + "/")
            if pattern.endswith("/*"):
                suffix = path.removeprefix(pattern[:-2] + "/")
                return bool(suffix) and "/" not in suffix
            return path == pattern

        if any(
            forbidden_pattern_matches(pattern, path)
            for pattern in projection.forbidden_repository_patterns
            for path in (*changed_paths, *deleted_paths)
        ):
            raise RuntimeError("external adoption changed path is forbidden by Task Card")

        raw_validation_card = validation.get("task_card")
        raw_validation_candidate = validation.get("candidate")
        validation_card: Mapping[str, Any] = raw_validation_card if isinstance(raw_validation_card, Mapping) else {}
        validation_candidate: Mapping[str, Any] = raw_validation_candidate if isinstance(raw_validation_candidate, Mapping) else {}
        if (
            validation.get("schema") != "nexus.evidence_producer_bridge.validation_receipt.v1"
            or validation.get("status") != "EVIDENCE_PRODUCER_BRIDGE_VALIDATED"
            or validation.get("repository") != request.repository
            or validation.get("task") != request.task_id
            or validation_card.get("path") != request.task_card_path
            or validation_card.get("card_file_sha256") != request.task_card_hash
            or validation_candidate.get("base_commit") != request.target_base_revision
            or validation_candidate.get("commit") != request.candidate_commit_sha
            or validation_candidate.get("tree") != request.candidate_tree_sha
            or sorted(validation_candidate.get("changed_paths") or []) != changed_paths
            or sorted(validation_candidate.get("deleted_paths") or []) != deleted_paths
        ):
            raise RuntimeError("external validation receipt binding mismatch")
        if (
            acceptance.get("schema") != "nexus.external_candidate_acceptance.v1"
            or acceptance.get("task_id") != request.task_id
            or acceptance.get("candidate_commit_sha") != request.candidate_commit_sha
            or acceptance.get("candidate_tree_sha") != request.candidate_tree_sha
            or acceptance.get("candidate_diff_sha256") != request.candidate_diff_sha256
            or acceptance.get("validation_receipt_sha256") != request.validation_receipt_sha256
            or acceptance.get("disposition") != "ACCEPT_CANDIDATE"
            or not str(acceptance.get("reviewer_id") or "").strip()
        ):
            raise RuntimeError("external acceptance receipt binding mismatch")

        validation_locator = self._store_adoption_artifact(
            request.task_id, request.validation_receipt_sha256, validation_bytes, "validation",
        )
        acceptance_locator = self._store_adoption_artifact(
            request.task_id, request.acceptance_receipt_sha256, acceptance_bytes, "acceptance",
        )
        target_root, target_path = resolve_canonical_target_roots(
            request.task_id,
            campaign_id="CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01",
        )
        contract_request = {
            "task_id": request.task_id,
            "what": "Physically adopt one immutable externally accepted Candidate",
            "why": "Re-enter normal lifecycle without worker execution or Candidate rewrite",
            "controller_revision": request.controller_revision,
            "target_base_revision": derived["target_base_revision"],
            "controller_repo_root": str(controller_root),
            "target_repo_root": str(target_path),
            "target_worktree_root": str(target_root),
            "allowed_files": list(derived["allowed_files"]),
            "forbidden_files": list(derived["forbidden_files"]),
            "authorized_deletions": list(derived["authorized_deletions"]),
            "verifier_commands": list(derived["verifier_commands"]),
            "protected_contracts": list(derived["protected_contracts"]),
            "worker": "codex",
            "execution_lane": "ISOLATED_TARGET",
        }
        contract = self.build_contract(contract_request)
        sanitized_request = request.model_dump(mode="json", exclude={
            "validation_receipt_b64", "acceptance_receipt_b64",
        })
        reservation = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": request.task_id,
            "status": "ADOPTING",
            "promotion_status": "NOT_CREATED",
            "submitted_at": _utc_now(),
            "updated_at": _utc_now(),
            "status_history": [{"status": "ADOPTING", "at": _utc_now()}],
            "attempt_id": request.attempt_id,
            "action_id": request.action_id,
            "idempotency_key": request.idempotency_key,
            "action": request.action.model_dump(mode="json"),
            "adoption_request_hash": semantic_hash,
            "request": sanitized_request,
            "contract_kind": ContractKind.TRACKED_TASK_CARD.value,
            "contract_hash": contract.contract_hash,
            "task_card_path": request.task_card_path,
            "task_card_hash": request.task_card_hash,
            "controller_worktree": str(controller_root),
            "controller_revision": request.controller_revision,
            "contract": contract.model_dump(mode="json"),
            "target_worktree": str(target_path),
            "target_initial_revision": request.target_base_revision,
            "target_branch": f"nexus/task/{request.task_id}",
            "validation_receipt_locator": validation_locator,
            "acceptance_receipt_locator": acceptance_locator,
            "derived_contract_projection": derived_projection,
            "worker_invocations": 0,
            "candidate_created": False,
            "merge_performed": False,
            "push_performed": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "approved_binding": None,
            "state_retention_status": "ACTIVE",
        }
        persisted, created = self._create_state(request.task_id, reservation)
        if not created:
            if persisted.get("adoption_request_hash") != semantic_hash:
                raise RuntimeError("external adoption task identity or request drift")
            if (
                persisted.get("status") == "PENDING_HUMAN_APPROVAL"
                and persisted.get("adoption_receipt_hash")
            ):
                self._read_adoption_artifact(
                    request.task_id, str(persisted.get("validation_receipt_locator") or ""),
                    request.validation_receipt_sha256, "validation",
                )
                self._read_adoption_artifact(
                    request.task_id, str(persisted.get("acceptance_receipt_locator") or ""),
                    request.acceptance_receipt_sha256, "acceptance",
                )
                try:
                    acceptance = json.loads(
                        self._read_adoption_artifact(
                            request.task_id, str(persisted.get("acceptance_receipt_locator") or ""),
                            request.acceptance_receipt_sha256, "acceptance",
                        ).decode("utf-8")
                    )
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("external adoption replay acceptance artifact is invalid") from exc
                if not isinstance(acceptance, Mapping):
                    raise RuntimeError("external adoption replay acceptance artifact is invalid")
                self._validate_persisted_external_adoption(
                    persisted, request, semantic_hash, acceptance,
                )
                return persisted
            if persisted.get("status") != "ADOPTING":
                raise RuntimeError("external adoption task already exists in an incompatible state")

        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        lease = manager.create_precommitted_lease(
            contract,
            request.candidate_commit_sha,
            request.candidate_tree_sha,
            task_states=self._submission_task_states(),
            attempt_id=request.attempt_id,
        )
        candidate = manager.capture_candidate(contract, lease)
        verified = CandidateVerifier(manager).verify(contract, lease, candidate)
        if not verified.verified or not verified.candidate_commit_allowed:
            raise RuntimeError("external Candidate failed lifecycle-native verification")
        packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified)
        if (
            packet.candidate_commit_sha != request.candidate_commit_sha
            or packet.candidate_tree_sha != request.candidate_tree_sha
        ):
            raise RuntimeError("external Candidate was rewritten during adoption")
        candidate_ref = manager.protect_candidate(
            contract, lease, request.candidate_commit_sha,
        )
        packet_payload = _jsonable(asdict(packet))
        verified_payload = _jsonable(asdict(verified))
        derived_projection["repository_contract_policy_revision_hash"] = verified_payload.get(
            "repository_contract_policy_revision_hash", ""
        )
        adoption_receipt = {
            "schema": "nexus.external_candidate_adoption_receipt.v1",
            "task_id": request.task_id,
            "attempt_id": request.attempt_id,
            "action_id": request.action_id,
            "idempotency_key": request.idempotency_key,
            "adoption_request_hash": semantic_hash,
            "task_card_path": request.task_card_path,
            "task_card_hash": request.task_card_hash,
            "contract_hash": contract.contract_hash,
            "controller_revision": request.controller_revision,
            "target_base_revision": request.target_base_revision,
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_diff_sha256": request.candidate_diff_sha256,
            "candidate_state_hash": packet.candidate_state_hash,
            "verified_receipt_hash": packet.verified_receipt_hash,
            "validation_receipt_sha256": request.validation_receipt_sha256,
            "acceptance_receipt_sha256": request.acceptance_receipt_sha256,
            "repository_contract_policy_revision_hash": verified_payload.get(
                "repository_contract_policy_revision_hash", ""
            ),
            "derived_contract_projection": derived_projection,
            "forbidden_repository_patterns": list(projection.forbidden_repository_patterns),
            "reviewer_id": str(acceptance.get("reviewer_id")),
            "candidate_ref": candidate_ref,
            "promotion_packet_hash": hashlib.sha256(json.dumps(
                packet_payload, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest(),
            "worker_invocations": 0,
            "candidate_rewritten": False,
            "approval_performed": False,
            "integration_performed": False,
            "merge_performed": False,
            "push_performed": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "claim_ceiling": list(_EXTERNAL_ADOPTION_CLAIM_CEILING),
            "issued_at": persisted.get("submitted_at"),
        }
        adoption_receipt_hash = hashlib.sha256(json.dumps(
            adoption_receipt, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()

        def finalize(current: dict[str, Any]) -> None:
            if (
                current.get("status") == "PENDING_HUMAN_APPROVAL"
                and current.get("adoption_request_hash") == semantic_hash
                and current.get("adoption_receipt_hash")
            ):
                return
            if (
                current.get("status") != "ADOPTING"
                or current.get("attempt_id") != request.attempt_id
                or current.get("action_id") != request.action_id
                or current.get("idempotency_key") != request.idempotency_key
                or current.get("adoption_request_hash") != semantic_hash
                or current.get("contract_hash") != contract.contract_hash
            ):
                raise RuntimeError("external adoption state changed before finalization")
            now = _utc_now()
            current.update({
                "status": "PENDING_HUMAN_APPROVAL",
                "promotion_status": "PENDING_HUMAN_APPROVAL",
                "candidate_status": "PENDING_HUMAN_APPROVAL",
                "candidate_commit_sha": packet.candidate_commit_sha,
                "candidate_tree_sha": packet.candidate_tree_sha,
                "candidate_state_hash": packet.candidate_state_hash,
                "verified_receipt_hash": packet.verified_receipt_hash,
                "verified_receipt": verified_payload,
                "promotion_packet": packet_payload,
                "derived_contract_projection": derived_projection,
                "candidate_ref": candidate_ref,
                "candidate": {
                    "candidate_commit_sha": packet.candidate_commit_sha,
                    "candidate_tree_sha": packet.candidate_tree_sha,
                    "candidate_state_hash": packet.candidate_state_hash,
                    "verified_receipt_hash": packet.verified_receipt_hash,
                },
                "lease": _jsonable(asdict(lease)),
                "adoption_receipt": adoption_receipt,
                "adoption_receipt_hash": adoption_receipt_hash,
                "external_acceptance": dict(acceptance),
                "candidate_created": True,
                "promotion_eligible": True,
                "execution_authority": "EXTERNAL_CANDIDATE_ADOPTION",
                "worker_invocations": 0,
                "approved_binding": None,
                "integration_authorization": None,
                "integration_receipt": None,
                "merge_performed": False,
                "push_performed": False,
                "public_claim_allowed": False,
                "production_ready": False,
                "updated_at": now,
                "heartbeat_at": now,
            })
            current.setdefault("status_history", []).append({
                "status": "PENDING_HUMAN_APPROVAL", "at": now,
            })

        finalized = self._mutate_state(request.task_id, finalize)
        if finalized is None:
            raise RuntimeError("external adoption state disappeared before finalization")
        return finalized

    def close_task_without_candidate(
        self,
        task_id: str,
        *,
        superseded_by: str,
    ) -> dict[str, Any]:
        if not superseded_by or not str(superseded_by).strip():
            raise ValueError("superseded_by evidence identifier is required and non-empty")
        superseded_by = str(superseded_by).strip()

        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError(f"task {task_id} is not in RETAINED_FOR_REVIEW or FINAL_BLOCK status")

        if state.get("promotion_status") != "NOT_CREATED":
            raise RuntimeError("promotion_status must be NOT_CREATED")

        packet = state.get("promotion_packet") or {}
        candidate_commit = packet.get("candidate_commit_sha") or state.get("candidate_commit_sha")
        candidate_ref = state.get("candidate_ref")
        candidate_dict = state.get("candidate") or {}
        candidate_created = (
            state.get("candidate_commit_created")
            or packet.get("candidate_commit_created")
            or candidate_dict.get("commit_created")
        )
        if (
            packet
            or candidate_commit
            or candidate_ref
            or candidate_created
        ):
            raise RuntimeError("task has candidate evidence present")

        worker_pid = state.get("worker_pid")
        if worker_pid and self._pid_alive(int(worker_pid)):
            raise RuntimeError("active worker process is running for task")

        child_pgid = state.get("worker_child_pgid")
        if child_pgid and self._pid_alive(int(child_pgid)):
            raise RuntimeError("active worker child process is running for task")

        contract = state.get("contract") or {}
        lease = state.get("lease") or {}
        target_raw = state.get("target_worktree") or lease.get("target_worktree") or contract.get("target_repo_root")
        cleanup_values: dict[str, Any] = {
            "cleanup_decision": state.get("cleanup_decision") or "ALREADY_REMOVED",
            "cleanup_eligible": state.get("cleanup_eligible", True),
            "cleanup_performed": state.get("cleanup_performed", False),
            "cleanup_performed_at": state.get("cleanup_performed_at"),
        }
        if target_raw:
            target_path = Path(str(target_raw)).expanduser().resolve()
            controller_raw = state.get("controller_worktree") or contract.get("controller_repo_root")
            lease_object = TargetWorktreeLease(**dict(lease)) if lease else None
            if target_path.exists() and (not controller_raw or not lease_object):
                raise RuntimeError(f"recorded Target path exists: {target_path}")
            if target_path.exists() and controller_raw and lease_object:
                controller_path = Path(str(controller_raw)).expanduser().resolve()
                if not controller_path.is_dir():
                    raise RuntimeError(f"recorded Target path exists: {target_path}")
                manager = WorktreeManager(
                    root_dir=str(contract.get("target_worktree_root") or target_path.parent)
                )
                entry = manager._worktree_entry(controller_path, target_path)
                if entry is not None:
                    if state.get("status") != "RETAINED_FOR_REVIEW":
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    has_recorded_salvage = bool(
                        state.get("salvage_commit_sha") and state.get("salvage_ref")
                    )
                    target_dirty = bool(manager._status_bytes(target_path))
                    if not target_dirty and not has_recorded_salvage:
                        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target_path)
                        if target_head != lease_object.initial_head:
                            raise RuntimeError(
                                "recorded clean Target HEAD changed without durable snapshot"
                            )
                    self._require_integrated_replacement(task_id, superseded_by)
                    salvage = {
                        "salvage_commit_sha": state.get("salvage_commit_sha"),
                        "salvage_ref": state.get("salvage_ref"),
                        "salvage_only": state.get("salvage_only"),
                        "promotion_eligible": state.get("promotion_eligible"),
                    }
                    try:
                        if not salvage["salvage_commit_sha"] or not salvage["salvage_ref"]:
                            if target_dirty:
                                salvage = manager.create_salvage_snapshot(
                                    self._contract_from_state(state),
                                    lease_object,
                                    str(state.get("attempt_id") or ""),
                                )
                            else:
                                salvage = {}
                        elif salvage["salvage_only"] is not True or salvage["promotion_eligible"] is not False:
                            raise RuntimeError("recorded salvage metadata is invalid")
                        if salvage:
                            self._checkpoint(
                                task_id,
                                "RETAINED_FOR_REVIEW",
                                {
                                    **salvage,
                                    "promotion_status": "NOT_CREATED",
                                    "superseded_by": superseded_by,
                                    "cleanup_decision": "SALVAGED",
                                    "cleanup_blocker": None,
                                    "cleanup_performed": False,
                                    "cleanup_eligible": False,
                                    "state_retention_status": "TERMINAL",
                                },
                                attempt_id=state.get("attempt_id"),
                            )
                            cleanup = manager.cleanup_terminal_target(
                                self._contract_from_state(state),
                                lease_object,
                                salvage_commit=str(salvage["salvage_commit_sha"]),
                                salvage_ref=str(salvage["salvage_ref"]),
                            )
                        else:
                            cleanup = manager.cleanup_terminal_target(
                                self._contract_from_state(state),
                                lease_object,
                            )
                    except Exception as exc:
                        retained = self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": "CLEANUP_BLOCKED",
                                "cleanup_blocker": str(exc),
                                "cleanup_performed": False,
                                "cleanup_eligible": False,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        ) or state
                        return retained
                    if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                        return self._checkpoint(
                            task_id,
                            "RETAINED_FOR_REVIEW",
                            {
                                **salvage,
                                "promotion_status": "NOT_CREATED",
                                "superseded_by": superseded_by,
                                "cleanup_decision": cleanup.decision,
                                "cleanup_blocker": cleanup.blocker,
                                "cleanup_performed": cleanup.performed,
                                "cleanup_eligible": cleanup.eligible,
                                "state_retention_status": "TERMINAL",
                            },
                            attempt_id=state.get("attempt_id"),
                        ) or state
                    cleanup_values = {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        **salvage,
                    }
                else:
                    cleanup = manager.cleanup_terminal_target(
                        self._contract_from_state(state),
                        lease_object,
                    )
                    if cleanup.decision not in {"REMOVED", "ALREADY_REMOVED"}:
                        raise RuntimeError(f"recorded Target path exists: {target_path}")
                    cleanup_values = {
                        "cleanup_decision": cleanup.decision,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                    }

        return self._checkpoint(
            task_id,
            "SUPERSEDED",
            {
                "promotion_status": "NOT_CREATED",
                "final_disposition": "SUPERSEDED",
                "superseded_by": superseded_by,
                "terminal_status": "SUPERSEDED",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
                "merge_performed": False,
                "push_performed": False,
                **cleanup_values,
            },
            attempt_id=state.get("attempt_id"),
        ) or state

    close_without_candidate = close_task_without_candidate

    def close_retained_without_candidate(
        self,
        task_id: str,
        *,
        superseded_by: str,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")

        if state.get("status") != "RETAINED_FOR_REVIEW":
            raise RuntimeError(f"task {task_id} is not in RETAINED_FOR_REVIEW status")

        return self.close_task_without_candidate(task_id, superseded_by=superseded_by)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") in TERMINAL_STATUSES:
            return state
        pid = state.get("worker_pid")
        if pid and self._pid_alive(int(pid)):
            raise RuntimeError("active process must stop before cancellation cleanup")
        cancelled = self._checkpoint(task_id, "CANCELLED", {
            "promotion_status": "CANCELLED",
            "terminal_status": "CANCELLED",
            "final_disposition": "CANCELLED",
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
            "push_performed": False,
        }, attempt_id=state.get("attempt_id")) or state
        result = self.cleanup_tasks(task_id=task_id, dry_run=False)
        return self._read_state(task_id) or {**cancelled, "cleanup": result}

    def lifecycle_status(self) -> dict[str, Any]:
        states = [
            state
            for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists()
            if (state := self._read_state_snapshot(path.stem)) is not None
        ]
        invalid_states = [state for state in states if state.get("state_valid") is False]
        valid_states = [state for state in states if state.get("state_valid") is not False]

        def has_active_target(state: Mapping[str, Any]) -> bool:
            target_worktree = (state.get("lease") or {}).get("target_worktree")
            return bool(
                target_worktree
                and state.get("status") not in TERMINAL_STATUSES
                and Path(str(target_worktree)).is_dir()
            )

        return {
            "canonical_state_root": str(self.state_dir),
            "tasks": len(states),
            "active_tasks": sum(state.get("status") not in TERMINAL_STATUSES for state in valid_states),
            "active_targets": sum(has_active_target(state) for state in valid_states),
            "invalid_states": len(invalid_states),
            "blockers": [state["blocker"] for state in invalid_states],
        }

    def _cleanup_authority_blocker(
        self,
        state: Mapping[str, Any],
        contract: Any,
        lease: TargetWorktreeLease,
    ) -> Optional[str]:
        """Revalidate persisted acceptance, authorization, integration, and refs."""
        if state.get("status") != "INTEGRATED" or state.get("promotion_status") != "INTEGRATED":
            return "cleanup requires INTEGRATED lifecycle state"
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        raw_acceptance = state.get("external_acceptance") or binding.get("external_acceptance")
        raw_authorization = state.get("integration_authorization") or binding.get("integration_authorization")
        if raw_acceptance is None:
            return "external acceptance receipt is missing"
        if raw_authorization is None:
            return "Owner cleanup authorization is missing"
        try:
            acceptance = raw_acceptance if isinstance(raw_acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(raw_acceptance))
            authorization = raw_authorization if isinstance(raw_authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**{key: value for key, value in dict(raw_authorization).items() if key != "authorization_hash"})
        except (TypeError, ValueError) as exc:
            return f"cleanup authority binding invalid: {exc}"
        if acceptance.task_id != state.get("task_id") or acceptance.candidate_commit != packet.get("candidate_commit_sha"):
            return "external acceptance binding mismatch"
        if authorization.task_id != state.get("task_id") or authorization.candidate_commit != packet.get("candidate_commit_sha"):
            return "cleanup authorization candidate mismatch"
        if authorization.attempt_id not in {"", str(state.get("attempt_id") or "")}:
            return "cleanup authorization attempt mismatch"
        if authorization.acceptance_receipt_hash != acceptance.receipt_hash:
            return "cleanup authorization acceptance mismatch"
        if state.get("task_card_hash") and authorization.task_card_hash != state.get("task_card_hash"):
            return "cleanup authorization task card mismatch"
        if authorization.candidate_tree_sha != str(packet.get("candidate_tree_sha") or ""):
            return "cleanup authorization candidate tree mismatch"
        if authorization.candidate_state_hash != str(packet.get("candidate_state_hash") or ""):
            return "cleanup authorization candidate state mismatch"
        if "CLEANUP_OWNED_TARGET" not in authorization.action_set or not authorization.cleanup_requested:
            return "cleanup authorization does not include CLEANUP_OWNED_TARGET"
        grant = binding.get("approval_grant") if isinstance(binding.get("approval_grant"), Mapping) else None
        if not grant or not grant.get("consumed_at") or grant.get("approval_scope") != "ALLOW_ACTION_ONCE":
            return "one-shot Owner approval grant is missing or invalid"
        receipt = state.get("integration_receipt") if isinstance(state.get("integration_receipt"), Mapping) else None
        if not receipt or not receipt.get("verifier_passed") or not receipt.get("merge_performed") or not receipt.get("post_apply_verified"):
            return "post-apply integration receipt is missing or incomplete"
        if receipt.get("acceptance_receipt_hash") != acceptance.receipt_hash:
            return "integration receipt acceptance mismatch"
        if receipt.get("authorization_hash") != authorization.authorization_hash:
            return "integration receipt authorization mismatch"
        integration_sha = str(receipt.get("integration_commit_sha") or "")
        candidate_sha = str(packet.get("candidate_commit_sha") or "")
        if not integration_sha or integration_sha != str(state.get("integration_result_sha") or ""):
            return "integration receipt result binding is missing"
        controller = Path(contract.controller_repo_root).resolve()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        candidate_ref = str(state.get("candidate_ref") or "")
        if not candidate_ref:
            return "candidate durable ref is missing"
        if authorization.durable_ref != candidate_ref:
            return "cleanup authorization durable ref mismatch"
        if Path(authorization.canonical_root).resolve() != controller:
            return "cleanup authorization canonical root mismatch"
        if str(state.get("integration_branch") or authorization.canonical_branch) != authorization.canonical_branch:
            return "cleanup authorization integration branch mismatch"
        try:
            if manager._run_git(["rev-parse", f"{candidate_ref}^{{commit}}"], cwd=controller) != candidate_sha:
                return "candidate durable ref mismatch"
            if manager._run_git(["merge-base", "--is-ancestor", candidate_sha, integration_sha], cwd=controller) is None:
                return "candidate is not an ancestor of integration result"
            branch = str(state.get("integration_branch") or authorization.canonical_branch)
            if manager._run_git(["merge-base", "--is-ancestor", integration_sha, branch], cwd=controller) is None:
                return "canonical branch does not contain integration result"
        except RuntimeError as exc:
            return f"integration ancestry/ref verification failed: {exc}"
        if Path(lease.target_worktree).resolve() != Path(authorization.cleanup_target_path).resolve():
            return "cleanup target path binding mismatch"
        return None

    def _persisted_cleanup_contract(
        self, state: Mapping[str, Any]
    ) -> tuple[Optional[ArchitectTaskContract], Optional[str]]:
        """Rehydrate an integrated task from its immutable persisted contract.

        Cleanup must not re-run admission or rebuild a contract: those inputs
        may legitimately be stale by the time an integrated Target is removed.
        The persisted contract and every contract identity that is present in
        the terminal binding are still required to agree before any cleanup
        manager is constructed.
        """
        raw_contract = state.get("contract")
        if not isinstance(raw_contract, Mapping):
            return None, "persisted contract is missing or malformed"
        if raw_contract.get("schema") != "nexus.self_hosted_task_contract.v2":
            return None, "persisted contract schema is missing or invalid"
        expected_task_id = str(state.get("task_id") or "")
        if raw_contract.get("task_id") != expected_task_id:
            return None, "persisted contract task_id mismatch"

        persisted_hash = state.get("contract_hash")
        if not isinstance(persisted_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", persisted_hash):
            return None, "persisted contract state hash is missing or malformed"
        nested_hash = raw_contract.get("contract_hash")
        if nested_hash is not None and (
            not isinstance(nested_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", nested_hash)
        ):
            return None, "persisted contract nested hash is malformed"

        try:
            contract = ArchitectTaskContract.model_validate(
                {key: value for key, value in raw_contract.items() if key != "contract_hash"}
            )
        except (TypeError, ValueError) as exc:
            return None, f"persisted contract is invalid: {exc}"
        computed_hash = contract.contract_hash
        if persisted_hash != computed_hash:
            return None, "persisted contract state hash mismatch"
        if nested_hash is not None and nested_hash != computed_hash:
            return None, "persisted contract nested hash mismatch"

        packet = state.get("promotion_packet")
        if isinstance(packet, Mapping) and packet.get("contract_hash") is not None:
            packet_hash = packet.get("contract_hash")
            if not isinstance(packet_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", packet_hash):
                return None, "promotion packet contract hash is malformed"
            if packet_hash != computed_hash:
                return None, "promotion packet contract hash mismatch"

        binding = state.get("approved_binding")
        binding_grant = binding.get("approval_grant") if isinstance(binding, Mapping) else None
        grants = [state.get("integration_approval_grant"), binding_grant]
        for grant in grants:
            if not isinstance(grant, Mapping) or not grant.get("consumed_at"):
                continue
            approval_hash = grant.get("contract_hash")
            if not isinstance(approval_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", approval_hash):
                return None, "consumed approval contract hash is malformed"
            if approval_hash != computed_hash:
                return None, "consumed approval contract hash mismatch"
        return contract, None

    def cleanup_tasks(self, *, task_id: Optional[str] = None, dry_run: bool = True) -> dict[str, Any]:
        ids = [task_id] if task_id else [path.stem for path in sorted(self.state_dir.glob("*.json"))]
        decisions = []
        for item in ids:
            state = (self._read_state_snapshot(item) if dry_run else self._read_state(item)) or {}
            if not dry_run and not self._state_path(item).exists():
                _, archived = self._latest_archived_state(item)
                if archived and archived.get("status") == "INTEGRATED":
                    state = self._reactivate_archived_state(item, archived)
            if not state:
                decisions.append({"task_id": item, "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": "task state not found", "cleanup_performed": False})
                continue
            if state.get("status") == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
                decision = {
                    "task_id": item,
                    "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_POST_APPLY_FAILURE",
                    "cleanup_blocker": "post-apply verification failed after physical integration apply",
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "target_present_after": True,
                }
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            if state.get("status") == "INTEGRATION_FAILED_PRE_APPLY":
                decision = {
                    "task_id": item,
                    "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_PRE_APPLY_FAILURE",
                    "cleanup_blocker": "integration was not applied; retry integration before cleanup",
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "target_present_after": True,
                }
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            if state.get("status") == "RETAINED_FOR_REVIEW":
                worker_pid = state.get("worker_pid")
                child_pgid = state.get("worker_child_pgid")
                if ((worker_pid and self._pid_alive(int(worker_pid))) or
                        (child_pgid and self._pid_alive(int(child_pgid)))):
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_PROCESS",
                        "cleanup_blocker": "active process uses Target",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                if not state.get("lease") or not state.get("request"):
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                        "cleanup_blocker": "retained task lacks lease or request authority",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                contract = self.build_contract(state["request"])
                lease = TargetWorktreeLease(**state["lease"])
                manager = WorktreeManager(root_dir=contract.target_worktree_root)
                target = Path(lease.target_worktree).resolve()
                controller = Path(contract.controller_repo_root).resolve()
                attempt_id = str(state.get("attempt_id") or "")
                if not attempt_id:
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
                        "cleanup_blocker": "retained task lacks attempt identity",
                        "cleanup_performed": False, "cleanup_eligible": False,
                    })
                    continue
                if dry_run:
                    entry = manager._worktree_entry(controller, target)
                    if not target.exists() and entry is None:
                        planned = "ALREADY_REMOVED"
                    elif entry is None:
                        planned = "BLOCKED_BY_UNSAVED_CHANGES"
                    elif manager.process_checker(target):
                        planned = "BLOCKED_BY_PROCESS"
                    else:
                        dirty = bool(manager._status_bytes(target))
                        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
                        if dirty:
                            planned = "WOULD_SALVAGE_AND_REMOVE"
                        elif head != lease.initial_head:
                            planned = "WOULD_PROTECT_HEAD_AND_REMOVE"
                        else:
                            planned = "WOULD_REMOVE"
                    decisions.append({
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "cleanup_decision": planned,
                        "cleanup_blocker": None,
                        "cleanup_performed": False,
                        "cleanup_eligible": planned not in {
                            "BLOCKED_BY_PROCESS", "BLOCKED_BY_UNSAVED_CHANGES"
                        },
                    })
                    continue

                salvage_commit = state.get("salvage_commit_sha")
                salvage_ref = state.get("salvage_ref")
                salvage: dict[str, Any] = {}
                try:
                    entry = manager._worktree_entry(controller, target)
                    if not target.exists() and entry is None:
                        cleanup = manager.cleanup_terminal_target(contract, lease)
                    else:
                        if entry is None:
                            raise RuntimeError("retained Target is not a registered worktree")
                        if manager.process_checker(target):
                            raise RuntimeError("active process uses Target")
                        dirty = bool(manager._status_bytes(target))
                        head = manager._run_git(["rev-parse", "HEAD"], cwd=target)
                        deterministic_ref = manager.salvage_ref_for(item, attempt_id)
                        if salvage_commit or salvage_ref:
                            if (state.get("salvage_only") is not True or
                                    state.get("promotion_eligible") is not False or
                                    not salvage_commit or not salvage_ref):
                                raise RuntimeError("recorded salvage metadata is invalid")
                            protected = manager._run_git(
                                ["rev-parse", f"{salvage_ref}^{{commit}}"], cwd=controller
                            )
                            if protected != salvage_commit or head != salvage_commit:
                                raise RuntimeError("salvage ref is missing or mismatched")
                            salvage = {
                                "salvage_commit_sha": salvage_commit,
                                "salvage_ref": salvage_ref,
                                "salvage_only": True,
                                "promotion_eligible": False,
                            }
                        else:
                            try:
                                protected = manager._run_git(
                                    ["rev-parse", f"{deterministic_ref}^{{commit}}"],
                                    cwd=controller,
                                )
                            except RuntimeError:
                                protected = ""
                            if protected:
                                if protected != head:
                                    raise RuntimeError(
                                        "salvage ref already exists with different commit"
                                    )
                                salvage = {
                                    "salvage_commit_sha": protected,
                                    "salvage_ref": deterministic_ref,
                                    "salvage_only": True,
                                    "promotion_eligible": False,
                                }
                            elif dirty:
                                salvage = manager.create_salvage_snapshot(
                                    contract, lease, attempt_id
                                )
                            elif head != lease.initial_head:
                                salvage = manager.protect_salvage_head(
                                    contract, lease, attempt_id
                                )
                        cleanup = manager.cleanup_terminal_target(
                            contract,
                            lease,
                            salvage_commit=salvage.get("salvage_commit_sha"),
                            salvage_ref=salvage.get("salvage_ref"),
                        )
                    decision = {
                        "task_id": item,
                        "status": "RETAINED_FOR_REVIEW",
                        "promotion_status": "NOT_CREATED",
                        "cleanup_decision": cleanup.decision,
                        "cleanup_blocker": cleanup.blocker,
                        "cleanup_performed": cleanup.performed,
                        "cleanup_eligible": cleanup.eligible,
                        "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                        **salvage,
                    }
                except Exception as exc:
                    decision = {
                        "task_id": item, "status": "RETAINED_FOR_REVIEW",
                        "promotion_status": "NOT_CREATED",
                        "cleanup_decision": "CLEANUP_BLOCKED",
                        "cleanup_blocker": str(exc),
                        "cleanup_performed": False, "cleanup_eligible": False,
                        **salvage,
                    }
                decisions.append(decision)
                self._checkpoint(
                    item, "RETAINED_FOR_REVIEW", decision,
                    attempt_id=state.get("attempt_id"),
                )
                continue
            if state.get("status") not in TERMINAL_STATUSES and state.get("status") not in {"CANDIDATE_COMMITTED", "TARGET_CLEANED", "PENDING_HUMAN_APPROVAL"}:
                decisions.append({"task_id": item, "status": state.get("status"), "cleanup_decision": "BLOCKED_BY_PROCESS", "cleanup_blocker": "task is active", "cleanup_performed": False})
                continue
            if not state.get("lease"):
                decision = {"task_id": item, "status": state.get("status"), "cleanup_decision": "ALREADY_REMOVED", "cleanup_blocker": None, "cleanup_performed": False, "cleanup_eligible": True}
                decisions.append(decision)
                if not dry_run:
                    self._checkpoint(item, str(state.get("status")), decision, attempt_id=state.get("attempt_id"))
                continue
            if state.get("status") == "INTEGRATED":
                contract, persisted_contract_blocker = self._persisted_cleanup_contract(state)
                if persisted_contract_blocker:
                    decisions.append({
                        "task_id": item,
                        "status": state.get("status"),
                        "cleanup_decision": "BLOCKED_BY_AUTHORITY",
                        "cleanup_blocker": persisted_contract_blocker,
                        "cleanup_performed": False,
                        "cleanup_eligible": False,
                    })
                    continue
                assert contract is not None
            else:
                contract = self.build_contract(state["request"])
            lease = TargetWorktreeLease(**state["lease"])
            packet = state.get("promotion_packet") or {}
            binding = state.get("approved_binding") or {}
            authority_blocker = self._cleanup_authority_blocker(state, contract, lease)
            if authority_blocker:
                decisions.append({
                    "task_id": item,
                    "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_AUTHORITY",
                    "cleanup_blocker": authority_blocker,
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                })
                continue
            if state.get("promotion_status") in {"APPROVED", "INTEGRATED"} and any(
                binding.get(field) != packet.get(field)
                for field in (
                    "candidate_commit_sha", "candidate_tree_sha",
                    "candidate_state_hash", "verified_receipt_hash",
                )
            ):
                decisions.append({
                    "task_id": item, "status": state.get("status"),
                    "cleanup_decision": "BLOCKED_BY_MISSING_REF",
                    "cleanup_blocker": "approval binding mismatch",
                    "cleanup_performed": False, "cleanup_eligible": False,
                })
                continue
            cleanup = WorktreeManager(root_dir=contract.target_worktree_root).cleanup_terminal_target(
                contract,
                lease,
                candidate_commit=packet.get("candidate_commit_sha"),
                candidate_ref=state.get("candidate_ref"),
                dry_run=dry_run,
            )
            cleanup_receipt = asdict(cleanup)
            cleanup_receipt_hash = hashlib.sha256(
                json.dumps(
                    cleanup_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            decision = {
                "task_id": item,
                "status": state.get("status"),
                "cleanup_decision": cleanup.decision,
                "cleanup_blocker": cleanup.blocker,
                "cleanup_performed": cleanup.performed,
                "cleanup_eligible": cleanup.eligible,
                "cleanup_performed_at": _utc_now() if cleanup.performed else None,
                "cleanup_receipt": cleanup_receipt,
                "cleanup_receipt_hash": cleanup_receipt_hash,
            }
            cleanup_receipt["target_present_after"] = Path(lease.target_worktree).resolve().exists()
            cleanup_receipt_hash = hashlib.sha256(
                json.dumps(
                    cleanup_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            decision["cleanup_receipt"] = cleanup_receipt
            decision["cleanup_receipt_hash"] = cleanup_receipt_hash
            decision["target_present_after"] = cleanup_receipt["target_present_after"]
            decisions.append(decision)
            if not dry_run:
                terminal = "RETAINED_FOR_REVIEW" if cleanup.decision == "BLOCKED_BY_UNSAVED_CHANGES" else str(state.get("status"))
                self._checkpoint(item, terminal, decision, attempt_id=state.get("attempt_id"))
        return {"dry_run": dry_run, "decisions": decisions}

    def archive_states(self, *, dry_run: bool = True) -> dict[str, Any]:
        archive_root = self._archive_root()
        entries = []
        for path in sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []:
            payload = path.read_bytes()
            state = json.loads(payload)
            if state.get("status") not in {"FINAL_BLOCK", "INTEGRATED", "INTEGRATED_AND_CLEANED", "REJECTED", "SUPERSEDED", "CANCELLED"}:
                continue
            if state.get("status") == "INTEGRATED" and state.get("cleanup_status") not in {None, "CLEANED"}:
                continue
            digest = hashlib.sha256(payload).hexdigest()
            destination = archive_root / path.name
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                attempt_id = str(state.get("attempt_id") or "unknown")
                destination = archive_root / f"{path.stem}--attempt-{attempt_id}.json"
            entries.append({
                "task_id": path.stem,
                "terminal_status": state.get("terminal_status") or state.get("status"),
                "candidate_commit": (state.get("promotion_packet") or {}).get("candidate_commit_sha"),
                "source": str(path),
                "archive_location": str(destination),
                "receipt_hash": digest,
                "archive_time": state.get("updated_at"),
            })
        manifest_bytes = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = archive_root / f"manifest-{manifest_hash}.json"
        if not dry_run and entries:
            archive_root.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                source = Path(entry["source"])
                destination = Path(entry["archive_location"])
                if destination.exists():
                    if hashlib.sha256(destination.read_bytes()).hexdigest() != entry["receipt_hash"]:
                        raise RuntimeError(f"archive receipt hash mismatch: {destination}")
                    source.unlink(missing_ok=True)
                else:
                    source.replace(destination)
                if hashlib.sha256(destination.read_bytes()).hexdigest() != entry["receipt_hash"]:
                    raise RuntimeError(f"archive receipt verification failed: {destination}")
            manifest_payload = {
                "schema": "nexus.self_hosted_state_archive_manifest.v1",
                "manifest_hash": manifest_hash,
                "entries": entries,
            }
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=archive_root,
                prefix=".manifest.", suffix=".tmp", delete=False,
            ) as handle:
                json.dump(manifest_payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                temporary = Path(handle.name)
            temporary.replace(manifest_path)
        return {"dry_run": dry_run, "entries": entries, "manifest_hash": manifest_hash, "manifest_path": str(manifest_path)}

    def verify_task(self, task_id: str) -> dict[str, Any]:
        """Read-only verification of a self-hosted task.

        Proves:
        - verifier commands only from durable task contract/state
        - reuses CandidateVerifier._run_verifiers() for command execution
        - provider_calls == 0 (deterministic commands only)
        - full state/contract/attempt binding checked
        - durable state digest verified before/after
        - integration result is verifiable ancestor when present
        - Target, lease, candidate, receipt or durable binding missing -> fail closed
        - verify must not commit, cleanup, approve, integrate, push, or modify state
        - repeated verify on same immutable state -> consistent verdict
        """
        # --- Phase 1: Pre-read durable state ---
        state_before = self._read_state_snapshot(task_id)
        if state_before is None:
            return {
                "task_id": task_id,
                "verdict": "STATE_MISSING",
                "verified": False,
                "failure_reasons": ["state_not_found"],
                "provider_calls": 0,
            }

        attempt_id = state_before.get("attempt_id")
        contract_hash = state_before.get("contract_hash")
        status = state_before.get("status")

        # --- Phase 2: State integrity + full binding check ---
        failures: list[str] = []

        # Compute pre-verification state digest
        state_digest_before = hashlib.sha256(
            json.dumps(state_before, sort_keys=True, default=str).encode()
        ).hexdigest()

        # State deletion/replacement check
        state_mid = self._read_state_snapshot(task_id)
        if state_mid is None:
            return {
                "task_id": task_id,
                "verdict": "STATE_DELETED",
                "verified": False,
                "failure_reasons": ["state_deleted_between_reads"],
                "provider_calls": 0,
            }

        # Hash drift check
        if state_mid.get("contract_hash") != contract_hash:
            failures.append("contract_hash_drift")

        # Attempt drift check
        if state_mid.get("attempt_id") != attempt_id:
            failures.append("attempt_drift")

        # --- Phase 3: Contract, lease, candidate binding validation (fail-closed) ---
        contract_data = state_mid.get("contract")
        if not contract_data:
            failures.append("contract_missing")
        lease_data = state_mid.get("lease")
        if not lease_data:
            failures.append("lease_missing")

        candidate_commit = state_mid.get("candidate_commit_sha")
        candidate_ref = state_mid.get("candidate_ref")
        promotion_packet = state_mid.get("promotion_packet") or {}

        # If candidate state exists, binding must be complete
        if candidate_commit and not candidate_ref:
            failures.append("candidate_ref_missing")
        if candidate_commit and not promotion_packet.get("candidate_state_hash"):
            failures.append("candidate_state_hash_missing")

        # --- Phase 4: Target or durable post-cleanup Candidate validation ---
        target_worktree = (
            state_mid.get("target_worktree")
            or (lease_data.get("target_worktree") if lease_data else None)
            or (contract_data.get("target_repo_root") if contract_data else None)
        )
        verification_mode = "target"
        durable_candidate_mode = False
        verified_receipt = state_mid.get("verified_receipt") or {}
        cleanup_decision = state_mid.get("cleanup_decision")
        target_integrity_before = "SKIPPED"
        target_integrity_after = "SKIPPED"
        target_integrity_error_before: Optional[str] = None
        target_integrity_error_after: Optional[str] = None

        if not target_worktree:
            failures.append("target_worktree_missing")
        else:
            target_path = Path(target_worktree)
            if (
                cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}
                and candidate_commit
                and candidate_ref
                and promotion_packet
                and verified_receipt
            ):
                verification_mode = "durable_candidate_receipt"
                durable_candidate_mode = True
                target_integrity_before = "DURABLE_CANDIDATE"
                target_integrity_after = "DURABLE_CANDIDATE"
                import re

                candidate_tree = state_mid.get("candidate_tree_sha") or promotion_packet.get("candidate_tree_sha")
                candidate_state_hash = state_mid.get("candidate_state_hash") or promotion_packet.get("candidate_state_hash")
                verified_receipt_hash = state_mid.get("verified_receipt_hash") or promotion_packet.get("verified_receipt_hash")
                controller_root = (
                    state_mid.get("controller_worktree")
                    or (contract_data.get("controller_repo_root") if contract_data else None)
                )
                candidate_ref_pattern = re.compile(
                    rf"refs/nexus-(?:candidates|candidate-commits)/{re.escape(task_id)}/[0-9a-f]{{40}}"
                )

                if not re.fullmatch(r"[0-9a-f]{40}", str(candidate_commit)):
                    failures.append("candidate_commit_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{40}", str(candidate_tree or "")):
                    failures.append("candidate_tree_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{64}", str(candidate_state_hash or "")):
                    failures.append("candidate_state_hash_invalid_format")
                if not re.fullmatch(r"[0-9a-f]{64}", str(verified_receipt_hash or "")):
                    failures.append("verified_receipt_hash_invalid_format")
                if not candidate_ref_pattern.fullmatch(str(candidate_ref)):
                    failures.append("candidate_ref_namespace_invalid")
                if not controller_root or not Path(controller_root).is_dir():
                    failures.append("controller_repo_unavailable")
                else:
                    try:
                        resolved_ref = subprocess.run(
                            ["git", "rev-parse", "--verify", str(candidate_ref)],
                            cwd=controller_root,
                            capture_output=True,
                            text=True,
                            timeout=10.0,
                        )
                        if resolved_ref.returncode != 0:
                            failures.append("candidate_ref_unresolved")
                        elif resolved_ref.stdout.strip() != candidate_commit:
                            failures.append("candidate_ref_commit_mismatch")

                        resolved_tree = subprocess.run(
                            ["git", "rev-parse", "--verify", f"{candidate_ref}^{{tree}}"],
                            cwd=controller_root,
                            capture_output=True,
                            text=True,
                            timeout=10.0,
                        )
                        if resolved_tree.returncode != 0:
                            failures.append("candidate_ref_tree_unresolved")
                        elif resolved_tree.stdout.strip() != candidate_tree:
                            failures.append("candidate_ref_tree_mismatch")
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        failures.append(f"candidate_ref_verification_error:{exc}")

                for field, expected in (
                    ("task_id", task_id),
                    ("contract_hash", contract_hash),
                    ("lease_id", lease_data.get("lease_id") if lease_data else None),
                    ("candidate_state_hash", candidate_state_hash),
                ):
                    if verified_receipt.get(field) != expected:
                        failures.append(f"verified_receipt_{field}_mismatch")

                if not verified_receipt.get("verified"):
                    failures.append("verified_receipt_not_verified")
                if not verified_receipt.get("candidate_commit_allowed"):
                    failures.append("verified_receipt_commit_not_allowed")
                if verified_receipt.get("public_claim_allowed") is not False:
                    failures.append("verified_receipt_public_claim_boundary_invalid")
                if verified_receipt.get("production_ready") is not False:
                    failures.append("verified_receipt_production_boundary_invalid")
                if verified_receipt.get("merge_performed") is not False:
                    failures.append("verified_receipt_merge_boundary_invalid")

                canonical_receipt = json.dumps(
                    verified_receipt,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
                actual_receipt_hash = hashlib.sha256(canonical_receipt).hexdigest()
                if actual_receipt_hash != verified_receipt_hash:
                    failures.append("verified_receipt_hash_mismatch")

                for field in (
                    "task_id",
                    "contract_hash",
                    "controller_revision",
                    "target_base_revision",
                    "candidate_commit_sha",
                    "candidate_tree_sha",
                    "candidate_state_hash",
                    "verified_receipt_hash",
                ):
                    expected = {
                        "task_id": task_id,
                        "contract_hash": contract_hash,
                        "controller_revision": contract_data.get("controller_revision") if contract_data else None,
                        "target_base_revision": contract_data.get("target_base_revision") if contract_data else None,
                        "candidate_commit_sha": candidate_commit,
                        "candidate_tree_sha": candidate_tree,
                        "candidate_state_hash": candidate_state_hash,
                        "verified_receipt_hash": verified_receipt_hash,
                    }[field]
                    if promotion_packet.get(field) != expected:
                        failures.append(f"promotion_packet_{field}_mismatch")
            elif cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}:
                verification_mode = "durable_candidate_receipt"
                failures.append("durable_candidate_binding_missing")
            elif target_path.exists():
                if not target_path.is_dir():
                    failures.append("target_not_directory")
                else:
                    try:
                        list(target_path.iterdir())
                    except PermissionError:
                        failures.append("target_unreadable")
                    target_integrity_before, target_integrity_error_before = self._snapshot_target_integrity(target_path)
                    if target_integrity_error_before:
                        failures.append(
                            f"target_integrity_before_verification:{target_integrity_error_before}"
                        )
            else:
                failures.append("target_missing")
                target_integrity_before, target_integrity_error_before = self._snapshot_target_integrity(target_path)

        # --- Phase 5: Integration SHA validation (actual ancestor check) ---
        integration_result_sha = state_mid.get("integration_result_sha")
        if integration_result_sha:
            import re
            if not re.fullmatch(r"[0-9a-f]{40}", integration_result_sha):
                failures.append("integration_sha_invalid_format")
            else:
                controller_root = (
                    state_mid.get("controller_worktree")
                    or (contract_data.get("controller_repo_root") if contract_data else None)
                )
                controller_rev = (
                    state_mid.get("controller_revision")
                    or (contract_data.get("controller_revision") if contract_data else None)
                )
                if controller_root and controller_rev:
                    try:
                        anc_result = subprocess.run(
                            [
                                "git", "-c", "core.hooksPath=/dev/null",
                                "merge-base", "--is-ancestor",
                                integration_result_sha, controller_rev,
                            ],
                            cwd=controller_root,
                            capture_output=True,
                            timeout=10.0,
                        )
                        if anc_result.returncode != 0:
                            failures.append("integration_ancestry_failed")
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        failures.append(f"integration_ancestry_error:{exc}")

        # --- Phase 6: Verifier command execution via CandidateVerifier._run_verifiers ---
        verifier_commands = (
            contract_data.get("verifier_commands") if contract_data else []
        ) or []
        verifier_evidence: list[dict[str, Any]] = []
        verifier_commands_executed: list[str] = []

        if durable_candidate_mode:
            verifier_evidence = list(verified_receipt.get("verifier_evidence") or [])
        elif (
            target_worktree
            and Path(target_worktree).is_dir()
            and verifier_commands
            and target_integrity_error_before is None
        ):
            class _MinimalContract:
                pass
            _min = _MinimalContract()
            _min.verifier_commands = verifier_commands

            try:
                passed, evidence_tuple, ver_failures = CandidateVerifier._run_verifiers(
                    _min, target_worktree,
                )
                for ev in evidence_tuple:
                    verifier_evidence.append({
                        "command": ev.command,
                        "status": ev.status,
                        "exit_code": ev.exit_code,
                        "stdout_sha256": ev.stdout_sha256,
                        "stderr_sha256": ev.stderr_sha256,
                        "wall_time_ms": ev.wall_time_ms,
                        "executable_identity": ev.executable_identity,
                        "timed_out": ev.timed_out,
                    })
                    verifier_commands_executed.append(ev.command)
                failures.extend(ver_failures)
            except Exception as exc:
                failures.append(f"verifier_runner_error:{exc}")

        if not durable_candidate_mode and target_worktree and target_integrity_before != "SKIPPED":
            target_integrity_after, target_integrity_error_after = self._snapshot_target_integrity(
                Path(target_worktree)
            )
            if target_integrity_error_after:
                failures.append(
                    f"target_integrity_after_verification:{target_integrity_error_after}"
                )
            if target_integrity_before != target_integrity_after:
                failures.append("target_digest_drift_during_verification")

        # --- Phase 7: Post-read state consistency + digest comparison ---
        state_after = self._read_state_snapshot(task_id)
        if state_after is None:
            failures.append("state_deleted_after_verification")
        else:
            if state_after.get("contract_hash") != contract_hash:
                failures.append("contract_hash_drift_after_verification")
            elif state_after.get("attempt_id") != attempt_id:
                failures.append("attempt_drift_after_verification")

            # Full state digest comparison
            state_digest_after = hashlib.sha256(
                json.dumps(state_after, sort_keys=True, default=str).encode()
            ).hexdigest()
            if state_digest_before != state_digest_after:
                failures.append("state_digest_drift_during_verification")

        verified = not failures
        action_state = self._task_action_envelope(state_after or state_before)
        return {
            "task_id": task_id,
            "verdict": "VERIFIED" if verified else "FAILED",
            "verified": verified,
            "failure_reasons": failures,
            "provider_calls": 0,
            "verification_mode": verification_mode,
            "verifier_commands_executed": verifier_commands_executed,
            "verifier_evidence": verifier_evidence,
            "status": status,
            "contract_hash": contract_hash,
            "attempt_id": attempt_id,
            "state_digest_before": state_digest_before,
            "state_intact": state_after is not None and state_after.get("contract_hash") == contract_hash,
            "target_integrity_before": target_integrity_before,
            "target_integrity_after": target_integrity_after,
            "target_integrity_error": target_integrity_error_before or target_integrity_error_after,
            "task_action": action_state,
            "action_state": action_state.get("action_state"),
            "attention_required": action_state.get("attention_required"),
            "next_action": action_state.get("next_action"),
            "recommended_tool": action_state.get("recommended_tool"),
        }

    def approve_promotion(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
        approval_context: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        if self._custom_runner is not None:
            raise RuntimeError("CUSTOM_RUNNER_PRODUCTION_CLAIM_FORBIDDEN")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        request = state.get("request") or {}
        if self.ephemeral and (
            request.get("task_card_required") or request.get("lifecycle_identity_required")
        ):
            raise RuntimeError("EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot be approved")
        identity = resolve_contract_identity(
            state,
            expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )
        packet = state.get("promotion_packet") or {}
        expected = {
            "candidate_commit_sha": candidate_commit_sha,
            "candidate_tree_sha": candidate_tree_sha,
            "candidate_state_hash": candidate_state_hash,
            "verified_receipt_hash": verified_receipt_hash,
        }

        valid = bool(packet) and not any(packet.get(k) != v for k, v in expected.items())
        status = "APPROVED" if valid else "APPROVAL_INVALIDATED"
        if approval_context is None:
            # Models and callers cannot mint approval; every surface needs a grant.
            raise RuntimeError("APPROVAL_GRANT_REQUIRED: candidate approval requires an approval grant")
        grant = dict(approval_context or {}) if approval_context is not None else None
        if grant is not None and (
            grant.get("claim_ceiling") == "CLAIM_PROTOCOL_CANDIDATE_PR_ONLY"
            or grant.get("role") in {"bounded_code_candidate", "implementer"}
            or "work_claim" in grant
        ):
            raise RuntimeError("IMPLEMENTER_CLAIM_CANNOT_AUTHORIZE_APPROVAL")
        # Every surface needs a grant naming its approver and bound to this task,
        # attempt and action; a bare schema marker is not authority.
        require_bound_approval_grant(
            grant,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=identity["task_card_hash"],
            contract_kind=identity["contract_kind"],
            contract_hash=identity["contract_hash"],
            owner_inline_contract=identity["owner_inline_contract"],
        )
        architecture_approval = grant.get("architecture_approval") if isinstance(grant, Mapping) else None
        receipt = state.get("verified_receipt") if isinstance(state.get("verified_receipt"), Mapping) else {}
        authority_required = bool(packet.get("authority_change_required") or receipt.get("authority_change_required"))
        authority_hash = str(packet.get("authority_findings_sha256") or receipt.get("authority_findings_sha256") or "")
        validate_architecture_approval(
            architecture_approval,
            required=authority_required,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            authority_findings_sha256=authority_hash,
        )
        external_acceptance: dict[str, Any] | None = None
        integration_authorization: dict[str, Any] | None = None
        if grant is not None:
            if str(grant.get("schema") or "") != "nexus.approval.v2":
                raise RuntimeError("APPROVAL_LEGACY_BINDING_INVALIDATED")
            if grant.get("consumed_at"):
                raise RuntimeError("APPROVAL_ALREADY_CONSUMED")
            if str(grant.get("approval_scope") or "ALLOW_ACTION_ONCE") != "ALLOW_ACTION_ONCE":
                raise RuntimeError("APPROVAL_SCOPE_UNSUPPORTED")
            raw_acceptance = grant.get("external_acceptance")
            raw_authorization = grant.get("integration_authorization")
            if (raw_acceptance is None) != (raw_authorization is None):
                raise RuntimeError("AUTHORIZED_CLOSURE_BINDING_INCOMPLETE")
            if raw_acceptance is not None and raw_authorization is not None:
                acceptance_obj = raw_acceptance if isinstance(raw_acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(raw_acceptance))
                authorization_obj = raw_authorization if isinstance(raw_authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**{key: value for key, value in dict(raw_authorization).items() if key != "authorization_hash"})
                if acceptance_obj.task_id != task_id or acceptance_obj.candidate_commit != candidate_commit_sha:
                    raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
                if authorization_obj.task_id != task_id or authorization_obj.candidate_commit != candidate_commit_sha:
                    raise RuntimeError("INTEGRATION_AUTHORIZATION_BINDING_MISMATCH")
                expected_authorization = {
                    "attempt_id": str(state.get("attempt_id") or ""),
                    "task_card_hash": str(state.get("task_card_hash") or grant.get("task_card_hash") or ""),
                    "candidate_tree_sha": candidate_tree_sha,
                    "candidate_state_hash": candidate_state_hash,
                    "candidate_receipt_hash": verified_receipt_hash,
                }
                authorization_values = {
                    "attempt_id": authorization_obj.attempt_id,
                    "task_card_hash": authorization_obj.task_card_hash,
                    "candidate_tree_sha": authorization_obj.candidate_tree_sha,
                    "candidate_state_hash": authorization_obj.candidate_state_hash,
                    "candidate_receipt_hash": authorization_obj.candidate_receipt_hash,
                }
                authorization_drift = [
                    key for key, expected_value in expected_authorization.items()
                    if str(authorization_values[key]) != str(expected_value)
                ]
                if authorization_drift:
                    raise RuntimeError(
                        "INTEGRATION_AUTHORIZATION_BINDING_MISMATCH: "
                        + ", ".join(authorization_drift)
                    )
                if authorization_obj.acceptance_receipt_hash != acceptance_obj.receipt_hash:
                    raise RuntimeError("INTEGRATION_AUTHORIZATION_ACCEPTANCE_MISMATCH")
                external_acceptance = acceptance_obj.to_dict()
                integration_authorization = authorization_obj.to_dict()
                integration_authorization["authorization_hash"] = authorization_obj.authorization_hash
        if valid:
            _require_verified_receipt_binding(state.get("verified_receipt"), packet)
        now = _utc_now()
        duplicate = False
        initial_status = state.get("status")
        initial_promotion_status = state.get("promotion_status")
        service_contract_hash = str(state.get("contract_hash") or "")
        packet_snapshot = json.dumps(
            _jsonable(packet), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        receipt_snapshot = json.dumps(
            _jsonable(receipt), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

        def mutate(current: dict[str, Any]) -> None:
            nonlocal duplicate
            if current.get("attempt_id") != state.get("attempt_id"):
                raise RuntimeError("task attempt ownership changed")
            current_identity = resolve_contract_identity(
                current,
                expected_task_id=task_id,
                expected_head=str(current.get("controller_revision") or ""),
            )
            current_packet = (
                current.get("promotion_packet")
                if isinstance(current.get("promotion_packet"), Mapping)
                else {}
            )
            current_receipt = (
                current.get("verified_receipt")
                if isinstance(current.get("verified_receipt"), Mapping)
                else {}
            )
            if (
                current.get("status") != initial_status
                or current.get("promotion_status") != initial_promotion_status
                or str(current.get("contract_hash") or "") != service_contract_hash
                or current_identity != identity
                or json.dumps(
                    _jsonable(current_packet),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                != packet_snapshot
                or json.dumps(
                    _jsonable(current_receipt),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                != receipt_snapshot
            ):
                raise RuntimeError("APPROVAL_BINDING_CONCURRENCY_DRIFT")
            existing = current.get("approved_binding") if isinstance(current.get("approved_binding"), Mapping) else {}
            existing_grant = existing.get("approval_grant") if isinstance(existing.get("approval_grant"), Mapping) else None
            if grant is not None and current.get("promotion_status") == "APPROVED" and existing_grant:
                same_request = (
                    str(existing_grant.get("approval_id")) == str(grant.get("approval_id"))
                    and all(existing.get(key) == value for key, value in expected.items())
                    and all(existing_grant.get(key) == grant.get(key) for key in ("contract_kind", "contract_hash", "task_card_hash"))
                )
                if same_request:
                    duplicate = True
                    return
                raise RuntimeError("APPROVAL_ALREADY_CONSUMED")
            consumed = dict(grant) if valid and grant is not None else None
            if consumed is not None:
                consumed["approval_scope"] = "ALLOW_ACTION_ONCE"
                consumed["consumed_at"] = now
                if isinstance(consumed.get("architecture_approval"), Mapping):
                    nested = dict(consumed["architecture_approval"])
                    nested["consumed_at"] = now
                    consumed["architecture_approval"] = nested
            current.update({
                "status": status,
                "promotion_status": status,
                "candidate_status": status,
                "approved_binding": ({
                    **expected,
                    "approval_grant": consumed,
                    "external_acceptance": external_acceptance,
                    "integration_authorization": integration_authorization,
                    "architecture_approval": (consumed or {}).get("architecture_approval") if consumed is not None else architecture_approval,
                } if valid else None),
                "external_acceptance": external_acceptance,
                "integration_authorization": integration_authorization,
                "approval_error": None if valid else "promotion binding does not match candidate packet",
                "merge_performed": False,
                "push_performed": False,
                "updated_at": now,
            })
            current.setdefault("status_history", []).append({"status": status, "at": now})

        result = self._mutate_state(task_id, mutate) or state
        if duplicate:
            result = dict(result)
            result["duplicate"] = True
        return result

    def owner_finish(
        self,
        task_id: str,
        *,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        candidate_state_hash: str,
        verified_receipt_hash: str,
        integration_branch: str = "nexus/integration/main",
        approval_context: Optional[Mapping[str, Any]] = None,
        external_acceptance: Optional[Mapping[str, Any]] = None,
        integration_authorization: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Owner-only terminal finish: approve, integrate, cleanup/retain, then archive."""
        if external_acceptance is None or integration_authorization is None:
            raise RuntimeError("owner finish requires external acceptance and Owner authorization")
        existing = self._read_state(task_id)
        if existing and existing.get("finalization_receipt") and existing.get("status") in {
            "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED",
        }:
            return {
                **existing,
                "duplicate": True,
                "owner_finish": {
                    "approval_status": "ALREADY_FINALIZED",
                    "integration_status": existing.get("integration_status"),
                    "cleanup_status": existing.get("cleanup_status"),
                    "archive": {"dry_run": False, "entries": []},
                },
            }
        context = dict(approval_context or {})
        context["external_acceptance"] = dict(external_acceptance)
        context["integration_authorization"] = dict(integration_authorization)
        approved = self.approve_promotion(
            task_id,
            candidate_commit_sha=candidate_commit_sha,
            candidate_tree_sha=candidate_tree_sha,
            candidate_state_hash=candidate_state_hash,
            verified_receipt_hash=verified_receipt_hash,
            approval_context=context,
        )
        if approved.get("status") != "APPROVED" or approved.get("promotion_status") != "APPROVED":
            raise RuntimeError("owner finish requires an exact approved candidate binding")
        integrated = self.integrate_approved(task_id, integration_branch=integration_branch)
        authorization = dict(integration_authorization)
        state_after_integration = self._read_state(task_id) or integrated
        lease_target = str((state_after_integration.get("lease") or {}).get("target_worktree") or "")
        requested_target = str(authorization.get("cleanup_target_path") or lease_target)
        target_path = Path(requested_target).expanduser().resolve() if requested_target else None
        temp_roots = _temporary_state_roots()
        controller_root = Path(str((state_after_integration.get("contract") or {}).get("controller_repo_root") or "")).expanduser().resolve()
        cleanup_allowed = bool(
            self.ephemeral
            and authorization.get("cleanup_requested") is True
            and "CLEANUP_OWNED_TARGET" in (authorization.get("action_set") or [])
            and target_path is not None
            and any(target_path == root or root in target_path.parents for root in temp_roots)
            and target_path != controller_root
        )
        if cleanup_allowed:
            cleanup_result = self.cleanup_tasks(task_id=task_id, dry_run=False)
        else:
            cleanup_result = {
                "dry_run": False,
                "decisions": [{
                    "task_id": task_id,
                    "cleanup_decision": "RETAINED_OUTSIDE_EPHEMERAL_SCOPE",
                    "cleanup_blocker": "live or non-ephemeral cleanup authority is disabled",
                    "cleanup_performed": False,
                    "cleanup_eligible": False,
                    "target_present_after": True,
                }],
            }
        decisions = [d for d in cleanup_result.get("decisions", []) if d.get("task_id", task_id) == task_id]
        decision = decisions[0] if decisions else {
            "cleanup_decision": "CLEANUP_BLOCKED",
            "cleanup_blocker": "cleanup authority returned no decision",
            "cleanup_performed": False,
            "cleanup_eligible": False,
            "target_present_after": True,
        }
        cleanup_receipt = dict(decision.get("cleanup_receipt") or {})
        cleanup_receipt.setdefault("schema", "nexus.target_cleanup_receipt.v1")
        cleanup_receipt.setdefault("task_id", task_id)
        cleanup_receipt.setdefault("decision", decision.get("cleanup_decision"))
        cleanup_receipt.setdefault("blocker", decision.get("cleanup_blocker"))
        cleanup_receipt.setdefault("performed", bool(decision.get("cleanup_performed")))
        cleanup_receipt.setdefault("eligible", bool(decision.get("cleanup_eligible")))
        cleanup_receipt.setdefault(
            "target_present_after",
            bool(decision.get("target_present_after", decision.get("cleanup_decision") != "ALREADY_REMOVED")),
        )
        cleanup_receipt_hash = hashlib.sha256(json.dumps(cleanup_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        cleaned = (
            not bool(cleanup_receipt.get("target_present_after"))
            and (bool(cleanup_receipt.get("performed")) or cleanup_receipt.get("decision") == "ALREADY_REMOVED")
        )
        final_status = "INTEGRATED_AND_CLEANED" if cleaned else "INTEGRATED_TARGET_RETAINED"
        finalization_status = "CLEANED" if cleaned else "RETAINED"
        retention_reason = None if cleaned else str(cleanup_receipt.get("blocker") or cleanup_receipt.get("decision") or "cleanup was not performed")
        integration_receipt = integrated.get("integration_receipt") or {}
        finalization = {
            "schema": "nexus.task_finalization_receipt.v1",
            "identity": {"task_id": task_id, "campaign_id": (state_after_integration.get("request") or {}).get("campaign_id"), "attempt_id": state_after_integration.get("attempt_id"), "task_card_hash": state_after_integration.get("task_card_hash")},
            "candidate": {"commit_sha": candidate_commit_sha, "tree_sha": candidate_tree_sha, "state_hash": candidate_state_hash, "verified_receipt_hash": verified_receipt_hash},
            "acceptance": {"receipt_hash": authorization.get("acceptance_receipt_hash") or dict(external_acceptance).get("receipt_hash"), "reviewer_id": dict(external_acceptance).get("reviewer_id")},
            "authorization": {"authorization_hash": authorization.get("authorization_hash"), "approval_id": ((state_after_integration.get("approved_binding") or {}).get("approval_grant") or {}).get("approval_id"), "consumed_at": ((state_after_integration.get("approved_binding") or {}).get("approval_grant") or {}).get("consumed_at"), "action_set": list(authorization.get("action_set") or [])},
            "integration": {"status": "INTEGRATED", "branch": integrated.get("integration_branch") or integration_branch, "head_before": integrated.get("integration_base_sha"), "staging_commit": integration_receipt.get("staging_commit_sha"), "head_after": integrated.get("integration_result_sha"), "candidate_is_ancestor": True, "merge_performed": bool(integrated.get("merge_performed", True)), "staging_verified": bool(integration_receipt.get("staging_verified", True)), "post_apply_verified": bool(integration_receipt.get("post_apply_verified", True)), "receipt_hash": hashlib.sha256(json.dumps(integration_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(), "failure_reason": None},
            "cleanup": {"status": finalization_status, "target_id": authorization.get("cleanup_target_id"), "target_path": requested_target, "target_present_after": bool(cleanup_receipt.get("target_present_after")), "performed": bool(cleanup_receipt.get("performed")), "eligible": bool(cleanup_receipt.get("eligible")), "blocker": cleanup_receipt.get("blocker"), "receipt_hash": cleanup_receipt_hash},
            "terminal": {"final_status": final_status, "retention_reason": retention_reason, "next_action": "none" if cleaned else "retry_cleanup", "archive_eligible": cleaned},
            "created_at": _utc_now(),
        }
        finalization["receipt_hash"] = hashlib.sha256(json.dumps(finalization, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        values = {"status": final_status, "promotion_status": "INTEGRATED", "candidate_status": "INTEGRATED", "integration_status": "INTEGRATED", "cleanup_status": finalization_status, "target_present": bool(cleanup_receipt.get("target_present_after")), "cleanup_receipt": cleanup_receipt, "cleanup_receipt_hash": cleanup_receipt_hash, "finalization_receipt": finalization, "retention_reason": retention_reason, "next_action": "none" if cleaned else "retry_cleanup", "terminal_status": final_status, "final_disposition": final_status, "archive_eligible": cleaned, "state_retention_status": "TERMINAL" if cleaned else "ACTIONABLE"}
        persisted = self._checkpoint(task_id, final_status, values, attempt_id=state_after_integration.get("attempt_id"))
        if persisted is None:
            persisted = dict(state_after_integration)
            persisted.update(values)
            persisted["task_id"] = task_id
            self._write_state(task_id, persisted)
        archive = {"dry_run": False, "entries": []}
        if cleaned:
            archive = self.archive_states(dry_run=False)
        fresh = self._read_state(task_id) or persisted
        return {**fresh, "duplicate": False, "owner_finish": {"approval_status": "APPROVED", "integration_status": "INTEGRATED", "cleanup_status": finalization_status, "archive": archive}}

    def recover_verified_uncommitted_candidate(self, task_id: str) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        
        status = state.get("status")
        if status not in {"RETAINED_FOR_REVIEW", "FINAL_BLOCK"}:
            raise RuntimeError(f"task status '{status}' is not eligible for uncommitted recovery; status must be RETAINED_FOR_REVIEW or FINAL_BLOCK")

        if _fail_to_pass_blocked(state):
            raise RuntimeError("FAIL_TO_PASS_GATE_BLOCKED: candidate failed the fail-to-pass gate")

        verified_receipt = state.get("verified_receipt") or {}
        if not verified_receipt.get("verified"):
            raise RuntimeError("candidate must be verified before recovery")

        attempt_res = state.get("attempt_resolution") or {}
        if attempt_res.get("verdict") != "PROVEN":
            raise RuntimeError("attempt_resolution verdict must be PROVEN")

        execution = state.get("execution") or {}
        if execution.get("outcome") != "EXECUTION_COMPLETED":
            raise RuntimeError("execution outcome must be EXECUTION_COMPLETED")

        if not verified_receipt.get("verifier_gate_passed"):
            raise RuntimeError("verifier_gate_passed must be True")
        if not verified_receipt.get("controller_gate_passed"):
            raise RuntimeError("controller_gate_passed must be True")
        if not verified_receipt.get("scope_gate_passed"):
            raise RuntimeError("scope_gate_passed must be True")
        if not verified_receipt.get("deletion_gate_passed"):
            raise RuntimeError("deletion_gate_passed must be True")
        if not verified_receipt.get("protected_contract_gate_passed"):
            raise RuntimeError("protected_contract_gate_passed must be True")

        contract_dict = state.get("contract") or {}
        lease_dict = state.get("lease") or {}
        contract_fields = set(ArchitectTaskContract.model_fields.keys()) if hasattr(ArchitectTaskContract, "model_fields") else set()
        lease_fields = set(TargetWorktreeLease.model_fields.keys()) if hasattr(TargetWorktreeLease, "model_fields") else set()

        clean_lease = {k: v for k, v in lease_dict.items() if k in lease_fields} if lease_fields else lease_dict

        contract = None
        if isinstance(contract_dict, dict) and contract_fields and contract_dict.get("contract_hash"):
            # Restore the persisted contract exactly: rebuilding it through
            # build_contract changes derived fields (and so contract_hash),
            # which the receipt identity binding (#1760) rightly rejects.
            try:
                restored = ArchitectTaskContract.model_validate(
                    {k: v for k, v in contract_dict.items() if k in contract_fields}
                )
            except Exception:  # noqa: BLE001 - fall back to the legacy rebuild
                restored = None
            if restored is not None and restored.contract_hash == contract_dict.get("contract_hash"):
                contract = restored
        if contract is not None:
            pass
        elif isinstance(contract_dict, dict):
            c_dict = contract_dict.copy()
            if not c_dict.get("what"):
                c_dict["what"] = c_dict.get("objective", "Recover candidate")
            if not c_dict.get("why"):
                c_dict["why"] = c_dict.get("objective", "Recover candidate")
            contract = self.build_contract(c_dict)
        else:
            contract = contract_dict
        lease = TargetWorktreeLease(**clean_lease) if isinstance(lease_dict, dict) else lease_dict

        target_path = Path(lease.target_worktree).resolve()
        if not target_path.exists():
            raise RuntimeError("target worktree path does not exist")

        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        controller_root = Path(contract.controller_repo_root).resolve()
        entry = manager._worktree_entry(controller_root, target_path)
        if entry is None:
            raise RuntimeError(f"target path is not a registered Git worktree under controller {controller_root}")

        if manager._path_has_process(target_path):
            raise RuntimeError("target worktree has active running process")

        target_head = manager._run_git(["rev-parse", "HEAD"], cwd=target_path)
        receipt_obj = VerifiedCandidateReceipt(**verified_receipt)

        if target_head != lease.initial_head:
            raise RuntimeError("verified-uncommitted recovery rejected: target HEAD moved from initial_head; use recover_retained_candidate()")

        current = manager.capture_candidate(contract, lease)
        expected_state_hash = state.get("candidate_state_hash") or verified_receipt.get("candidate_state_hash")
        if current.candidate_state_hash != expected_state_hash:
            raise RuntimeError("candidate state hash changed after verification")
        committer = CandidateCommitter(manager)
        packet = committer.create_candidate_commit(contract, lease, receipt_obj)

        candidate_ref = manager.protect_candidate(contract, lease, packet.candidate_commit_sha)

        updates = {
            "candidate_commit_sha": packet.candidate_commit_sha,
            "candidate_tree_sha": packet.candidate_tree_sha,
            "candidate_ref": candidate_ref,
            "candidate_state_hash": packet.candidate_state_hash,
            "verified_receipt_hash": packet.verified_receipt_hash,
            "promotion_packet": asdict(packet),
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_status": "COMMITTED",
            "status": "PENDING_HUMAN_APPROVAL",
            "error": None,
            "cleanup_decision": "PROTECTED_BY_CANDIDATE_REF",
            "cleanup_eligible": False,
        }
        res = self._checkpoint(task_id, "PENDING_HUMAN_APPROVAL", updates, attempt_id=state.get("attempt_id"))
        return res or self._read_state(task_id) or state

    def bind_candidate_integration_closure(
        self,
        task_id: str,
        *,
        external_acceptance: ExternalAcceptanceReceipt,
        approval: Mapping[str, Any],
        runtime_identity: Mapping[str, Any],
        expected_canonical_head: str,
        integration_branch: str = "nexus/integration/main",
        _recovery_authority_normalization: bool = False,
    ) -> dict[str, Any]:
        """Bind external acceptance and a fresh integrate approval, without applying.

        The public Gateway supplies only these two typed inputs.  This service
        derives the preview and authorization envelope from the persisted
        APPROVED Candidate (or its exact non-applied PRE_APPLY failure), current
        repository HEAD, and runtime identity, then atomically records the
        closure binding for the existing integrate path.
        """
        if not isinstance(external_acceptance, ExternalAcceptanceReceipt):
            raise RuntimeError("EXTERNAL_ACCEPTANCE_TYPED_REQUIRED")
        approval_keys = {"schema", "approval_id", "approved_by", "issued_at", "expires_at", "bound_task_id", "bound_attempt_id", "bound_action_type", "approval_scope", "contract_kind", "contract_hash", "task_card_hash", "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash", "lifecycle_revision", "server_instance_id", "expected_canonical_head", "integration_branch", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "acceptance_receipt_hash"}
        if set(approval) - approval_keys:
            raise RuntimeError("CLOSURE_APPROVAL_SCHEMA_CLOSED")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if str(state.get("task_id") or "") != task_id:
            raise RuntimeError("CLOSURE_TASK_ID_DRIFT")
        identity = resolve_contract_identity(
            state,
            expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )
        runtime_identity = dict(runtime_identity)
        for key in ("contract_kind", "contract_hash", "task_card_hash", "owner_inline_contract"):
            if key in runtime_identity and runtime_identity[key] != identity[key]:
                raise RuntimeError("CLOSURE_RUNTIME_IDENTITY_MISMATCH")
        runtime_identity.update(identity)
        failed_pre_apply = (
            state.get("status") == "INTEGRATION_FAILED_PRE_APPLY"
            and state.get("promotion_status") == "INTEGRATION_FAILED_PRE_APPLY"
        )
        approved_pair = state.get("status") == "APPROVED" and state.get("promotion_status") == "APPROVED"
        integrating_pair = state.get("status") == "INTEGRATING" and state.get("promotion_status") == "INTEGRATING"
        mixed_recovery_pair = (
            _recovery_authority_normalization
            and state.get("status") == "INTEGRATING"
            and state.get("promotion_status") == "APPROVED"
        )
        if not failed_pre_apply and not (approved_pair or integrating_pair or mixed_recovery_pair):
            raise RuntimeError("CLOSURE_APPROVED_CANDIDATE_REQUIRED")
        if (
            not failed_pre_apply
            and integrating_pair
            and (
                state.get("merge_performed")
                or state.get("integration_result_sha") is not None
                or state.get("integration_receipt") is not None
                or state.get("integration_execution") is not None
            )
        ):
            raise RuntimeError("CLOSURE_INTEGRATING_REBIND_REQUIRES_UNRECORDED_APPLY")
        if integrating_pair or mixed_recovery_pair:
            persisted_contract = state.get("contract")
            packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
            candidate_sha = str(packet.get("candidate_commit_sha") or state.get("candidate_commit_sha") or "")
            if not isinstance(persisted_contract, Mapping) or not candidate_sha:
                raise RuntimeError("CLOSURE_INTEGRATING_BINDING_MISSING")
            contract_for_rebind = ArchitectTaskContract.model_validate({key: value for key, value in persisted_contract.items() if key != "contract_hash"})
            physical_manager = WorktreeManager(root_dir=contract_for_rebind.target_worktree_root)
            controller_root = Path(contract_for_rebind.controller_repo_root).resolve()
            # A separate detached Controller (#2251) applied by update-ref: the
            # applied subject is the integration branch ref, not its HEAD, and
            # only untracked pending Task Cards are admitted.  Every other
            # shape keeps the Controller HEAD tree and full cleanliness.
            separate_recovery_head = (
                ControlledIntegrationManager.separate_controller_integration_head(
                    controller_root, integration_branch
                )
            )
            current_head = physical_manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
            current_tree = physical_manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=controller_root)
            if separate_recovery_head is not None:
                current_head = separate_recovery_head
                current_tree = physical_manager._run_git(
                    ["rev-parse", f"{current_head}^{{tree}}"], cwd=controller_root
                )
            candidate_tree = physical_manager._run_git(["rev-parse", f"{candidate_sha}^{{tree}}"], cwd=controller_root)
            old_authorization = state.get("integration_authorization") if isinstance(state.get("integration_authorization"), Mapping) else {}
            prior_closure = state.get("integration_closure_binding") if isinstance(state.get("integration_closure_binding"), Mapping) else {}
            if not old_authorization or not prior_closure:
                raise RuntimeError("CLOSURE_INTEGRATING_PRIOR_CLOSURE_REQUIRED")
            try:
                prior_authorization = IntegrationAuthorizationEnvelope(**{
                    key: value for key, value in old_authorization.items()
                    if key != "authorization_hash"
                })
            except Exception as exc:
                raise RuntimeError("CLOSURE_INTEGRATING_PRIOR_AUTH_INVALID") from exc
            if old_authorization.get("authorization_hash") != prior_authorization.authorization_hash:
                raise RuntimeError("CLOSURE_INTEGRATING_PRIOR_AUTH_HASH_DRIFT")
            closure_payload = {key: value for key, value in prior_closure.items() if key != "binding_hash"}
            expected_closure_hash = hashlib.sha256(json.dumps(
                closure_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()).hexdigest()
            if (
                prior_closure.get("binding_hash") != expected_closure_hash
                or prior_closure.get("authorization_hash") != old_authorization.get("authorization_hash")
            ):
                raise RuntimeError("CLOSURE_INTEGRATING_PRIOR_CLOSURE_HASH_DRIFT")
            old_pre_apply_head = str(
                prior_closure.get("recovery_pre_apply_head")
                or old_authorization.get("expected_canonical_head")
                or ""
            )
            if separate_recovery_head is not None:
                ControlledIntegrationManager._require_clean_controller(
                    controller_root,
                    allow_pending_task_cards=True,
                    message="CLOSURE_INTEGRATING_APPLIED_TREE_REQUIRED",
                )
            if (
                current_head != expected_canonical_head
                or current_tree != candidate_tree
                or (
                    separate_recovery_head is None
                    and physical_manager._run_git(
                        ["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root
                    )
                )
                or not re.fullmatch(r"[0-9a-f]{40}", old_pre_apply_head)
                or old_pre_apply_head == current_head
            ):
                raise RuntimeError("CLOSURE_INTEGRATING_APPLIED_TREE_REQUIRED")
            parents = physical_manager._run_git(
                ["rev-list", "--parents", "-n", "1", current_head], cwd=controller_root
            ).split()[1:]
            if current_head == candidate_sha:
                # Exact candidate HEAD is retained for legacy fast-forward
                # recovery.  Any other applied head must be the direct no-ff
                # merge of exactly the old head and candidate.
                if len(parents) != 1:
                    raise RuntimeError("CLOSURE_INTEGRATING_APPLIED_TOPOLOGY_REQUIRED")
            elif len(parents) != 2 or set(parents) != {old_pre_apply_head, candidate_sha}:
                raise RuntimeError("CLOSURE_INTEGRATING_APPLIED_TOPOLOGY_REQUIRED")
            try:
                candidate_ref_head = physical_manager._run_git(["rev-parse", state.get("candidate_ref") or ""], cwd=controller_root)
            except RuntimeError as exc:
                raise RuntimeError("CLOSURE_INTEGRATING_CANDIDATE_REF_DRIFT") from exc
            if candidate_ref_head != candidate_sha:
                raise RuntimeError("CLOSURE_INTEGRATING_CANDIDATE_REF_DRIFT")
            ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", candidate_sha, current_head], cwd=controller_root, capture_output=True, text=True)
            if ancestry.returncode != 0:
                raise RuntimeError("CLOSURE_INTEGRATING_CANDIDATE_ANCESTRY_REQUIRED")
            old_ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", old_pre_apply_head, current_head], cwd=controller_root, capture_output=True, text=True)
            if old_ancestry.returncode != 0:
                raise RuntimeError("CLOSURE_INTEGRATING_PRE_APPLY_HEAD_REQUIRED")
        if failed_pre_apply:
            failed_execution = state.get("integration_execution")
            if (
                state.get("merge_performed")
                or state.get("integration_result_sha")
                or state.get("integration_receipt")
                or not isinstance(failed_execution, Mapping)
                or failed_execution.get("stage") != "PRE_APPLY"
                or failed_execution.get("merge_performed") is not False
                or failed_execution.get("branch_head_before")
                != failed_execution.get("branch_head_after")
            ):
                raise RuntimeError("CLOSURE_PRE_APPLY_FAILURE_REQUIRED")
        expected_status = (
            "INTEGRATION_FAILED_PRE_APPLY"
            if failed_pre_apply
            else ("INTEGRATING" if integrating_pair or mixed_recovery_pair else "APPROVED")
        )
        if "integration_closure_binding" in state and (not isinstance(state.get("integration_closure_binding"), Mapping) or not state.get("integration_closure_binding")):
            raise RuntimeError("CLOSURE_BINDING_MALFORMED")
        existing = state.get("integration_closure_binding") if isinstance(state.get("integration_closure_binding"), Mapping) else None
        if existing:
            if "integration_approval_grant" not in state or not isinstance(state.get("integration_approval_grant"), Mapping) or not state.get("integration_approval_grant"):
                raise RuntimeError("CLOSURE_BINDING_MALFORMED")
            if state.get("merge_performed") or state.get("integration_receipt") or state.get("integration_result_sha") or (state.get("integration_execution") and not failed_pre_apply) or state.get("status") in {"INTEGRATED", "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED", "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"}:
                raise RuntimeError("CLOSURE_REBIND_AFTER_INTEGRATION_FORBIDDEN")
            prior_history = state.get("integration_closure_history")
            if "integration_closure_history" in state and not isinstance(prior_history, list):
                raise RuntimeError("CLOSURE_HISTORY_MALFORMED")
            persisted_grant = state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else {}
            packet_for_rebind = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
            immutable_state = {
                "task_id": task_id,
                "attempt_id": str(state.get("attempt_id") or ""),
                "candidate_commit_sha": str(packet_for_rebind.get("candidate_commit_sha") or state.get("candidate_commit_sha") or ""),
                "candidate_tree_sha": str(packet_for_rebind.get("candidate_tree_sha") or state.get("candidate_tree_sha") or ""),
                "candidate_state_hash": str(packet_for_rebind.get("candidate_state_hash") or state.get("candidate_state_hash") or ""),
                "verified_receipt_hash": str(packet_for_rebind.get("verified_receipt_hash") or state.get("verified_receipt_hash") or ""),
                "contract_kind": identity["contract_kind"],
                "contract_hash": identity["contract_hash"] or "",
                "task_card_hash": identity["task_card_hash"] or "",
            }
            for field, value in immutable_state.items():
                prior_value = existing.get(field)
                if field not in existing and field not in {"contract_kind", "contract_hash", "task_card_hash"}:
                    raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
                if not prior_value and field == "contract_kind":
                    prior_value = persisted_grant.get("contract_kind") or ContractKind.TRACKED_TASK_CARD.value
                if not prior_value and field == "contract_hash":
                    prior_value = persisted_grant.get("contract_hash") or ""
                if not prior_value and field == "task_card_hash":
                    prior_value = persisted_grant.get("task_card_hash") or ""
                if prior_value is not None and str(prior_value or "") != value:
                    raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
            if str(existing.get("acceptance_receipt_hash") or "") != str(external_acceptance.receipt_hash) or str(existing.get("canonical_branch") or "") != str(integration_branch) or str(existing.get("bound_action_type") or persisted_grant.get("bound_action_type") or "") != LifecycleActionType.CANDIDATE_INTEGRATE.value or str(existing.get("approval_scope") or persisted_grant.get("approval_scope") or "") != "ALLOW_ACTION_ONCE":
                raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
            persisted_acceptance = state.get("external_acceptance")
            if not isinstance(persisted_acceptance, Mapping) or dict(persisted_acceptance) != external_acceptance.to_dict():
                raise RuntimeError("CLOSURE_IMMUTABLE_BINDING_DRIFT")
            replay = (
                str(existing.get("task_id") or "") == task_id
                and str(existing.get("attempt_id") or "") == str(state.get("attempt_id") or "")
                and str(existing.get("candidate_commit_sha") or "") == immutable_state["candidate_commit_sha"]
                and str(existing.get("candidate_tree_sha") or "") == immutable_state["candidate_tree_sha"]
                and str(existing.get("candidate_state_hash") or "") == immutable_state["candidate_state_hash"]
                and str(existing.get("verified_receipt_hash") or "") == immutable_state["verified_receipt_hash"]
                and str(existing.get("acceptance_receipt_hash") or "") == str(external_acceptance.receipt_hash)
                and str(existing.get("canonical_branch") or "") == str(integration_branch)
                and str(existing.get("expected_canonical_head") or existing.get("canonical_head") or "") == str(expected_canonical_head)
                and dict(existing.get("runtime_identity") or {}) == dict(runtime_identity)
                and str(existing.get("approval_id") or persisted_grant.get("approval_id") or "") == str(approval.get("approval_id") or "")
                and str(existing.get("approval_issued_at") or persisted_grant.get("issued_at") or "") == str(approval.get("issued_at") or "")
                and str(existing.get("approval_expires_at") or persisted_grant.get("expires_at") or "") == str(approval.get("expires_at") or "")
                and dict(existing.get("approval_projection") or {key: persisted_grant.get(key) for key in approval_keys}) == {key: approval.get(key) for key in approval_keys}
            )
            projection = dict(existing.get("approval_projection") or {key: persisted_grant.get(key) for key in approval_keys})
            same_approval_id = str(existing.get("approval_id") or persisted_grant.get("approval_id") or "") == str(approval.get("approval_id") or "")
            if failed_pre_apply and same_approval_id:
                raise RuntimeError("CLOSURE_FAILED_APPROVAL_REUSE")
            if same_approval_id and projection != {key: approval.get(key) for key in approval_keys}:
                raise RuntimeError("CLOSURE_APPROVAL_REPLAY_DRIFT")
            if replay and not failed_pre_apply:
                return {**state, "closure_binding": dict(existing), "duplicate": True, "integration_performed": False}
        attempt_id = str(state.get("attempt_id") or "")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        candidate_commit = str(packet.get("candidate_commit_sha") or state.get("candidate_commit_sha") or "")
        candidate_tree = str(packet.get("candidate_tree_sha") or state.get("candidate_tree_sha") or "")
        candidate_state = str(packet.get("candidate_state_hash") or state.get("candidate_state_hash") or "")
        verified_receipt_hash = str(packet.get("verified_receipt_hash") or state.get("verified_receipt_hash") or "")
        approved_binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        old_approval = approved_binding.get("approval_grant") if isinstance(approved_binding.get("approval_grant"), Mapping) else {}
        if not approved_binding or not old_approval.get("consumed_at") or old_approval.get("approval_scope") != "ALLOW_ACTION_ONCE":
            raise RuntimeError("CLOSURE_APPROVED_BINDING_REQUIRED")
        for field in ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash"):
            if not approved_binding.get(field) or str(approved_binding.get(field)) != str(packet.get(field)):
                raise RuntimeError("CLOSURE_CANDIDATE_BINDING_DRIFT")
        if external_acceptance.task_id != task_id or external_acceptance.attempt_id != attempt_id:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
        if external_acceptance.candidate_commit != candidate_commit:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
        approval_binding = {"candidate_commit_sha": candidate_commit, "candidate_tree_sha": candidate_tree, "candidate_state_hash": candidate_state, "verified_receipt_hash": verified_receipt_hash, "acceptance_receipt_hash": external_acceptance.receipt_hash}
        if any(str(approval.get(key) or "") != str(value) for key, value in approval_binding.items()):
            raise RuntimeError("CLOSURE_CANDIDATE_BINDING_DRIFT")
        artifact_path = Path(external_acceptance.verifier_artifact).expanduser()
        evidence_root = (self.state_dir / "acceptance-artifacts" / task_id).resolve()
        try:
            artifact_path.resolve().relative_to(evidence_root)
        except ValueError as exc:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_REQUIRED") from exc
        if not artifact_path.is_absolute() or ".git" in artifact_path.parts or not artifact_path.is_file():
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_REQUIRED")
        try:
            artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_UNREADABLE") from exc
        if artifact_digest != external_acceptance.receipt_hash:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_HASH_MISMATCH")
        contract_kind = identity["contract_kind"]
        contract_hash = identity["contract_hash"]
        task_card_hash = identity["task_card_hash"]
        owner_inline_contract = identity["owner_inline_contract"]
        approval_validated = validate_approval_grant(
            approval,
            task_id=task_id,
            attempt_id=attempt_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE.value,
            task_card_hash=str(task_card_hash) if task_card_hash else None,
            contract_kind=contract_kind,
            contract_hash=contract_hash or None,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=str(runtime_identity.get("tool_manifest_hash") or ""),
            full_tool_schema_hash=str(runtime_identity.get("full_tool_schema_hash") or ""),
            permission_policy_hash=str(runtime_identity.get("permission_policy_hash") or ""),
            lifecycle_revision=str(runtime_identity.get("lifecycle_revision") or ""),
            server_instance_id=str(runtime_identity.get("server_instance_id") or ""),
            allow_consumed=False,
        )
        contract_data = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        verifier_manifest = ControlledIntegrationManager._admitted_manifest(
            state,
            contract_data,
        )
        verifier_manifest_payload = [dict(item) for item in verifier_manifest]
        verifier_manifest_hash = hashlib.sha256(
            json.dumps(
                verifier_manifest_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        controller_root = Path(str(contract_data.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
        manager = WorktreeManager(root_dir=str(contract_data.get("target_worktree_root") or controller_root))
        # A separate detached Controller (#2230) integrates by update-ref: the
        # canonical head is the integration branch ref (its CAS subject), not
        # the Controller HEAD, which tasks/-only Task Card bind commits move.
        # Every other shape keeps HEAD on a checked-out, fully clean branch.
        separate_controller_head = ControlledIntegrationManager.separate_controller_integration_head(
            controller_root, integration_branch
        )
        separate_controller = separate_controller_head is not None
        current_head = (
            separate_controller_head
            if separate_controller
            else manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        )
        if not re.fullmatch(r"[0-9a-f]{40}", expected_canonical_head) or current_head != expected_canonical_head:
            raise RuntimeError("CLOSURE_CANONICAL_HEAD_DRIFT")
        if str(approval.get("expected_canonical_head") or expected_canonical_head) != expected_canonical_head:
            raise RuntimeError("CLOSURE_HEAD_BINDING_MISMATCH")
        if separate_controller:
            # Only untracked plain pending Task Cards under tasks/ are admitted.
            ControlledIntegrationManager._require_clean_controller(
                controller_root, allow_pending_task_cards=True, message="CLOSURE_CANONICAL_DIRTY"
            )
        status = manager._run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root)
        if status and not separate_controller:
            raise RuntimeError("CLOSURE_CANONICAL_DIRTY")
        if not approval.get("integration_branch") or integration_branch != str(approval.get("integration_branch")):
            raise RuntimeError("CLOSURE_BRANCH_BINDING_MISMATCH")
        current_branch = manager._run_git(["branch", "--show-current"], cwd=controller_root)
        if current_branch != ("" if separate_controller else integration_branch):
            raise RuntimeError("CLOSURE_CANONICAL_BRANCH_DRIFT")
        lease = state.get("lease") if isinstance(state.get("lease"), Mapping) else {}
        target_id = str(lease.get("lease_id") or state.get("target_id") or task_id)
        target_path = str(lease.get("target_worktree") or contract_data.get("target_repo_root") or "")
        if not target_path:
            raise RuntimeError("CLOSURE_TARGET_BINDING_REQUIRED")
        verification_commands = tuple(str(command) for command in contract_data.get("verifier_commands") or ())
        preview = TargetIntegrationLifecycle.build_preview(
            task_id=task_id,
            target_id=target_id,
            candidate_commit=candidate_commit,
            acceptance=external_acceptance,
            canonical_branch=integration_branch,
            expected_canonical_head=current_head,
            verification_commands=verification_commands,
            cleanup_target_id=target_id,
            rollback="retain target and candidate ref",
        )
        dirty_baseline = hashlib.sha256(status.encode()).hexdigest()
        authorization = TargetIntegrationLifecycle.authorize(
            task_id=task_id,
            campaign_id=str((state.get("request") or {}).get("campaign_id") or task_id),
            task_card_hash=str(task_card_hash or contract_hash),
            candidate_commit=candidate_commit,
            candidate_receipt_hash=verified_receipt_hash,
            acceptance_receipt_hash=external_acceptance.receipt_hash,
            canonical_root=str(controller_root),
            canonical_branch=integration_branch,
            expected_canonical_head=current_head,
            canonical_dirty_baseline=dirty_baseline,
            preview=preview,
            cleanup_target_id=target_id,
            cleanup_target_path=target_path,
            durable_ref=str(state.get("candidate_ref") or ""),
            rollback="retain target and candidate ref",
            issued_at=str(approval.get("issued_at") or _utc_now()),
            expires_at=str(approval.get("expires_at") or "") or None,
            attempt_id=attempt_id,
            candidate_tree_sha=candidate_tree,
            candidate_state_hash=candidate_state,
            reviewer_id=external_acceptance.reviewer_id,
            verifier_artifact_hash=artifact_digest,
        )
        authorization_dict = authorization.to_dict()
        authorization_dict["authorization_hash"] = authorization.authorization_hash
        closure = {
            "schema": "nexus.candidate_integration_closure.v1",
            "task_id": task_id,
            "attempt_id": attempt_id,
            "candidate_commit_sha": candidate_commit,
            "candidate_tree_sha": candidate_tree,
            "candidate_state_hash": candidate_state,
            "verified_receipt_hash": verified_receipt_hash,
            "acceptance_receipt_hash": external_acceptance.receipt_hash,
            "canonical_head": current_head,
            "expected_canonical_head": expected_canonical_head,
            "canonical_branch": integration_branch,
            "runtime_identity": dict(runtime_identity),
            "approval_id": str(approval.get("approval_id") or ""),
            "approval_issued_at": str(approval.get("issued_at") or ""),
            "approval_expires_at": str(approval.get("expires_at") or ""),
            "approval_projection": {key: approval.get(key) for key in approval_keys},
            "recovery_only": integrating_pair or mixed_recovery_pair,
            "recovery_pre_apply_head": old_pre_apply_head if integrating_pair or mixed_recovery_pair else None,
            "approval_scope": str(approval.get("approval_scope") or ""),
            "bound_action_type": LifecycleActionType.CANDIDATE_INTEGRATE.value,
            "contract_kind": contract_kind,
            "contract_hash": contract_hash,
            "task_card_hash": str(task_card_hash or ""),
            "verifier_manifest_sha256": verifier_manifest_hash,
            "preview": preview.to_dict(),
            "authorization_hash": authorization.authorization_hash,
        }
        if separate_controller:
            # Audit only: integration never reads this worktree or its HEAD.
            closure["controller_shape"] = "SEPARATE_DETACHED_WORKTREE"
            closure["controller_head"] = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        closure_hash = hashlib.sha256(json.dumps(closure, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        closure["binding_hash"] = closure_hash
        now = _utc_now()
        duplicate = False
        expected_prior_snapshot = json.dumps(_jsonable(dict(existing)) if existing else None, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_history_snapshot = json.dumps(_jsonable(state.get("integration_closure_history")), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_grant_snapshot = json.dumps(_jsonable(state.get("integration_approval_grant")), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_failure_snapshot = json.dumps(
            _jsonable(state.get("integration_execution")),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        service_contract_hash = str(state.get("contract_hash") or "")
        expected_prior_pair = (
            ("INTEGRATING", "APPROVED")
            if mixed_recovery_pair
            else (expected_status, expected_status)
        )

        def mutate(current: dict[str, Any]) -> None:
            nonlocal duplicate, closure_hash
            if (
                str(current.get("task_id") or "") != task_id
                or (current.get("status"), current.get("promotion_status")) != expected_prior_pair
            ):
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if mixed_recovery_pair and (
                current.get("merge_performed") not in (False, None)
                or current.get("integration_result_sha") is not None
                or current.get("integration_receipt") is not None
                or current.get("integration_execution") is not None
            ):
                raise RuntimeError("RECOVERY_AUTHORITY_CONCURRENCY_EFFECT_DRIFT")
            if current.get("attempt_id") != attempt_id:
                raise RuntimeError("CLOSURE_ATTEMPT_DRIFT")
            current_packet = current.get("promotion_packet") if isinstance(current.get("promotion_packet"), Mapping) else {}
            for key, expected in {
                "candidate_commit_sha": candidate_commit,
                "candidate_tree_sha": candidate_tree,
                "candidate_state_hash": candidate_state,
                "verified_receipt_hash": verified_receipt_hash,
            }.items():
                if str(current_packet.get(key) or current.get(key) or "") != str(expected):
                    raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            current_identity = resolve_contract_identity(
                current,
                expected_task_id=task_id,
                expected_head=str(current.get("controller_revision") or ""),
            )
            if (
                str(current.get("contract_hash") or "") != service_contract_hash
                or current_identity != identity
            ):
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            persisted_current_acceptance = current.get("external_acceptance")
            if not isinstance(persisted_current_acceptance, Mapping) or dict(persisted_current_acceptance) != external_acceptance.to_dict():
                if existing or persisted_current_acceptance is not None:
                    raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if not existing and current.get("integration_approval_grant"):
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            prior = current.get("integration_closure_binding") if isinstance(current.get("integration_closure_binding"), Mapping) else None
            if json.dumps(_jsonable(dict(prior)) if prior else None, sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_prior_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if json.dumps(_jsonable(current.get("integration_closure_history")), sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_history_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if json.dumps(_jsonable(current.get("integration_approval_grant")), sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_grant_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if json.dumps(_jsonable(current.get("integration_execution")), sort_keys=True, separators=(",", ":"), ensure_ascii=False) != expected_failure_snapshot:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            current_contract = current.get("contract") if isinstance(current.get("contract"), Mapping) else {}
            current_manifest = ControlledIntegrationManager._admitted_manifest(
                current,
                current_contract,
            )
            if list(current_manifest) != verifier_manifest_payload:
                raise RuntimeError("CLOSURE_BINDING_CONCURRENCY_DRIFT")
            if separate_controller:
                try:
                    still_separate = ControlledIntegrationManager.separate_controller_integration_head(
                        controller_root, integration_branch
                    ) is not None
                    ControlledIntegrationManager._require_clean_controller(
                        controller_root,
                        allow_pending_task_cards=True,
                        message="CLOSURE_CANONICAL_REBIND_DRIFT",
                    )
                except RuntimeError as exc:
                    raise RuntimeError("CLOSURE_CANONICAL_REBIND_DRIFT") from exc
                if not still_separate:
                    raise RuntimeError("CLOSURE_CANONICAL_REBIND_DRIFT")
                # The audit-only Controller HEAD is sealed as of lock time.
                locked_head = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
                if locked_head != closure["controller_head"]:
                    closure.pop("binding_hash")
                    closure["controller_head"] = locked_head
                    sealed = json.dumps(
                        closure, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    )
                    closure_hash = hashlib.sha256(sealed.encode()).hexdigest()
                    closure["binding_hash"] = closure_hash
            else:
                live_branch = manager._run_git(["branch", "--show-current"], cwd=controller_root)
                live_status = manager._run_git(["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root)
                if live_branch != integration_branch or live_status:
                    raise RuntimeError("CLOSURE_CANONICAL_REBIND_DRIFT")
            try:
                if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != external_acceptance.receipt_hash:
                    raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_HASH_MISMATCH")
            except OSError as exc:
                raise RuntimeError("EXTERNAL_ACCEPTANCE_ARTIFACT_UNREADABLE") from exc
            if prior:
                if current.get("merge_performed") or current.get("integration_receipt") or current.get("integration_result_sha") or (current.get("integration_execution") and not failed_pre_apply) or current.get("status") in {"INTEGRATED", "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED", "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"}:
                    raise RuntimeError("CLOSURE_REBIND_AFTER_INTEGRATION_FORBIDDEN")
                history = current.get("integration_closure_history")
                if "integration_closure_history" in current and not isinstance(history, list):
                    raise RuntimeError("CLOSURE_HISTORY_MALFORMED")
                if history is None:
                    history = []
                    current["integration_closure_history"] = history
                history.append({
                    "closure_binding": _jsonable(dict(prior)),
                    "approval_grant": _jsonable(current.get("integration_approval_grant")),
                    "preview": _jsonable(current.get("integration_preview")),
                    "authorization": _jsonable(current.get("integration_authorization")),
                    "binding_hash": prior.get("binding_hash"),
                    "superseded_at": now,
                    "superseded_by": str(approval.get("approval_id") or ""),
                    "reason": "pre_apply_rebind",
                })
            if separate_controller:
                try:
                    live_head = ControlledIntegrationManager.separate_controller_integration_head(
                        controller_root, integration_branch
                    )
                except RuntimeError as exc:
                    raise RuntimeError("CLOSURE_CANONICAL_HEAD_DRIFT") from exc
            else:
                live_head = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
            if live_head != current_head:
                raise RuntimeError("CLOSURE_CANONICAL_HEAD_DRIFT")
            consumed = dict(approval)
            consumed["consumed_at"] = now
            consumed["validation_receipt"] = approval_validated
            current["external_acceptance"] = external_acceptance.to_dict()
            current["integration_authorization"] = authorization_dict
            current["integration_preview"] = preview.to_dict()
            current["integration_approval_grant"] = consumed
            current["integration_closure_binding"] = closure
            current["integration_closure_binding_hash"] = closure_hash
            current["integration_recovery_only"] = bool(integrating_pair or mixed_recovery_pair)
            current["integration_verifier_manifest"] = verifier_manifest_payload
            if failed_pre_apply:
                failure_history = current.get("integration_failure_history")
                if "integration_failure_history" in current and not isinstance(failure_history, list):
                    raise RuntimeError("CLOSURE_FAILURE_HISTORY_MALFORMED")
                if failure_history is None:
                    failure_history = []
                    current["integration_failure_history"] = failure_history
                failure_history.append({
                    "schema": "nexus.integration_failure_history.v1",
                    "status": "INTEGRATION_FAILED_PRE_APPLY",
                    "integration_error": current.get("integration_error"),
                    "integration_status": current.get("integration_status"),
                    "integration_execution": _jsonable(current.get("integration_execution")),
                    "closure_binding_hash": prior.get("binding_hash") if prior else None,
                    "approval_id": persisted_grant.get("approval_id"),
                    "superseded_at": now,
                })
                current["status"] = "APPROVED"
                current["promotion_status"] = "APPROVED"
                current["terminal_status"] = "APPROVED"
                current["final_disposition"] = "REBIND_READY"
                current["integration_status"] = "REBIND_READY"
                current["integration_error"] = None
                current["integration_execution"] = None
                current["state_retention_status"] = "ACTIVE"
                current["archive_eligible"] = False
                current["cleanup_eligible"] = False
                status_history = current.get("status_history")
                if not isinstance(status_history, list):
                    raise RuntimeError("CLOSURE_STATUS_HISTORY_MALFORMED")
                status_history.append({
                    "at": now,
                    "status": "APPROVED",
                    "reason": "pre_apply_closure_rebind",
                })
            elif mixed_recovery_pair:
                # Normalize the historical mixed pair only after every exact
                # binding and live-tree CAS check above has passed.  Keep all
                # prior pre-apply evidence untouched; this fence only permits
                # the dedicated recovery reconciliation path.
                current["status"] = "INTEGRATING"
                current["promotion_status"] = "INTEGRATING"
                current["terminal_status"] = "INTEGRATING"
                current["final_disposition"] = "RECOVERY_AUTHORITY_BOUND"
                current["integration_status"] = "RECOVERY_ONLY"
                current["state_retention_status"] = "ACTIVE"
                current["archive_eligible"] = False
                current["cleanup_eligible"] = False
                status_history = current.get("status_history")
                if not isinstance(status_history, list):
                    raise RuntimeError("CLOSURE_STATUS_HISTORY_MALFORMED")
                status_history.append({
                    "at": now,
                    "status": "INTEGRATING",
                    "reason": "recovery_authority_normalized",
                })

        persisted = self._mutate_state(task_id, mutate)
        if persisted is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return {**persisted, "closure_binding": closure, "duplicate": duplicate, "integration_performed": False}

    def normalize_integration_recovery_authority(
        self,
        task_id: str,
        *,
        external_acceptance: ExternalAcceptanceReceipt,
        approval: Mapping[str, Any],
        runtime_identity: Mapping[str, Any],
        expected_canonical_head: str,
        integration_branch: str = "nexus/integration/main",
    ) -> dict[str, Any]:
        """Bind a fresh recovery fence to one historical mixed state.

        This is intentionally separate from ordinary closure binding: only
        ``INTEGRATING/APPROVED`` is eligible, and the closed integration
        approval is treated as a one-shot recovery authority.  No integration
        manager, retry, or receipt recording is performed here.
        """
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") != "INTEGRATING" or state.get("promotion_status") != "APPROVED":
            normalized = (
                state.get("status") == "INTEGRATING"
                and state.get("promotion_status") == "INTEGRATING"
                and state.get("integration_recovery_only") is True
                and isinstance(state.get("integration_closure_binding"), Mapping)
                and state["integration_closure_binding"].get("recovery_only") is True
            )
            if not normalized:
                raise RuntimeError("RECOVERY_AUTHORITY_MIXED_STATE_REQUIRED")
            closure = state["integration_closure_binding"]
            identity = resolve_contract_identity(
                state, expected_task_id=task_id,
                expected_head=str(state.get("controller_revision") or ""),
            )
            supplied_runtime = dict(runtime_identity)
            supplied_runtime.update(identity)
            projection = closure.get("approval_projection")
            if (
                dict(closure.get("runtime_identity") or {}) != supplied_runtime
                or dict(state.get("external_acceptance") or {}) != external_acceptance.to_dict()
                or not isinstance(projection, Mapping)
                or dict(projection) != {key: approval.get(key) for key in projection}
                or str(closure.get("expected_canonical_head") or closure.get("canonical_head") or "") != str(expected_canonical_head)
                or str(closure.get("canonical_branch") or "") != str(integration_branch)
            ):
                raise RuntimeError("RECOVERY_AUTHORITY_REPLAY_DRIFT")
            return self.bind_candidate_integration_closure(
                task_id,
                external_acceptance=external_acceptance,
                approval=approval,
                runtime_identity=runtime_identity,
                expected_canonical_head=expected_canonical_head,
                integration_branch=integration_branch,
                _recovery_authority_normalization=True,
            )
        if (
            state.get("merge_performed")
            or state.get("integration_receipt") is not None
            or state.get("integration_result_sha") is not None
            or state.get("integration_execution") is not None
        ):
            raise RuntimeError("RECOVERY_AUTHORITY_EFFECT_ALREADY_RECORDED")
        return self.bind_candidate_integration_closure(
            task_id,
            external_acceptance=external_acceptance,
            approval=approval,
            runtime_identity=runtime_identity,
            expected_canonical_head=expected_canonical_head,
            integration_branch=integration_branch,
            _recovery_authority_normalization=True,
        )

    def integrate_approved(
        self,
        task_id: str,
        *,
        integration_branch: str = "nexus/integration/main",
        runtime_identity: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("integration_recovery_only") or (
            isinstance(state.get("integration_closure_binding"), Mapping)
            and state["integration_closure_binding"].get("recovery_only")
        ):
            raise RuntimeError("INTEGRATION_RECOVERY_ONLY")
        request = state.get("request") or {}
        if self.ephemeral and (
            request.get("task_card_required") or request.get("lifecycle_identity_required")
        ):
            raise RuntimeError("EPHEMERAL_INTEGRATION_FORBIDDEN: rehearsal state cannot be integrated")
        if state.get("status") in {"INTEGRATED", "INTEGRATED_AND_CLEANED", "INTEGRATED_TARGET_RETAINED"} and state.get("promotion_status") == "INTEGRATED":
            return state
        promotion_status = state.get("promotion_status") or state.get("status")
        if state.get("merge_performed") or state.get("status") == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
            raise RuntimeError("INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN")
        if state.get("status") not in {"APPROVED", "INTEGRATING"} and promotion_status not in {"APPROVED", "INTEGRATING"}:
            raise RuntimeError(
                "exact approved binding is required before integration; "
                f"task status must be APPROVED or INTEGRATING to integrate, got {state.get('status')}"
            )

        if runtime_identity is not None:
            approved = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
            integration_grant = state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else None
            grant = integration_grant or (approved.get("approval_grant") if isinstance(approved.get("approval_grant"), Mapping) else None)
            if not grant or not grant.get("consumed_at"):
                raise RuntimeError("APPROVAL_REVALIDATION_REQUIRED: persisted approval grant is missing consume evidence")
            identity = resolve_contract_identity(
                state,
                expected_task_id=task_id,
                expected_head=str(state.get("controller_revision") or ""),
            )
            for key in ("contract_kind", "contract_hash", "task_card_hash", "owner_inline_contract"):
                if key in runtime_identity and runtime_identity[key] != identity[key]:
                    raise RuntimeError("APPROVAL_RUNTIME_IDENTITY_MISMATCH")
            contract_kind = identity["contract_kind"]
            contract_hash = identity["contract_hash"]
            task_card_hash = identity["task_card_hash"]
            owner_inline_contract = identity["owner_inline_contract"]
            if integration_grant:
                validate_approval_grant(
                    integration_grant,
                    task_id=task_id,
                    attempt_id=str(state.get("attempt_id") or ""),
                    action_type=LifecycleActionType.CANDIDATE_INTEGRATE.value,
                    task_card_hash=task_card_hash,
                    contract_kind=contract_kind,
                    contract_hash=contract_hash,
                    owner_inline_contract=owner_inline_contract,
                    tool_manifest_hash=str(runtime_identity.get("tool_manifest_hash") or ""),
                    full_tool_schema_hash=str(runtime_identity.get("full_tool_schema_hash") or ""),
                    permission_policy_hash=str(runtime_identity.get("permission_policy_hash") or ""),
                    lifecycle_revision=str(runtime_identity.get("lifecycle_revision") or ""),
                    server_instance_id=str(runtime_identity.get("server_instance_id") or ""),
                    allow_consumed=True,
                )
            expected_identity = {
                "contract_kind": contract_kind,
                "contract_hash": contract_hash,
                "task_card_hash": task_card_hash,
                "tool_manifest_hash": runtime_identity.get("tool_manifest_hash"),
                "full_tool_schema_hash": runtime_identity.get("full_tool_schema_hash"),
                "permission_policy_hash": runtime_identity.get("permission_policy_hash"),
                "lifecycle_revision": runtime_identity.get("lifecycle_revision"),
                "server_instance_id": runtime_identity.get("server_instance_id"),
            }
            drift = {
                key: {"expected": value, "received": grant.get(key)}
                for key, value in expected_identity.items()
                if str(grant.get(key)) != str(value)
            }
            if drift:
                code = "APPROVAL_BINDING_MISMATCH" if set(drift) & {"contract_kind", "contract_hash", "task_card_hash"} else "APPROVAL_DEFINITION_DRIFT"
                raise RuntimeError(f"{code}: {json.dumps(drift, sort_keys=True)}")
            packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
            binding_fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
            if any(approved.get(field) != packet.get(field) for field in binding_fields):
                raise RuntimeError("APPROVAL_CANDIDATE_BINDING_DRIFT")

        approved = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        raw_acceptance = state.get("external_acceptance") or approved.get("external_acceptance")
        raw_authorization = state.get("integration_authorization") or approved.get("integration_authorization")
        if raw_acceptance is None:
            raise RuntimeError("EXTERNAL_ACCEPTANCE_REQUIRED: persisted acceptance receipt is missing")
        if raw_authorization is None:
            raise RuntimeError("OWNER_AUTHORIZATION_REQUIRED: persisted integration authorization is missing")
        acceptance_obj = raw_acceptance if isinstance(raw_acceptance, ExternalAcceptanceReceipt) else ExternalAcceptanceReceipt(**dict(raw_acceptance))
        authorization_obj = raw_authorization if isinstance(raw_authorization, IntegrationAuthorizationEnvelope) else IntegrationAuthorizationEnvelope(**{key: value for key, value in dict(raw_authorization).items() if key != "authorization_hash"})
        if acceptance_obj.task_id != task_id or acceptance_obj.candidate_commit != str((state.get("promotion_packet") or {}).get("candidate_commit_sha") or ""):
            raise RuntimeError("EXTERNAL_ACCEPTANCE_BINDING_MISMATCH")
        if authorization_obj.task_id != task_id or authorization_obj.attempt_id not in {"", str(state.get("attempt_id") or "")}:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_BINDING_MISMATCH")
        if authorization_obj.candidate_commit != acceptance_obj.candidate_commit or authorization_obj.acceptance_receipt_hash != acceptance_obj.receipt_hash:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_ACCEPTANCE_MISMATCH")
        if authorization_obj.canonical_branch != integration_branch:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_BRANCH_DRIFT")
        if "INTEGRATION_STAGING" not in authorization_obj.action_set or "APPLY_VERIFIED_INTEGRATION" not in authorization_obj.action_set:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_ACTION_SET_INCOMPLETE")
        persisted_auth_hash = str(
            (isinstance(raw_authorization, Mapping) and raw_authorization.get("authorization_hash"))
            or (isinstance(state.get("integration_closure_binding"), Mapping) and state["integration_closure_binding"].get("authorization_hash"))
            or ""
        )
        if persisted_auth_hash and authorization_obj.authorization_hash != persisted_auth_hash:
            raise RuntimeError("INTEGRATION_AUTHORIZATION_TAMPERED: authorization hash mismatch")
        grant = (state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else None) or (approved.get("approval_grant") if isinstance(approved.get("approval_grant"), Mapping) else None)
        if not grant or not grant.get("consumed_at"):
            raise RuntimeError("APPROVAL_REVALIDATION_REQUIRED: one-shot approval grant is not consumed")
        if grant.get("consumed_at") and grant.get("approval_scope") != "ALLOW_ACTION_ONCE":
            raise RuntimeError("APPROVAL_SCOPE_UNSUPPORTED")

        boundary_identity = resolve_contract_identity(
            state,
            expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )

        def persisted_contract(bound_state: Mapping[str, Any]) -> ArchitectTaskContract:
            raw_contract = bound_state.get("contract")
            if not isinstance(raw_contract, Mapping) or not raw_contract:
                raise RuntimeError("INTEGRATION_CONTRACT_REQUIRED")
            contract_payload = {
                key: value for key, value in raw_contract.items() if key != "contract_hash"
            }
            try:
                replayed = ArchitectTaskContract.model_validate(contract_payload)
            except Exception as exc:
                raise RuntimeError("INTEGRATION_CONTRACT_INVALID") from exc
            computed_hash = replayed.contract_hash
            state_hash = str(bound_state.get("contract_hash") or "")
            identity_hash = str(boundary_identity.get("contract_hash") or "")
            bound_request = bound_state.get("request")
            workforce_projection_present = any(
                key in bound_state
                or (isinstance(bound_request, Mapping) and key in bound_request)
                for key in (
                    "workforce_demands",
                    "workforce_admission",
                    "canonical_dispatch_envelope",
                    "workforce_dispatch",
                )
            )
            if boundary_identity["contract_kind"] == ContractKind.TRACKED_TASK_CARD.value:
                # Legacy synthetic states without Workforce projections may
                # omit this identity.  Any real persisted dispatch requires a
                # complete, exact contract identity.
                if state_hash or identity_hash or workforce_projection_present:
                    if (
                        not re.fullmatch(r"[0-9a-f]{64}", state_hash)
                        or computed_hash != state_hash
                        or computed_hash != identity_hash
                    ):
                        raise RuntimeError("INTEGRATION_CONTRACT_BINDING_MISMATCH")
            else:
                # OWNER_INLINE uses the nested Owner Inline envelope as its
                # approval identity; still authenticate the persisted
                # operational contract against its own durable hash before
                # handing it to repository/integration gates.
                persisted_contract_hash = str(
                    bound_state.get("contract", {}).get("contract_hash") or ""
                )
                if (
                    not re.fullmatch(r"[0-9a-f]{64}", persisted_contract_hash)
                    or computed_hash != persisted_contract_hash
                ):
                    raise RuntimeError("INTEGRATION_CONTRACT_BINDING_MISMATCH")
            expected_binding_hash = (
                computed_hash
                if boundary_identity["contract_kind"] == ContractKind.TRACKED_TASK_CARD.value
                else identity_hash
            )
            if state_hash or identity_hash:
                for approval_binding in (
                    bound_state.get("integration_approval_grant"),
                    bound_state.get("integration_closure_binding"),
                ):
                    if isinstance(approval_binding, Mapping) and approval_binding.get("contract_hash"):
                        if str(approval_binding.get("contract_hash")) != expected_binding_hash:
                            raise RuntimeError("INTEGRATION_CONTRACT_BINDING_MISMATCH")
            if replayed.task_id != task_id:
                raise RuntimeError("INTEGRATION_CONTRACT_TASK_ID_MISMATCH")
            return replayed

        def persisted_workforce_coherence(
            bound_state: Mapping[str, Any],
            bound_contract: ArchitectTaskContract,
        ) -> None:
            """Check the recorded dispatch without re-evaluating admission."""
            bound_request = bound_state.get("request")
            if not isinstance(bound_request, Mapping):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            request_fields = {
                "demands": bound_request.get("workforce_demands"),
                "admission": bound_request.get("workforce_admission"),
                "canonical_dispatch_envelope": bound_request.get(
                    "canonical_dispatch_envelope"
                ),
            }
            request_projection_present = any(
                key in bound_request for key in (
                    "workforce_demands",
                    "workforce_admission",
                    "canonical_dispatch_envelope",
                )
            )
            state_projection_present = any(
                key in bound_state for key in (
                    "workforce_dispatch",
                    "canonical_dispatch_envelope",
                    "selected_worker_id",
                    "selected_provider",
                    "selected_model",
                    "workforce_policy_hash",
                    "workforce_binding_hash",
                    "workforce_aggregate_binding_hash",
                )
            )
            if not request_projection_present and not state_projection_present:
                if bound_state.get("execution_authority") == "WORKER_REGISTRY":
                    raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
                return
            if (
                not request_projection_present
                or any(value is None or not isinstance(value, Mapping) for value in request_fields.values())
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            persisted = bound_state.get("workforce_dispatch")
            state_envelope = bound_state.get("canonical_dispatch_envelope")
            if not isinstance(persisted, Mapping) or not isinstance(state_envelope, Mapping):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            for key, expected in request_fields.items():
                if persisted.get(key) != expected:
                    raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            if state_envelope != request_fields["canonical_dispatch_envelope"]:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            try:
                envelope = CanonicalDispatchEnvelope(**dict(state_envelope))
            except (TypeError, ValueError) as exc:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT") from exc
            raw_demands = request_fields["demands"].get("demands")
            if not isinstance(raw_demands, list) or len(raw_demands) != 1:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            demand = raw_demands[0]
            if not isinstance(demand, Mapping):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            envelope_identity = {
                "task_id": bound_state.get("task_id"),
                "attempt_id": bound_state.get("attempt_id"),
                "task_card_path": bound_state.get("task_card_path"),
                "task_card_hash": bound_state.get("task_card_hash"),
                "demand_id": demand.get("demand_id"),
            }
            if any(
                getattr(envelope, key) != value
                for key, value in envelope_identity.items()
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            if str(persisted.get("demand_id") or "") != envelope.demand_id:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            admission = request_fields["admission"]
            records = admission.get("records")
            policy_identity = admission.get("policy_identity")
            if (
                admission.get("overall_decision") != "ALLOW"
                or not isinstance(records, list)
                or len(records) != 1
                or not isinstance(records[0], Mapping)
                or not isinstance(policy_identity, Mapping)
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            record = records[0]
            decision = record.get("decision")
            record_request = record.get("request")
            if not isinstance(decision, Mapping) or not isinstance(record_request, Mapping):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            if (
                record.get("demand") != demand
                or str(record.get("binding_hash") or "") != str(persisted.get("binding_hash") or "")
                or str(admission.get("aggregate_binding_hash") or "")
                != str(persisted.get("aggregate_binding_hash") or "")
                or str(policy_identity.get("policy_hash") or "")
                != str(persisted.get("policy_hash") or "")
                or decision.get("decision") != "ALLOW"
                or str(decision.get("resolved_worker_id") or "")
                != str(persisted.get("worker_id") or "")
                or str(decision.get("resolved_provider") or "")
                != str(persisted.get("provider") or "")
                or str(decision.get("resolved_model") or "")
                != str(persisted.get("model") or "")
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            try:
                recorded_binding_hash = _sha256_json(
                    _binding_payload(
                        WorkforceDemand.from_dict(dict(demand)),
                        record_request,
                        decision,
                        policy_identity,
                    )
                )
                recorded_aggregate_hash = _sha256_json(
                    {
                        "policy_hash": str(policy_identity.get("policy_hash") or ""),
                        "record_hashes": [recorded_binding_hash],
                    }
                )
            except (TypeError, ValueError):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            if (
                recorded_binding_hash != str(record.get("binding_hash") or "")
                or recorded_aggregate_hash != str(admission.get("aggregate_binding_hash") or "")
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            allowed_providers = {
                str(provider)
                for provider in bound_contract.provider_order
                if str(provider).strip()
            }
            if bound_contract.preferred_provider:
                allowed_providers.add(str(bound_contract.preferred_provider))
            if bound_contract.fallback_provider:
                allowed_providers.add(str(bound_contract.fallback_provider))
            if str(persisted.get("provider") or "") not in allowed_providers:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            dispatch_fields = (
                ("worker_id", "selected_worker_id"),
                ("provider", "selected_provider"),
                ("model", "selected_model"),
                ("policy_hash", "workforce_policy_hash"),
                ("binding_hash", "workforce_binding_hash"),
                ("aggregate_binding_hash", "workforce_aggregate_binding_hash"),
            )
            for dispatch_key, state_key in dispatch_fields:
                dispatch_value = str(persisted.get(dispatch_key) or "")
                state_value = str(bound_state.get(state_key) or "")
                if not dispatch_value or dispatch_value != state_value:
                    raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            for key in (
                "worker_id", "provider", "model", "policy_hash", "binding_hash",
                "aggregate_binding_hash",
            ):
                if getattr(envelope, key) != str(persisted.get(key) or ""):
                    raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")

        # Integration replays the exact contract that was persisted and
        # independently verified at Candidate time.  Rebuilding from request
        # would re-run date-sensitive Workforce admission and invalidate an
        # otherwise valid historical ALLOW receipt.
        contract = persisted_contract(state)
        persisted_workforce_coherence(state, contract)
        current_universe = {
            "task_id": task_id,
            "campaign_id": str(state.get("campaign_id") or (state.get("contract") or {}).get("campaign_id") or authorization_obj.campaign_id),
            "task_card_hash": str(state.get("task_card_hash") or (state.get("contract") or {}).get("task_card_hash") or boundary_identity.get("task_card_hash") or authorization_obj.task_card_hash),
            "candidate_commit": str((state.get("promotion_packet") or {}).get("candidate_commit_sha") or authorization_obj.candidate_commit),
            "candidate_receipt_hash": str((state.get("promotion_packet") or {}).get("candidate_receipt_hash") or authorization_obj.candidate_receipt_hash),
            "acceptance_receipt_hash": acceptance_obj.receipt_hash,
            "canonical_root": str(authorization_obj.canonical_root),
            "canonical_branch": integration_branch,
            "expected_canonical_head": authorization_obj.expected_canonical_head,
            "canonical_dirty_baseline": str(authorization_obj.canonical_dirty_baseline),
            "integration_plan_hash": str(authorization_obj.integration_plan_hash),
            "cleanup_target_id": str((state.get("lease") or {}).get("target_id") or authorization_obj.cleanup_target_id),
            "cleanup_target_path": str((state.get("lease") or {}).get("target_path") or authorization_obj.cleanup_target_path),
            "durable_ref": str(state.get("candidate_ref") or authorization_obj.durable_ref),
            "attempt_id": str(state.get("attempt_id") or authorization_obj.attempt_id),
            "candidate_tree_sha": str((state.get("promotion_packet") or {}).get("candidate_tree_sha") or authorization_obj.candidate_tree_sha),
            "candidate_state_hash": str((state.get("promotion_packet") or {}).get("candidate_state_hash") or authorization_obj.candidate_state_hash),
            "reviewer_id": acceptance_obj.reviewer_id,
            "verifier_artifact_hash": str(authorization_obj.verifier_artifact_hash),
            "require_clean": authorization_obj.require_clean,
            "strategy": authorization_obj.strategy,
            "verification_commands_hash": authorization_obj.verification_commands_hash,
            "post_apply_commands_hash": authorization_obj.post_apply_commands_hash,
            "cleanup_requested": authorization_obj.cleanup_requested,
            "approval_scope": authorization_obj.approval_scope,
        }
        try:
            authorization_obj.validate_current(current_universe)
        except ValueError as exc:
            raise RuntimeError(f"INTEGRATION_AUTHORIZATION_EXPIRED: {exc}" if "expired" in str(exc) else f"INTEGRATION_AUTHORIZATION_DRIFT: {exc}") from exc
        protected_binding_fields = (
            "task_id",
            "attempt_id",
            "request",
            "contract",
            "promotion_packet",
            "verified_receipt",
            "approved_binding",
            "external_acceptance",
            "integration_authorization",
            "integration_approval_grant",
            "integration_closure_binding",
            "integration_closure_binding_hash",
            "integration_verifier_manifest",
            "controller_revision",
            "contract_kind",
            "contract_hash",
            "task_card_hash",
            "owner_inline_contract",
        )

        def binding_hash(bound_state: Mapping[str, Any]) -> str:
            payload = {
                key: _jsonable(bound_state.get(key)) for key in protected_binding_fields
            }
            return hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

        def repository_recheck(
            bound_state: Mapping[str, Any],
            bound_contract: ArchitectTaskContract,
        ) -> Any:
            packet = bound_state.get("promotion_packet") if isinstance(
                bound_state.get("promotion_packet"), Mapping
            ) else {}
            verified_receipt = bound_state.get("verified_receipt") if isinstance(
                bound_state.get("verified_receipt"), Mapping
            ) else {}
            expected_policy_revision_hash = str(
                verified_receipt.get("repository_contract_policy_revision_hash") or ""
            )
            if verified_receipt.get("repository_contract_gate_passed") is not True:
                raise RuntimeError(
                    "REPOSITORY_CONTRACT_RECHECK_REQUIRED: verified gate proof is missing"
                )
            if not re.fullmatch(r"[0-9a-f]{64}", expected_policy_revision_hash):
                raise RuntimeError(
                    "REPOSITORY_CONTRACT_RECHECK_REQUIRED: policy revision hash is missing"
                )
            result = RepositoryContractGate(
                WorktreeManager(bound_contract.target_worktree_root)
            ).evaluate_committed_candidate(
                contract=bound_contract,
                candidate_commit=str(packet.get("candidate_commit_sha") or ""),
                candidate_tree_sha=str(packet.get("candidate_tree_sha") or ""),
                expected_policy_revision_hash=expected_policy_revision_hash,
                architecture_approval=(bound_state.get("approved_binding") or {}).get("architecture_approval") if isinstance(bound_state.get("approved_binding"), Mapping) else None,
                task_id=str(bound_state.get("task_id") or task_id),
                attempt_id=str(bound_state.get("attempt_id") or ""),
            )
            if not result.passed:
                raise RuntimeError(
                    "REPOSITORY_CONTRACT_RECHECK_FAILED: "
                    + json.dumps(
                        list(result.blocking_reasons),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            return result

        approved_binding_hash = binding_hash(state)
        integration_recheck = repository_recheck(state, contract)

        self._checkpoint(
            task_id,
            "INTEGRATING",
            {
                "integration_branch": integration_branch,
                "push_performed": False,
                "repository_contract_integration_recheck": _jsonable(
                    integration_recheck
                ),
            },
            attempt_id=state.get("attempt_id"),
        )
        try:
            # Hold the lifecycle state lock across the final exact-tree recheck
            # and apply call so no formal state writer can change the approved
            # packet between proof and mutation.
            with self._state_lock():
                integrating = self._load_state_path(self._state_path(task_id), task_id)
                if integrating is None:
                    raise RuntimeError("INTEGRATION_STATE_MISSING_AT_APPLY_BOUNDARY")
                if binding_hash(integrating) != approved_binding_hash:
                    raise RuntimeError("INTEGRATION_BINDING_DRIFT_AT_APPLY_BOUNDARY")
                final_identity = resolve_contract_identity(
                    integrating,
                    expected_task_id=task_id,
                    expected_head=str(integrating.get("controller_revision") or ""),
                )
                if final_identity != boundary_identity:
                    raise RuntimeError("INTEGRATION_BINDING_DRIFT_AT_APPLY_BOUNDARY")
                final_contract = persisted_contract(integrating)
                persisted_workforce_coherence(integrating, final_contract)
                final_recheck = repository_recheck(integrating, final_contract)
                integrating["repository_contract_integration_recheck"] = _jsonable(
                    final_recheck
                )
                receipt = ControlledIntegrationManager(
                    integration_root=final_contract.controller_repo_root
                ).integrate_authorized_task_state(
                    integrating,
                    integration_branch=integration_branch,
                    staging_root=str(
                        integrating.get("integration_staging_root")
                        or (
                            Path(final_contract.target_worktree_root).parent
                            / ".nexus-integration-staging"
                        )
                    ),
                    apply=True,
                    post_apply_commands=tuple(
                        tuple(command)
                        for command in integrating.get("post_apply_commands") or ()
                    ),
                )
        except IntegrationExecutionError as exc:
            failed_status = (
                "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"
                if exc.merge_performed
                else "INTEGRATION_FAILED_PRE_APPLY"
            )
            integration_status = "APPLIED_NOT_VERIFIED" if exc.merge_performed else "NOT_APPLIED"
            self._checkpoint(
                task_id,
                failed_status,
                {
                    "status": failed_status,
                    "promotion_status": failed_status,
                    "integration_branch": integration_branch,
                    "integration_error": str(exc),
                    "integration_status": integration_status,
                    "integration_execution": {
                        "stage": exc.stage,
                        "branch_head_before": exc.branch_head_before,
                        "branch_head_after": exc.branch_head_after,
                        "staging_commit_sha": exc.staging_commit_sha,
                        "candidate_commit_sha": exc.candidate_commit_sha,
                        "candidate_is_ancestor": exc.merge_performed,
                        "merge_performed": exc.merge_performed,
                        "post_apply_verified": exc.post_apply_verified,
                        "failure_reason": exc.failure_reason,
                    },
                    "integration_result_sha": exc.integration_result_sha,
                    "terminal_status": failed_status,
                    "final_disposition": failed_status,
                    "state_retention_status": "ACTIONABLE",
                    "archive_eligible": False,
                    "cleanup_eligible": False,
                    "merge_performed": exc.merge_performed,
                    "push_performed": False,
                },
                attempt_id=state.get("attempt_id"),
            )
            raise
        except Exception as exc:
            self._checkpoint(
                task_id,
                "INTEGRATION_FAILED_PRE_APPLY",
                {
                    "status": "INTEGRATION_FAILED_PRE_APPLY",
                    "promotion_status": "INTEGRATION_FAILED_PRE_APPLY",
                    "integration_branch": integration_branch,
                    "integration_error": str(exc),
                    "integration_status": "NOT_APPLIED",
                    "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
                    "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
                    "state_retention_status": "ACTIONABLE",
                    "archive_eligible": False,
                    "cleanup_eligible": False,
                    "merge_performed": False,
                    "push_performed": False,
                },
                attempt_id=state.get("attempt_id"),
            )
            raise
        return self._record_integration(receipt, task_id=task_id)

    def recover_applied_integration_receipt(
        self,
        task_id: str,
        receipt: Any,
        *,
        runtime_identity: Mapping[str, Any],
        integration_branch: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record an externally witnessed apply without replaying integration."""
        from nexus.orchestrator.governed_integration import IntegrationReceipt

        if not isinstance(receipt, IntegrationReceipt):
            raise TypeError("receipt must be an IntegrationReceipt instance")
        if not isinstance(runtime_identity, Mapping):
            raise TypeError("runtime_identity must be a mapping")
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") in {
            "INTEGRATED",
            "INTEGRATED_AND_CLEANED",
            "INTEGRATED_TARGET_RETAINED",
        } and state.get("promotion_status") == "INTEGRATED":
            persisted_receipt = state.get("integration_receipt")
            if not isinstance(persisted_receipt, Mapping) or dict(persisted_receipt) != asdict(receipt):
                raise RuntimeError("receipt recovery idempotency receipt mismatch")
            return state
        if state.get("status") != "INTEGRATING" or state.get("promotion_status") != "INTEGRATING":
            raise RuntimeError("receipt recovery requires INTEGRATING state")
        if state.get("merge_performed") or state.get("integration_receipt") or state.get("integration_result_sha"):
            raise RuntimeError("receipt recovery requires an unrecorded applied state")
        if state.get("integration_execution"):
            raise RuntimeError("receipt recovery requires no persisted execution record")
        if not state.get("integration_recovery_only") and not (
            isinstance(state.get("integration_closure_binding"), Mapping)
            and state["integration_closure_binding"].get("recovery_only")
        ):
            raise RuntimeError("receipt recovery fence missing")
        closure = state.get("integration_closure_binding")
        if not isinstance(closure, Mapping):
            raise RuntimeError("receipt recovery closure binding missing")
        runtime_keys = (
            "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash",
            "lifecycle_revision", "server_instance_id", "contract_kind",
            "contract_hash", "task_card_hash", "owner_inline_contract",
        )
        trusted_runtime = closure.get("runtime_identity")
        if (
            not isinstance(trusted_runtime, Mapping)
            or any(key not in runtime_identity for key in runtime_keys)
            or dict(runtime_identity) != dict(trusted_runtime)
        ):
            raise RuntimeError("receipt recovery runtime identity mismatch")
        if receipt.task_id != task_id or not receipt.merge_performed or receipt.push_performed:
            raise RuntimeError("receipt recovery physical binding mismatch")
        if not receipt.verifier_passed or not receipt.post_apply_verified:
            raise RuntimeError("receipt recovery requires verified apply evidence")
        if receipt.staging_commit_sha != receipt.integration_commit_sha:
            raise RuntimeError("receipt recovery requires the verified staging commit")

        contract_data = state.get("contract")
        if not isinstance(contract_data, Mapping) or not contract_data:
            raise RuntimeError("INTEGRATION_CONTRACT_REQUIRED")
        contract_payload = {key: value for key, value in contract_data.items() if key != "contract_hash"}
        try:
            contract = ArchitectTaskContract.model_validate(contract_payload)
        except Exception as exc:
            raise RuntimeError("INTEGRATION_CONTRACT_INVALID") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", str(state.get("contract_hash") or "")):
            raise RuntimeError("INTEGRATION_CONTRACT_BINDING_MISMATCH")
        if contract.contract_hash != state.get("contract_hash"):
            raise RuntimeError("INTEGRATION_CONTRACT_BINDING_MISMATCH")

        request = state.get("request")
        dispatch = state.get("workforce_dispatch")
        projection_present = any(
            key in state or (isinstance(request, Mapping) and key in request)
            for key in ("workforce_demands", "workforce_admission", "canonical_dispatch_envelope", "workforce_dispatch")
        )
        if (
            state.get("execution_authority") == "WORKER_REGISTRY"
            and not projection_present
        ):
            raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
        if projection_present:
            if not isinstance(request, Mapping) or not isinstance(dispatch, Mapping):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            if (
                request.get("workforce_demands") != dispatch.get("demands")
                or request.get("workforce_admission") != dispatch.get("admission")
                or request.get("canonical_dispatch_envelope") != dispatch.get("canonical_dispatch_envelope")
                or state.get("canonical_dispatch_envelope") != dispatch.get("canonical_dispatch_envelope")
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            envelope_data = dispatch.get("canonical_dispatch_envelope")
            try:
                envelope = CanonicalDispatchEnvelope(**dict(envelope_data))
            except Exception as exc:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT") from exc
            if envelope.task_id != task_id or envelope.attempt_id != str(state.get("attempt_id") or ""):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            demands_data = dispatch.get("demands")
            admission = dispatch.get("admission")
            records = admission.get("records") if isinstance(admission, Mapping) else None
            demand_list = demands_data.get("demands") if isinstance(demands_data, Mapping) else None
            if (
                not isinstance(admission, Mapping)
                or admission.get("overall_decision") != "ALLOW"
                or not isinstance(records, list)
                or len(records) != 1
                or not isinstance(demand_list, list)
                or len(demand_list) != 1
                or records[0].get("demand") != demand_list[0]
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")
            record = records[0]
            try:
                expected_binding = _sha256_json(_binding_payload(
                    WorkforceDemand.from_dict(record["demand"]),
                    record["request"], record["decision"], admission["policy_identity"],
                ))
                expected_aggregate = _sha256_json({
                    "policy_hash": admission["policy_identity"]["policy_hash"],
                    "record_hashes": [expected_binding],
                })
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT") from exc
            if (
                record.get("binding_hash") != expected_binding
                or admission.get("aggregate_binding_hash") != expected_aggregate
                or envelope.binding_hash != expected_binding
                or envelope.aggregate_binding_hash != expected_aggregate
                or (state.get("selected_worker_id"), state.get("selected_provider"), state.get("selected_model"))
                != (envelope.worker_id, envelope.provider, envelope.model)
                or (dispatch.get("worker_id"), dispatch.get("provider"), dispatch.get("model"))
                != (envelope.worker_id, envelope.provider, envelope.model)
                or envelope.provider not in {str(contract.preferred_provider or ""), *[str(p) for p in contract.provider_order]}
            ):
                raise RuntimeError("INTEGRATION_WORKFORCE_DISPATCH_DRIFT")

        authorization = state.get("integration_authorization")
        acceptance = state.get("external_acceptance")
        if not isinstance(closure, Mapping) or not isinstance(authorization, Mapping) or not isinstance(acceptance, Mapping):
            raise RuntimeError("receipt recovery persisted approval/acceptance binding missing")
        grant = state.get("integration_approval_grant")
        if not isinstance(grant, Mapping) or not grant.get("consumed_at"):
            raise RuntimeError("receipt recovery consumed integration approval missing")
        closure_payload = {key: value for key, value in closure.items() if key != "binding_hash"}
        closure_hash = hashlib.sha256(json.dumps(
            closure_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()).hexdigest()
        if closure.get("binding_hash") != closure_hash:
            raise RuntimeError("receipt recovery closure binding drift")
        rebound_applied_head = closure.get("expected_canonical_head")
        if (
            not isinstance(rebound_applied_head, str)
            or not re.fullmatch(r"[0-9a-f]{40}", rebound_applied_head)
            or not isinstance(receipt.integration_commit_sha, str)
            or receipt.integration_commit_sha != rebound_applied_head
        ):
            raise RuntimeError("receipt recovery commit does not match rebound applied head")
        try:
            authorization_obj = IntegrationAuthorizationEnvelope(**{
                key: value for key, value in authorization.items() if key != "authorization_hash"
            })
        except Exception as exc:
            raise RuntimeError("receipt recovery authorization invalid") from exc
        if authorization.get("authorization_hash") != authorization_obj.authorization_hash:
            raise RuntimeError("receipt recovery authorization drift")
        current_identity = resolve_contract_identity(
            state, expected_task_id=task_id,
            expected_head=str(state.get("controller_revision") or ""),
        )
        if any(runtime_identity.get(key) != current_identity.get(key) for key in (
            "contract_kind", "contract_hash", "task_card_hash", "owner_inline_contract"
        )):
            raise RuntimeError("receipt recovery runtime identity mismatch")
        expected_fields = {
            "task_id": task_id,
            "attempt_id": state.get("attempt_id"),
            "candidate_commit": closure.get("candidate_commit_sha"),
            "candidate_tree_sha": closure.get("candidate_tree_sha"),
            "candidate_state_hash": closure.get("candidate_state_hash"),
            "candidate_receipt_hash": closure.get("verified_receipt_hash"),
            "acceptance_receipt_hash": acceptance.get("receipt_hash"),
            "task_card_hash": state.get("task_card_hash"),
            "canonical_branch": closure.get("canonical_branch"),
            "expected_canonical_head": closure.get("expected_canonical_head"),
        }
        if any(getattr(authorization_obj, key) != value for key, value in expected_fields.items()):
            raise RuntimeError("receipt recovery authorization binding mismatch")
        if grant.get("contract_hash") != state.get("contract_hash") or grant.get("task_card_hash") != state.get("task_card_hash"):
            raise RuntimeError("receipt recovery approval binding mismatch")
        if grant.get("bound_task_id") != task_id or grant.get("bound_attempt_id") != state.get("attempt_id"):
            raise RuntimeError("receipt recovery approval binding mismatch")
        if grant.get("bound_action_type") != LifecycleActionType.CANDIDATE_INTEGRATE.value or grant.get("approval_scope") != "ALLOW_ACTION_ONCE":
            raise RuntimeError("receipt recovery approval binding mismatch")
        for grant_key, persisted_key in (
            ("candidate_commit_sha", "candidate_commit_sha"),
            ("candidate_tree_sha", "candidate_tree_sha"),
            ("candidate_state_hash", "candidate_state_hash"),
            ("verified_receipt_hash", "verified_receipt_hash"),
            ("acceptance_receipt_hash", "receipt_hash"),
        ):
            if grant.get(grant_key) != (closure.get(persisted_key) if persisted_key != "receipt_hash" else acceptance.get(persisted_key)):
                raise RuntimeError("receipt recovery approval binding mismatch")
        expires_at = _parse_time(str(grant.get("expires_at") or ""))
        if expires_at is None or expires_at <= datetime.now(timezone.utc).timestamp():
            raise RuntimeError("receipt recovery approval expired or malformed")
        artifact_path = acceptance.get("verifier_artifact")
        if not isinstance(artifact_path, str) or not artifact_path:
            raise RuntimeError("receipt recovery acceptance artifact missing")
        try:
            artifact_hash = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError("receipt recovery acceptance artifact unreadable") from exc
        if artifact_hash != str(acceptance.get("receipt_hash") or ""):
            raise RuntimeError("receipt recovery acceptance artifact drift")
        if receipt.acceptance_receipt_hash != acceptance.get("receipt_hash"):
            raise RuntimeError("integration receipt acceptance binding mismatch")
        if receipt.authorization_hash != authorization.get("authorization_hash"):
            raise RuntimeError("integration receipt authorization binding mismatch")
        if receipt.candidate_commit_sha != closure.get("candidate_commit_sha"):
            raise RuntimeError("receipt candidate_commit_sha does not match persisted closure")
        for receipt_key, persisted_key in (
            ("candidate_tree_sha", "candidate_tree_sha"),
            ("candidate_state_hash", "candidate_state_hash"),
            ("verified_receipt_hash", "verified_receipt_hash"),
            ("task_card_hash", "task_card_hash"),
        ):
            if getattr(receipt, receipt_key) != closure.get(persisted_key):
                raise RuntimeError("receipt recovery candidate binding mismatch")
        branch = integration_branch or state.get("integration_branch") or closure.get("canonical_branch")
        if receipt.integration_branch != branch:
            raise RuntimeError("receipt integration branch mismatch")
        acceptance_obj = ExternalAcceptanceReceipt(**acceptance)
        current_universe = {
            "task_id": task_id,
            "campaign_id": str((request or {}).get("campaign_id") or authorization_obj.campaign_id) if isinstance(request, Mapping) else authorization_obj.campaign_id,
            "task_card_hash": str(state.get("task_card_hash") or ""),
            "candidate_commit": str((state.get("promotion_packet") or {}).get("candidate_commit_sha") or ""),
            "candidate_receipt_hash": str((state.get("promotion_packet") or {}).get("verified_receipt_hash") or ""),
            "acceptance_receipt_hash": acceptance_obj.receipt_hash,
            "canonical_root": str(authorization_obj.canonical_root),
            "canonical_branch": branch,
            "expected_canonical_head": authorization_obj.expected_canonical_head,
            "canonical_dirty_baseline": str(authorization_obj.canonical_dirty_baseline),
            "integration_plan_hash": str(authorization_obj.integration_plan_hash),
            "cleanup_target_id": str(authorization_obj.cleanup_target_id),
            "cleanup_target_path": str(authorization_obj.cleanup_target_path),
            "durable_ref": str(state.get("candidate_ref") or ""),
            "attempt_id": str(state.get("attempt_id") or ""),
            "candidate_tree_sha": str((state.get("promotion_packet") or {}).get("candidate_tree_sha") or ""),
            "candidate_state_hash": str((state.get("promotion_packet") or {}).get("candidate_state_hash") or ""),
            "reviewer_id": acceptance_obj.reviewer_id,
            "verifier_artifact_hash": str(authorization_obj.verifier_artifact_hash),
            "require_clean": authorization_obj.require_clean,
            "strategy": authorization_obj.strategy,
            "verification_commands_hash": authorization_obj.verification_commands_hash,
            "post_apply_commands_hash": authorization_obj.post_apply_commands_hash,
            "cleanup_requested": authorization_obj.cleanup_requested,
            "approval_scope": authorization_obj.approval_scope,
        }
        try:
            authorization_obj.validate_current(current_universe)
        except ValueError as exc:
            raise RuntimeError("receipt recovery authorization is not current") from exc
        controller_root = Path(contract.controller_repo_root).resolve()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)
        candidate = closure.get("candidate_commit_sha")
        # A separate detached Controller (#2251) applied by update-ref: the
        # applied head is the integration branch ref, HEAD stays detached and
        # only untracked pending Task Cards are admitted.  Read-only probe on
        # the real class (never an integration run); other shapes unchanged.
        from nexus.orchestrator.governed_integration import (
            ControlledIntegrationManager as ControllerShape,
        )

        separate_head = ControllerShape.separate_controller_integration_head(
            controller_root, str(branch)
        )
        actual_head = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
        if separate_head is not None:
            actual_head = separate_head
        if actual_head != receipt.integration_commit_sha:
            raise RuntimeError("receipt recovery applied HEAD mismatch")
        if receipt.integration_commit_sha != candidate:
            parents = manager._run_git(
                ["rev-list", "--parents", "-n", "1", receipt.integration_commit_sha],
                cwd=controller_root,
            ).split()
            if len(parents) != 3 or candidate not in parents[1:]:
                raise RuntimeError("receipt recovery refuses post-candidate extra commit")
        expected_current_branch = "" if separate_head is not None else branch
        if (
            manager._run_git(["branch", "--show-current"], cwd=controller_root)
            != expected_current_branch
        ):
            raise RuntimeError("receipt recovery branch mismatch")
        if separate_head is not None:
            ControllerShape._require_clean_controller(
                controller_root,
                allow_pending_task_cards=True,
                message="receipt recovery canonical tree is dirty",
            )
        elif manager._run_git(
            ["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root
        ):
            raise RuntimeError("receipt recovery canonical tree is dirty")
        if candidate:
            candidate_tree = manager._run_git(["rev-parse", f"{candidate}^{{tree}}"], cwd=controller_root)
            if candidate_tree != receipt.candidate_tree_sha:
                raise RuntimeError("receipt recovery candidate tree mismatch")
            actual_tree = manager._run_git(["rev-parse", "HEAD^{tree}"], cwd=controller_root)
            if separate_head is not None:
                actual_tree = manager._run_git(
                    ["rev-parse", f"{separate_head}^{{tree}}"], cwd=controller_root
                )
            if actual_tree != receipt.candidate_tree_sha:
                raise RuntimeError("receipt recovery applied tree mismatch")
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", str(candidate), receipt.integration_commit_sha],
                cwd=controller_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError("receipt recovery result does not contain candidate")
        return self._record_integration(receipt, task_id=task_id)

    def retry_integration(self, task_id: str, *, integration_branch: Optional[str] = None) -> dict[str, Any]:
        """Retry only the integration phase after a non-merge integration failure."""
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("integration_recovery_only") or (
            isinstance(state.get("integration_closure_binding"), Mapping)
            and state["integration_closure_binding"].get("recovery_only")
        ):
            raise RuntimeError("INTEGRATION_RECOVERY_ONLY")
        if state.get("merge_performed") or state.get("status") == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY":
            raise RuntimeError("INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN")
        if state.get("status") not in {"INTEGRATION_FAILED", "INTEGRATION_FAILED_PRE_APPLY"} or not state.get("approved_binding"):
            raise RuntimeError("integration retry requires the original approved binding")
        branch = integration_branch or state.get("integration_branch") or "nexus/integration/main"
        self._checkpoint(
            task_id,
            "INTEGRATING",
            {"integration_branch": branch, "integration_retry": True, "push_performed": False},
            attempt_id=state.get("attempt_id"),
        )
        return self.integrate_approved(task_id, integration_branch=str(branch))

    def correct_applied_integration_receipt(
        self,
        task_id: str,
        *,
        expected_state_hash: str,
        original_receipt_hash: str,
        attempt_id: str,
        candidate_commit_sha: str,
        candidate_tree_sha: str,
        acceptance_receipt_hash: str,
        approval: Mapping[str, Any],
        authorization: Mapping[str, Any],
        runtime_identity: Mapping[str, Any],
        closure_binding: Mapping[str, Any],
        integration_branch: str,
        expected_applied_head: str,
        corrected_base_sha: str,
        reason: str = "RECOVERY_BASE_MISBOUND_TO_APPLIED_HEAD",
    ) -> dict[str, Any]:
        """CAS-correct only the base fields of an already-applied receipt.

        This is an append-only evidence repair.  It never invokes a provider,
        admission, integration manager, or ref update; all physical facts are
        re-read while holding the lifecycle state lock.
        """
        if reason != "RECOVERY_BASE_MISBOUND_TO_APPLIED_HEAD":
            raise RuntimeError("RECEIPT_CORRECTION_REASON_UNSUPPORTED")
        if not isinstance(approval, Mapping) or not isinstance(authorization, Mapping):
            raise TypeError("approval and authorization must be mappings")
        if not isinstance(runtime_identity, Mapping) or not isinstance(closure_binding, Mapping):
            raise TypeError("runtime_identity and closure_binding must be mappings")

        def canonical_hash(value: Any) -> str:
            return hashlib.sha256(json.dumps(
                _jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()).hexdigest()

        def reject(code: str) -> None:
            raise RuntimeError(code)

        state_path = self._state_path(task_id)
        try:
            prelock_state_hash = hashlib.sha256(state_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError("RECEIPT_CORRECTION_STATE_REQUIRED") from exc
        if str(expected_state_hash) != prelock_state_hash:
            reject("RECEIPT_CORRECTION_STATE_BINDING_MISMATCH")
        with self._state_lock():
            try:
                locked_state_bytes = state_path.read_bytes()
            except OSError as exc:
                raise RuntimeError("RECEIPT_CORRECTION_STATE_REQUIRED") from exc
            if hashlib.sha256(locked_state_bytes).hexdigest() != str(expected_state_hash):
                reject("RECEIPT_CORRECTION_STATE_CAS_DRIFT")
            state = self._load_state_path(state_path, task_id)
            if state is None:
                raise KeyError(f"unknown task_id: {task_id}")
            if (
                state.get("status") != "INTEGRATED"
                or state.get("promotion_status") != "INTEGRATED"
                or state.get("integration_recovery_only") is not True
            ):
                reject("RECEIPT_CORRECTION_RECOVERY_STATE_REQUIRED")
            raw_receipt = state.get("integration_receipt")
            if not isinstance(raw_receipt, Mapping):
                reject("RECEIPT_CORRECTION_RECEIPT_REQUIRED")
            persisted_hash = canonical_hash(raw_receipt)
            history = state.get("integration_receipt_correction_history")
            if history is not None and not isinstance(history, list):
                reject("RECEIPT_CORRECTION_HISTORY_INVALID")
            history = list(history or [])
            packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
            if state.get("task_id") != task_id or str(state.get("attempt_id") or "") != str(attempt_id):
                reject("RECEIPT_CORRECTION_ATTEMPT_BINDING_MISMATCH")
            if state.get("merge_performed") is not True or state.get("integration_result_sha") != expected_applied_head:
                reject("RECEIPT_CORRECTION_EFFECT_BINDING_MISMATCH")
            replay = bool(history and history[-1].get("original_receipt_hash") == original_receipt_hash)
            if str(original_receipt_hash) != persisted_hash and not replay:
                reject("RECEIPT_CORRECTION_RECEIPT_BINDING_MISMATCH")
            if str(raw_receipt.get("task_id") or "") != task_id:
                reject("RECEIPT_CORRECTION_RECEIPT_BINDING_MISMATCH")
            lease = state.get("lease") if isinstance(state.get("lease"), Mapping) else {}
            expected_source_branch = str(
                lease.get("target_branch") or state.get("source_branch") or ""
            )
            receipt_schema = raw_receipt.get("schema")
            legacy_receipt_schema = "nexus.integration_receipt/v1"
            if (
                receipt_schema not in {"nexus.integration_receipt.v1", legacy_receipt_schema}
                or not expected_source_branch
                or raw_receipt.get("source_branch") != expected_source_branch
                or raw_receipt.get("worktree_removed") is not False
                or raw_receipt.get("failure_reason") is not None
                or raw_receipt.get("post_apply_error") is not None
            ):
                reject("RECEIPT_CORRECTION_RECEIPT_SHAPE_INVALID")
            expected_fields = {
                "candidate_commit_sha": candidate_commit_sha,
                "candidate_tree_sha": candidate_tree_sha,
                "candidate_state_hash": packet.get("candidate_state_hash"),
                "verified_receipt_hash": packet.get("verified_receipt_hash"),
                "acceptance_receipt_hash": acceptance_receipt_hash,
                "authorization_hash": authorization.get("authorization_hash"),
                "task_card_hash": state.get("task_card_hash"),
                "integration_branch": integration_branch,
                "integration_commit_sha": expected_applied_head,
                "staging_commit_sha": expected_applied_head,
                "branch_head_after": expected_applied_head,
            }
            receipt_fields = {
                key: raw_receipt.get(key) for key in expected_fields
            }
            if any(receipt_fields[key] != value for key, value in expected_fields.items()):
                reject("RECEIPT_CORRECTION_RECEIPT_BINDING_MISMATCH")
            if raw_receipt.get("merge_performed") is not True or raw_receipt.get("push_performed") is not False:
                reject("RECEIPT_CORRECTION_EFFECT_BINDING_MISMATCH")
            if (
                raw_receipt.get("verifier_passed") is not True
                or raw_receipt.get("post_apply_verified") is not True
                or raw_receipt.get("candidate_is_ancestor") is not True
                or raw_receipt.get("staging_verified") is not True
                or state.get("integration_result_sha") != expected_applied_head
            ):
                reject("RECEIPT_CORRECTION_EFFECT_BINDING_MISMATCH")

            persisted_approval = state.get("integration_approval_grant")
            persisted_authorization = state.get("integration_authorization")
            persisted_closure = state.get("integration_closure_binding")
            if not isinstance(persisted_approval, Mapping) or dict(approval) != dict(persisted_approval):
                reject("RECEIPT_CORRECTION_APPROVAL_BINDING_MISMATCH")
            if not isinstance(persisted_authorization, Mapping) or dict(authorization) != dict(persisted_authorization):
                reject("RECEIPT_CORRECTION_AUTHORIZATION_BINDING_MISMATCH")
            try:
                authorization_obj = IntegrationAuthorizationEnvelope(**{
                    key: value for key, value in persisted_authorization.items()
                    if key != "authorization_hash"
                })
            except Exception as exc:
                raise RuntimeError("RECEIPT_CORRECTION_AUTHORIZATION_INVALID") from exc
            if persisted_authorization.get("authorization_hash") != authorization_obj.authorization_hash:
                reject("RECEIPT_CORRECTION_AUTHORIZATION_HASH_MISMATCH")
            if not isinstance(persisted_closure, Mapping) or dict(closure_binding) != dict(persisted_closure):
                reject("RECEIPT_CORRECTION_CLOSURE_BINDING_MISMATCH")
            closure_payload = {
                key: value for key, value in persisted_closure.items()
                if key != "binding_hash"
            }
            if persisted_closure.get("binding_hash") != canonical_hash(closure_payload):
                reject("RECEIPT_CORRECTION_CLOSURE_HASH_MISMATCH")
            if persisted_closure.get("authorization_hash") != persisted_authorization.get("authorization_hash"):
                reject("RECEIPT_CORRECTION_AUTHORIZATION_CLOSURE_MISMATCH")
            if dict(runtime_identity) != dict(persisted_closure.get("runtime_identity") or {}):
                reject("RECEIPT_CORRECTION_RUNTIME_BINDING_MISMATCH")
            if persisted_closure.get("candidate_commit_sha") not in (None, candidate_commit_sha):
                reject("RECEIPT_CORRECTION_CLOSURE_BINDING_MISMATCH")
            for key, expected in {
                "candidate_tree_sha": candidate_tree_sha,
                "candidate_state_hash": packet.get("candidate_state_hash"),
                "verified_receipt_hash": packet.get("verified_receipt_hash"),
                "acceptance_receipt_hash": acceptance_receipt_hash,
                "task_card_hash": state.get("task_card_hash"),
                "canonical_branch": integration_branch,
            }.items():
                if persisted_closure.get(key) != expected:
                    raise RuntimeError(
                        "RECEIPT_CORRECTION_CLOSURE_BINDING_MISMATCH: "
                        f"{key} expected={expected!r} actual={persisted_closure.get(key)!r}"
                    )
            for key, expected in {
                "task_id": task_id,
                "candidate_commit": candidate_commit_sha,
                "candidate_tree_sha": candidate_tree_sha,
                "candidate_state_hash": packet.get("candidate_state_hash"),
                "candidate_receipt_hash": packet.get("verified_receipt_hash"),
                "acceptance_receipt_hash": acceptance_receipt_hash,
                "task_card_hash": state.get("task_card_hash"),
                "canonical_branch": integration_branch,
            }.items():
                if getattr(authorization_obj, key, None) != expected:
                    raise RuntimeError(
                        "RECEIPT_CORRECTION_AUTHORIZATION_BINDING_MISMATCH: "
                        f"{key} expected={expected!r} actual={getattr(authorization_obj, key, None)!r}"
                    )
            if str(persisted_closure.get("recovery_pre_apply_head") or "") != str(corrected_base_sha):
                reject("RECEIPT_CORRECTION_CLOSURE_BINDING_MISMATCH")

            manager = WorktreeManager(root_dir=str((state.get("contract") or {}).get("controller_repo_root") or ""))
            controller_root = Path((state.get("contract") or {}).get("controller_repo_root") or "").resolve()
            if not controller_root.is_dir():
                reject("RECEIPT_CORRECTION_CONTROLLER_ROOT_REQUIRED")
            # A separate detached Controller (#2251) binds the integration
            # ref with HEAD detached and only pending Task Cards untracked.
            from nexus.orchestrator.governed_integration import (
                ControlledIntegrationManager as ControllerShape,
            )

            try:
                separate_head = ControllerShape.separate_controller_integration_head(
                    controller_root, integration_branch
                )
            except RuntimeError as exc:
                raise RuntimeError("RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH") from exc
            actual_branch = manager._run_git(["branch", "--show-current"], cwd=controller_root)
            actual_head = manager._run_git(["rev-parse", "HEAD"], cwd=controller_root)
            if separate_head is not None:
                try:
                    ControllerShape._require_clean_controller(
                        controller_root,
                        allow_pending_task_cards=True,
                        message="RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH",
                    )
                except RuntimeError as exc:
                    raise RuntimeError("RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH") from exc
                if actual_branch != "" or separate_head != expected_applied_head:
                    reject("RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH")
            else:
                dirty = manager._run_git(
                    ["status", "--porcelain=v1", "--untracked-files=all"], cwd=controller_root
                )
                if (
                    actual_branch != integration_branch
                    or actual_head != expected_applied_head
                    or dirty
                ):
                    reject("RECEIPT_CORRECTION_PHYSICAL_BINDING_MISMATCH")
            candidate_tree = manager._run_git(["rev-parse", f"{candidate_commit_sha}^{{tree}}"], cwd=controller_root)
            if candidate_tree != candidate_tree_sha:
                reject("RECEIPT_CORRECTION_CANDIDATE_TREE_MISMATCH")
            parents = manager._run_git(["rev-list", "--parents", "-n", "1", expected_applied_head], cwd=controller_root).split()[1:]
            if set(parents) != {candidate_commit_sha, corrected_base_sha} or len(parents) != 2:
                reject("CORRECTION_APPLIED_TOPOLOGY_REQUIRED")

            if replay:
                last = history[-1]
                effective = last.get("effective_receipt_hash")
                if effective == canonical_hash(raw_receipt):
                    return {**state, "duplicate": True}
                reject("RECEIPT_CORRECTION_REPLAY_DRIFT")
            if history:
                reject("RECEIPT_CORRECTION_REPLAY_DRIFT")

            corrected = dict(raw_receipt)
            corrected["integration_base_sha"] = corrected_base_sha
            corrected["branch_head_before"] = corrected_base_sha
            schema_delta = receipt_schema == legacy_receipt_schema
            if schema_delta:
                # A durable recovery receipt was emitted by the historical
                # slash-schema writer.  Accept that exact legacy identity only
                # for this recovery correction and canonicalize the effective
                # receipt; it is never silently treated as a v1-equivalent
                # receipt by other lifecycle paths.
                corrected["schema"] = "nexus.integration_receipt.v1"
            allowed_mutations = {"integration_base_sha", "branch_head_before"}
            if schema_delta:
                allowed_mutations.add("schema")
            if any(corrected[key] != raw_receipt[key] for key in corrected if key not in allowed_mutations):
                reject("RECEIPT_CORRECTION_MUTATION_SCOPE")
            entry = {
                "schema": "nexus.integration_receipt_correction.v1",
                "reason": reason,
                "task_id": task_id,
                "attempt_id": attempt_id,
                "original_receipt_hash": original_receipt_hash,
                "original_receipt": dict(raw_receipt),
                "effective_receipt_hash": canonical_hash(corrected),
                "corrected_base_sha": corrected_base_sha,
                "candidate_commit_sha": candidate_commit_sha,
                "candidate_tree_sha": candidate_tree_sha,
                "correction_deltas": {
                    "schema": {
                        "from": raw_receipt.get("schema"),
                        "to": corrected.get("schema"),
                    },
                    "integration_base_sha": {
                        "from": raw_receipt.get("integration_base_sha"),
                        "to": corrected_base_sha,
                    },
                    "branch_head_before": {
                        "from": raw_receipt.get("branch_head_before"),
                        "to": corrected_base_sha,
                    },
                },
            }
            state["integration_receipt"] = corrected
            state["integration_base_sha"] = corrected_base_sha
            state["integration_receipt_correction_history"] = [*history, entry]
            self._write_state_locked(task_id, state)
            return {**state, "duplicate": False}

    # Compatibility spelling for callers that use the shorter public name.
    correct_integration_receipt = correct_applied_integration_receipt

    def _record_integration(
        self,
        receipt: Any,
        *,
        task_id: Optional[str] = None,
    ) -> dict[str, Any]:
        from nexus.orchestrator.governed_integration import IntegrationReceipt
        if not isinstance(receipt, IntegrationReceipt):
            raise TypeError("receipt must be an IntegrationReceipt instance")
        rec_task_id = getattr(receipt, "task_id", None) or task_id
        if not rec_task_id:
            raise KeyError("unknown task_id")
        task_id = rec_task_id
        state = self._read_state(task_id)
        if state is None:
            raise KeyError(f"unknown task_id: {task_id}")
        if state.get("status") not in {"APPROVED", "INTEGRATING"}:
            raise RuntimeError("task status must be APPROVED or INTEGRATING to record integration")
        if not receipt.verifier_passed:
            raise RuntimeError("integration receipt verifier_passed must be True")
        if not receipt.merge_performed:
            raise RuntimeError("integration receipt merge_performed must be True")
        if receipt.push_performed:
            raise RuntimeError("integration receipt push_performed must be False")
        if not getattr(receipt, "post_apply_verified", False):
            raise RuntimeError("post-apply verification is required before integration recording")
        if getattr(receipt, "staging_commit_sha", None) != receipt.integration_commit_sha:
            raise RuntimeError("integration result must equal the verified staging commit")
        acceptance_state = state.get("external_acceptance") if isinstance(state.get("external_acceptance"), Mapping) else {}
        authorization_state = state.get("integration_authorization") if isinstance(state.get("integration_authorization"), Mapping) else {}
        if acceptance_state or authorization_state:
            if getattr(receipt, "acceptance_receipt_hash", None) != acceptance_state.get("receipt_hash"):
                raise RuntimeError("integration receipt acceptance binding mismatch")
            if getattr(receipt, "authorization_hash", None) != authorization_state.get("authorization_hash"):
                raise RuntimeError("integration receipt authorization binding mismatch")

        packet = state.get("promotion_packet") or {"candidate_commit_sha": receipt.integration_commit_sha}
        binding = state.get("approved_binding") or packet
        if not binding or not packet:
            raise RuntimeError("exact approved binding is required for integration recording")
        binding_fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
        if state.get("approved_binding") and any(binding.get(f) != packet.get(f) for f in binding_fields):
            raise RuntimeError("approved binding mismatch")
        rcpt_cand_sha = getattr(receipt, "candidate_commit_sha", None)
        if rcpt_cand_sha and rcpt_cand_sha != binding.get("candidate_commit_sha"):
            raise RuntimeError("receipt candidate_commit_sha does not match approved binding")

        c_dict = state.get("contract")
        if not isinstance(c_dict, Mapping) or not c_dict:
            raise RuntimeError("INTEGRATION_CONTRACT_REQUIRED")
        contract_payload = {
            key: value for key, value in c_dict.items() if key != "contract_hash"
        }
        try:
            contract = ArchitectTaskContract.model_validate(contract_payload)
        except Exception as exc:
            raise RuntimeError("INTEGRATION_CONTRACT_INVALID") from exc
        computed_contract_hash = contract.contract_hash
        persisted_contract_hash = str(state.get("contract_hash") or "")
        if persisted_contract_hash and computed_contract_hash != persisted_contract_hash:
            raise RuntimeError("INTEGRATION_CONTRACT_BINDING_MISMATCH")
        controller_root = Path(contract.controller_repo_root).resolve()
        manager = WorktreeManager(root_dir=contract.target_worktree_root)

        try:
            actual = manager._run_git(["rev-parse", "--verify", f"{receipt.integration_commit_sha}^{{commit}}"], cwd=controller_root)
            if actual != receipt.integration_commit_sha:
                raise RuntimeError("integration result sha not present in controller")
            candidate_sha = binding.get("candidate_commit_sha")
            if candidate_sha:
                res = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", candidate_sha, receipt.integration_commit_sha],
                    cwd=controller_root,
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    raise RuntimeError("integration result commit does not contain candidate commit")
        except Exception as exc:
            if not self.ephemeral:
                raise RuntimeError(f"integration result SHA verification failed: {exc}")

        updates = {
            "candidate_commit_sha": binding.get("candidate_commit_sha"),
            "candidate_tree_sha": binding.get("candidate_tree_sha"),
            "candidate_state_hash": binding.get("candidate_state_hash"),
            "verified_receipt_hash": binding.get("verified_receipt_hash"),
            "candidate_ref": state.get("candidate_ref") or f"refs/heads/nexus/task/{task_id}",
            "approved_binding": binding,
            "integration_branch": receipt.integration_branch,
            "integration_base_sha": receipt.integration_base_sha,
            "integration_result_sha": receipt.integration_commit_sha,
            "integration_receipt": asdict(receipt),
            "candidate_status": "INTEGRATED",
            "promotion_status": "INTEGRATED",
            "terminal_status": "INTEGRATED",
            "final_disposition": "INTEGRATED",
            "status": "INTEGRATED",
            "merge_performed": True,
            "push_performed": False,
            "state_retention_status": "TERMINAL",
            "archive_eligible": True,
        }
        res = self._checkpoint(task_id, "INTEGRATED", updates, attempt_id=state.get("attempt_id"))
        return res or self._read_state(task_id) or state
