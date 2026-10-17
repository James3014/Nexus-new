"""Single GPT-visible MCP gateway for bounded Nexus workspace/lifecycle actions.

The gateway deliberately exposes a small public surface.  The existing
29-action self-hosted server remains an internal lifecycle provider; callers
must not need to know its Target paths or internal action names.
"""

from __future__ import annotations

import ast
import copy
import difflib
import hashlib
import importlib
import json
import os
import re
import select  # noqa: F401 - kept on the facade after the G1 move
import shutil
import signal  # noqa: F401 - kept on the facade after the G7a move
import stat
import subprocess
import sys
import tempfile  # noqa: F401 - kept on the facade after the G7a move
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit  # noqa: F401 - kept on the facade after the G3 move
from uuid import uuid4

import nexus.orchestrator.standing_grant_store as _standing_grant_store_module
from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.contracts.execution_readiness import (
    COMPLETION_AUTHORITY_KIND,  # noqa: F401 - kept on the facade after the G2 move
    HOST_GATEWAY_SERVICE_LABEL,  # noqa: F401 - kept on the facade after the G2 move
    ExecutionReadinessBlockerCode,  # noqa: F401 - kept on the facade after the G2 move
    ExecutionReadinessPlane,  # noqa: F401 - kept on the facade after the G2 move
    ExecutionReadinessRequest,
    ExecutionReadinessStatus,  # noqa: F401 - kept on the facade after the G2 move
)
from nexus.contracts.gateway_convergence import (
    ConvergenceAction,
    ConvergenceReason,
    DesiredDeploymentMode,
    GatewayConvergenceRequest,
    RecoveryEffectState,
)
from nexus.contracts.gateway_deployment import RECOVERY_RECEIPT_PATH
from nexus.contracts.lifecycle_action import (
    ContractKind,
    ExternalCandidateAdoptionRequest,  # noqa: F401 - kept on the facade after the G10 move
    LifecycleActionEnvelope,  # noqa: F401 - kept on the facade after the G6 move
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
)
from nexus.contracts.target_integration_lifecycle import (
    ExternalAcceptanceReceipt,  # noqa: F401 - kept on the facade after the G10 move
)
from nexus.engine.canonical_task_seam import (
    VerifiedTaskCardIdentity,  # noqa: F401 - kept on the facade after the G7b move
    build_canonical_dispatch_envelope,  # noqa: F401 - kept on the facade after the G7b move
    build_canonical_planner_admission,  # noqa: F401 - kept on the facade after the G7b move
    execute_canonical_product_task,
)
from nexus.engine.learning_policy_loader import (
    DEFAULT_GOVERNED_ADOPTION_PATH,
    DEFAULT_GOVERNED_ROLLBACK_PATH,
)
from nexus.orchestrator import bootstrap_agent_authority
from nexus.orchestrator.ambient_core import LazyCanonicalCoreControlPort
from nexus.orchestrator.canonical_mcp_ingress import (
    build_mcp_execution_context,
    reject_caller_route_overrides,
)
from nexus.orchestrator.canonical_source_root import (
    CONTROLLER_BINDING_PROBLEM,
    CONTROLLER_IS_SEPARATE,
    LOADED_SOURCE_ROOT,
    bound_controller_problem,
    controller_binding_status,
)
from nexus.orchestrator.execution_readiness import (
    _COMPLETION_REQUIRED_CAPABILITIES,  # noqa: F401 - kept on the facade after the G2 move
    COMPLETION_INTERFACE_REVISION,  # noqa: F401 - kept on the facade after the G2 move
    COMPLETION_REPOSITORY,  # noqa: F401 - kept on the facade after the G2 move
    CompletionAuthorityObservation,  # noqa: F401 - kept on the facade after the G2 move
    GatewayReadinessObservation,
    PlaneObservation,  # noqa: F401 - kept on the facade after the G2 move
    evaluate_completion_contract,  # noqa: F401 - kept on the facade after the G2 move
    evaluate_execution_readiness,
    evaluate_source_binding,  # noqa: F401 - kept on the facade after the G2 move
)
from nexus.orchestrator.gateway_convergence import evaluate_gateway_convergence
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,  # noqa: F401 - kept on the facade after the G10 move
)
from nexus.orchestrator.learning_policy_control import (
    apply_learning_policy_effect,
)
from nexus.orchestrator.lifecycle_guards import (
    LifecycleGuardError,
    configure_runtime_manifest_hash,
    post_action_receipt_formatter,
    pre_action_guard,
    validate_approval_grant,
)
from nexus.orchestrator.mutation_admission import (
    CANONICAL_REPOSITORIES,  # noqa: F401 - kept on the facade after the G3 move
    MutationAdmissionError,  # noqa: F401 - kept on the facade after the G8 move
    MutationAdmissionStore,
)
from nexus.orchestrator.owner_confirmation import (
    LEGACY_PROTOCOL_VERSION,
    NEGOTIATED_ELICITATION_PROTOCOL,
    OwnerConfirmationError,
    OwnerConfirmationRequest,
    StdioElicitationChannel,
    UnavailableConfirmationChannel,
    client_supports_form_elicitation,
)
from nexus.orchestrator.self_hosted_task_service import (
    CANONICAL_SOURCE_ROOT,
    SelfHostedTaskService,
    resolve_contract_identity,
    resolve_lifecycle_identity,  # noqa: F401 - kept on the facade after the G7b move
    validate_task_card_binding,  # noqa: F401 - kept on the facade after the G7b move
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantKey,
    StandingGrantReceipt,
    StandingGrantReceiptError,
    authorize_durable_standing_grant_effect,
    load_keyed_standing_grant_receipt,
    load_keyed_standing_grant_receipt_structural,
    restore_task_card_authority,
    switch_task_card_authority,
    write_keyed_standing_grant_receipt,
)
from nexus.orchestrator.task_card_scope import protected_path_reason
from nexus.orchestrator.task_contract import (
    TASK_CARD_EXPECTED_EVIDENCE_FENCE,
    EvidenceRequirementMode,
    EvidenceSubjectApplicability,
    ExpectedEvidenceUniverse,
    parse_task_card_expected_evidence,
)
from nexus.orchestrator.unified_mcp_gateway_parts.assist_jobs import (
    _AssistJobsMixin as _AssistJobsMixin,
)
from nexus.orchestrator.unified_mcp_gateway_parts.assist_probe import (
    _AssistProbeMixin as _AssistProbeMixin,
)
from nexus.orchestrator.unified_mcp_gateway_parts.assist_response import (
    _AssistResponseMixin as _AssistResponseMixin,
)
from nexus.orchestrator.unified_mcp_gateway_parts.candidate_ops import (
    _CandidateOpsMixin as _CandidateOpsMixin,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    _CORE_PROVENANCE_PUBLIC_FIELDS as _CORE_PROVENANCE_PUBLIC_FIELDS,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    _GITHUB_CLI_ENV as _GITHUB_CLI_ENV,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    CORE_PROVENANCE_RECHECK_SECONDS as CORE_PROVENANCE_RECHECK_SECONDS,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    _canonical_remote_matches as _canonical_remote_matches,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    _core_provenance_cache as _core_provenance_cache,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    _core_provenance_lock as _core_provenance_lock,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    _resolve_github_cli as _resolve_github_cli,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    gateway_core_provenance as gateway_core_provenance,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    github_observer_runtime_identity as github_observer_runtime_identity,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    observe_github_issue as observe_github_issue,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    observe_github_repository_default_head as observe_github_repository_default_head,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    preload_core_transport as preload_core_transport,
)
from nexus.orchestrator.unified_mcp_gateway_parts.github_observer import (
    public_core_provenance as public_core_provenance,
)
from nexus.orchestrator.unified_mcp_gateway_parts.model_probe import (
    _ModelProbeMixin as _ModelProbeMixin,
)
from nexus.orchestrator.unified_mcp_gateway_parts.mutation_admission import (
    _MutationAdmissionMixin as _MutationAdmissionMixin,
)
from nexus.orchestrator.unified_mcp_gateway_parts.readiness import (
    _READINESS_DEFAULTED_PASSED_PLANES as _READINESS_DEFAULTED_PASSED_PLANES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.readiness import (
    _READINESS_ENV_STATUS_VARS as _READINESS_ENV_STATUS_VARS,
)
from nexus.orchestrator.unified_mcp_gateway_parts.readiness import (
    EXECUTION_READINESS_TOOL_NAME as EXECUTION_READINESS_TOOL_NAME,
)
from nexus.orchestrator.unified_mcp_gateway_parts.readiness import (
    _completion_authority_observation_from_environment as _completion_authority_observation_from_environment,
)
from nexus.orchestrator.unified_mcp_gateway_parts.readiness import (
    _in_process_readiness_plane_observations as _in_process_readiness_plane_observations,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_RESULT_BYTES as MAX_RESULT_BYTES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_FILE_BYTES as MAX_SEARCH_FILE_BYTES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_FILES as MAX_SEARCH_FILES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_LINE_BYTES as MAX_SEARCH_LINE_BYTES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_RESULTS as MAX_SEARCH_RESULTS,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_SECONDS as MAX_SEARCH_SECONDS,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_STDERR_BYTES as MAX_SEARCH_STDERR_BYTES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    MAX_SEARCH_TOTAL_BYTES as MAX_SEARCH_TOTAL_BYTES,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _bounded_match_line as _bounded_match_line,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _bounded_rg_matches as _bounded_rg_matches,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _bounded_text as _bounded_text,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _display_search_path as _display_search_path,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _git_ls_files as _git_ls_files,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _literal_matches_in_file as _literal_matches_in_file,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _python_literal_search as _python_literal_search,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _run_rg_literal_search as _run_rg_literal_search,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _search_candidate_files as _search_candidate_files,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _searchable_file as _searchable_file,
)
from nexus.orchestrator.unified_mcp_gateway_parts.search import (
    _terminate_and_reap_search_process as _terminate_and_reap_search_process,
)
from nexus.orchestrator.unified_mcp_gateway_parts.worker_candidate import (
    _WorkerCandidateMixin as _WorkerCandidateMixin,
)
from nexus.services.agy_account_pool import (
    AgyAccountPoolBusyError,  # noqa: F401 - kept on the facade after the G7a move
    AgyAccountPoolExhaustedError,  # noqa: F401 - kept on the facade after the G7a move
    CrossProcessLeaseCoordinator,
    get_account_pool_manager,
)
from nexus.services.model_capability_lineage import (
    CHANGE_KIND_VALUES,
    CalibrationPlanner,
    LineageResolutionError,  # noqa: F401 - kept on the facade after the G7b move
    ModelCapabilityLineageRegistry,
)
from nexus.services.model_workforce_policy import (
    NON_ADMISSIBLE_STATES,  # pyright: ignore[reportAttributeAccessIssue]  # noqa: F401 - kept on the facade after the G7b move
    WorkforcePolicyLoader,  # pyright: ignore[reportAttributeAccessIssue]
)
from nexus.services.unified_runtime import (
    LOCAL_ONLY_PROVIDERS,  # noqa: F401 - kept on the facade after the G4 move
    ONLINE_CLI_SPEC_REGISTRY,
    resolve_registered_provider_executable,  # noqa: F401 - kept on the facade after the G7a move
)

GATEWAY_NAME = "nexus-mcp-gateway"
GATEWAY_VERSION = "0.1.0"
PUBLIC_APP_NAME = "Nexus"
SERVER_INSTANCE_ID = uuid4().hex
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()
LIFECYCLE_REVISION = "nexus.lifecycle.gateway.v2"
LIFECYCLE_STATE_SCHEMA_REVISION = "nexus.self_hosted_task_state.v1"
TASK_CONTRACT_REVISION = "nexus.task_contract.v1"
PERMISSION_POLICY_REVISION = "nexus.permission.policy.v1"
PERMISSION_POLICY = {
    "revision": PERMISSION_POLICY_REVISION,
    "profiles": ["DISCOVERY", "OBSERVE", "VERIFY", "MUTATE_BOUNDED", "CANDIDATE", "INTEGRATE"],
    "approval_scopes": ["ALLOW_ACTION_ONCE", "ALLOW_TASK_ATTEMPT", "REJECT"],
    "always_allow": False,
}
PERMISSION_POLICY_HASH = hashlib.sha256(
    json.dumps(PERMISSION_POLICY, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
_LEGACY_EPB_CAMPAIGN_ID = "CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01"
_LEGACY_EPB_SPEC_ID = "SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001"
_LEGACY_EPB_SPEC_SHA256 = "9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1"
MAX_READ_BYTES = 1024 * 1024
FRESHNESS_SEMANTICS_REVISION = "nexus.gateway_freshness.v3"
CLINE_RUN_TIMEOUT_SECONDS = 60
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
GITHUB_REPOSITORY = RepositoryIdentity(
    repository_id="James3014/Nexus-new",
    canonical_remote="https://github.com/James3014/Nexus-new.git",
)

# Populated from ``UnifiedMCPGateway.tool_specs()`` after the class definition.
# There must be one public manifest truth; status, health, recovery validation,
# and the MCP initialize revision all consume this derived tuple.
PUBLIC_TOOL_NAMES: tuple[str, ...]
TOOL_MANIFEST_REVISION: str
FULL_TOOL_SCHEMA_HASH: str
SERVER_REPO_HEAD_AT_START: str
# Freeze the runtime source set and its digests once at gateway load so later
# imports never change the freshness comparison baseline.
RUNTIME_SOURCE_PATHS: tuple[Path, ...]
RUNTIME_SOURCE_SHA256_AT_START: str
ACTION_CONTRACT_SHA256_AT_START: str
PERMISSION_ENFORCEMENT_SHA256_AT_START: str


# Agy 1.1.11 encodes the reasoning tier in the model identity suffix
# (-high/-medium/-low) and rejects an ``--effort`` flag that contradicts the
# tier.  Both assisted-provider paths must normalize effort through this single
# compiler so a hard-coded default can never override the model identity.
AGY_EFFORT_TIERS: tuple[str, ...] = ("high", "medium", "low")
AGY_PRINT_TIMEOUT = "25s"
AGY_MODEL_PROBE_PRINT_TIMEOUT = "300s"


def _agy_effort_tier(model: str) -> str:
    """Return the effort tier embedded in an Agy model name, or ``""``."""
    name = (model or "").strip()
    for tier in AGY_EFFORT_TIERS:
        if name.endswith(f"-{tier}"):
            return tier
    return ""


def _compile_agy_command(
    *,
    executable: str,
    model: str,
    prompt: str,
    json_schema: str = "",
    explicit_effort: str = "",
    print_timeout: str = AGY_PRINT_TIMEOUT,
) -> list[str]:
    """Single source of truth for Agy CLI argument compilation.

    Rules:
    - ``--effort`` is emitted only when the caller explicitly supplies it.
    - An explicit effort that contradicts a tier suffix in the model identity
      fails closed deterministically instead of silently overriding.
    - A model carrying no tier suffix still requires an explicit effort for
      Agy 1.1.11; the compiler never invents a default tier on its own.
    - Suffixed models accept the canonical ``--model <name>`` form with the
      tier omitted from the flag surface.
    """
    name = (model or "").strip()
    tier = _agy_effort_tier(name)
    explicit = (explicit_effort or "").strip().lower()
    if explicit and explicit not in AGY_EFFORT_TIERS:
        raise GatewayInputError(f"agy effort must be one of {', '.join(AGY_EFFORT_TIERS)}")
    if explicit and tier and explicit != tier:
        raise GatewayInputError(
            f"agy model {name!r} embeds {(tier + ' effort')!r}; explicit --effort {explicit!r} conflicts"
        )
    command = [executable, "--mode", "plan", "--sandbox", "--output-format", "json"]
    if json_schema:
        command.extend(["--json-schema", json_schema])
    if explicit:
        command.extend(["--effort", explicit])
    elif not tier and not name:
        # Neither the model nor the caller pinned an effort.  The adapter must
        # not choose one on behalf of the caller.
        raise GatewayInputError("agy model requires an explicit effort or an embedded tier suffix")
    if name:
        command.extend(["--model", name])
    command.extend(["--print-timeout", print_timeout, "--prompt", prompt])
    return command


class GatewayInputError(ValueError):
    """Raised when a public gateway request is outside its bounded contract."""


# Until per-effect scope enforcement exists (#1750 phase 2), host-confirmed
# grants may not carry merge-, integration-, release- or grant-class authority.
_SCOPE_ENFORCEMENT_REQUIRED_ACTIONS = frozenset(
    {
        AutonomyActionClass.GITHUB_MERGE,
        AutonomyActionClass.CANDIDATE_INTEGRATE,
        AutonomyActionClass.PRODUCTION_RELEASE,
        AutonomyActionClass.RUNTIME_ACTIVATE,
        AutonomyActionClass.OWNER_REPRESENTATION_GRANT_ISSUE,
    }
)


def _text(value: Any, field: str, *, max_length: int = 4096) -> str:
    result = str(value or "").strip()
    if not result:
        raise GatewayInputError(f"{field} is required")
    if len(result) > max_length:
        raise GatewayInputError(f"{field} exceeds {max_length} characters")
    return result


def _safe_relative_path(value: Any, field: str = "path") -> Path:
    raw = _text(value, field, max_length=1024)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GatewayInputError(f"{field} must be a bounded relative path")
    if ".git" in candidate.parts:
        raise GatewayInputError(f"{field} cannot access .git")
    resolved = (CANONICAL_SOURCE_ROOT / candidate).resolve()
    try:
        resolved.relative_to(CANONICAL_SOURCE_ROOT)
    except ValueError as exc:
        raise GatewayInputError(f"{field} escapes canonical root") from exc
    return resolved


def _safe_search_target(value: Any) -> tuple[Path, Path]:
    """Validate a search target fail-closed against symlink traversal.

    Returns ``(lexical, resolved)`` where ``lexical`` stays inside the canonical
    root and ``resolved`` is the on-disk target.  Every path component - the
    intermediate directories and the final component - is checked with
    ``lstat()``; any symlink rejects the request so a search can never read
    through a link planted outside the canonical root.
    """
    raw = _text(value, "path", max_length=1024)
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GatewayInputError("path must be a bounded relative path")
    if ".git" in candidate.parts:
        raise GatewayInputError("path cannot access .git")
    lexical = CANONICAL_SOURCE_ROOT / candidate
    current = CANONICAL_SOURCE_ROOT
    for part in candidate.parts:
        current = current / part
        try:
            if stat.S_ISLNK(os.lstat(current).st_mode):
                raise GatewayInputError("search path cannot traverse symlinks")
        except FileNotFoundError:
            break
    resolved = lexical.resolve()
    try:
        resolved.relative_to(CANONICAL_SOURCE_ROOT)
    except ValueError as exc:
        raise GatewayInputError("path escapes canonical root") from exc
    return lexical, resolved


def _require_bound_controller(expected_head: Optional[str] = None) -> None:
    """Re-check a separate Controller right before a Controller effect (#1939).

    The startup check can go stale; Task Card create/commit, governed start,
    mutation admission and finish re-prove that the Controller is still the
    loaded commit plus bind commits only.  With ``expected_head`` the HEAD the
    caller binds must also be the HEAD that was just validated, so a Controller
    moved between the check and the bind is refused.  Without a separate
    Controller this is a no-op.
    """
    if CONTROLLER_BINDING_PROBLEM is not None:
        # Degraded start (#2230): the canonical root fell back to the loaded
        # deployment, which must never receive a Controller effect.
        raise GatewayInputError(f"CONTROLLER_BINDING_INVALID:DEGRADED:{CONTROLLER_BINDING_PROBLEM}")
    if not CONTROLLER_IS_SEPARATE:
        return
    reason = bound_controller_problem(Path(CANONICAL_SOURCE_ROOT), Path(LOADED_SOURCE_ROOT))
    if reason is not None:
        raise GatewayInputError(f"CONTROLLER_BINDING_INVALID:{reason}")
    if expected_head is not None and _git("rev-parse", "HEAD").strip() != expected_head:
        raise GatewayInputError("CONTROLLER_BINDING_INVALID:HEAD_MOVED_DURING_CHECK")


def _current_controller_binding() -> dict[str, Optional[str]]:
    """Controller state as this module sees it (same globals as ``_require_bound_controller``)."""
    if CONTROLLER_BINDING_PROBLEM is not None:
        return {"status": "DEGRADED", "reason": CONTROLLER_BINDING_PROBLEM}
    return {"status": "SEPARATE" if CONTROLLER_IS_SEPARATE else "NOT_SEPARATE", "reason": None}


def _loaded_git(*args: str, timeout: float = 3.0) -> str:
    """Git in the checkout this process runs (identity), not the Controller (#1939).

    Without a separate Controller worktree both roots are one checkout, so this
    is exactly ``_git``.
    """
    if not CONTROLLER_IS_SEPARATE:
        return _git(*args)
    result = subprocess.run(
        ["git", *args],
        cwd=LOADED_SOURCE_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _git(*args: str, timeout: float = 3.0) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=CANONICAL_SOURCE_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git command failed: {' '.join(args)}")
    return result.stdout


def _loaded_runtime_source_paths() -> tuple[Path, ...]:
    """Collect the Nexus Python modules already loaded inside the canonical repo.

    The comparison set must be frozen at gateway start; later imports of other
    modules must never change it.
    """
    root_resolved = LOADED_SOURCE_ROOT.resolve()
    paths: list[Path] = []
    for module in sorted(sys.modules.values(), key=lambda value: str(getattr(value, "__name__", ""))):
        name = str(getattr(module, "__name__", ""))
        if name != "nexus" and not name.startswith("nexus."):
            continue
        file_path = getattr(module, "__file__", None)
        if not file_path:
            continue
        candidate = Path(file_path)
        if candidate.suffix != ".py":
            continue
        if "__pycache__" in candidate.parts or candidate.suffix == ".pyc":
            continue
        if "tests" in candidate.parts:
            continue
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        paths.append(resolved)
    return tuple(sorted(set(paths), key=lambda path: path.as_posix()))


def _hash_source_paths(paths: tuple[Path, ...], *, root: Path = LOADED_SOURCE_ROOT) -> str:
    """Deterministic SHA-256 over relative path + file bytes for a frozen set.

    A missing or unreadable file contributes a distinct marker so any change,
    including deletion, surfaces as runtime source drift.
    """
    root_resolved = root.resolve()
    digest = hashlib.sha256()
    for path in paths:
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(root_resolved)
        except ValueError:
            relative = Path(resolved.name)
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\x00")
        try:
            data = resolved.read_bytes()
        except OSError:
            digest.update(b"\x00missing\x00")
            continue
        digest.update(b"\x00len=%d\x00" % len(data))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


# Directly define the public action schema or permission semantics.  Implementation
# changes (for example ``_search``) must not alter the action contract fingerprint.
ACTION_CONTRACT_TOP_LEVEL_CONSTANTS = (
    "PERMISSION_POLICY",
    "PERMISSION_POLICY_REVISION",
    "TASK_CONTRACT_REVISION",
    "LIFECYCLE_REVISION",
    "LIFECYCLE_STATE_SCHEMA_REVISION",
)


def _action_contract_digest(source: str) -> Optional[str]:
    """Non-executing AST fingerprint of the public action contract.

    Hashes the assignment expression of each named top-level constant plus the
    body of ``UnifiedMCPGateway.tool_specs``.  Returns ``None`` when the source
    cannot be parsed (fail closed).
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    collected: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.Assign):
                targets = node.targets
            else:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in ACTION_CONTRACT_TOP_LEVEL_CONSTANTS:
                    collected[target.id] = ast.dump(node.value, include_attributes=False)
        elif isinstance(node, ast.ClassDef) and node.name == "UnifiedMCPGateway":
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name == "tool_specs":
                    collected["UnifiedMCPGateway.tool_specs"] = ast.dump(member, include_attributes=False)
    if not collected:
        return None
    digest = hashlib.sha256()
    for key in sorted(collected):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(collected[key].encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _action_contract_fingerprint(
    *,
    root: Path = LOADED_SOURCE_ROOT,
    source: Optional[str] = None,
) -> tuple[str, bool, tuple[str, ...]]:
    """Return ``(sha256, ok, reasons)`` for the action contract.

    ``ok=False`` means the contract cannot be evaluated and review must fail
    closed; ``reasons`` carries the explicit cause for ``reload_reasons``.
    """
    if source is None:
        source_path = root / "nexus" / "orchestrator" / "unified_mcp_gateway.py"
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            return "", False, (f"action_contract_source_unreadable:{exc.__class__.__name__}",)
    digest = _action_contract_digest(source)
    if digest is None:
        return "", False, ("action_contract_source_unparseable",)
    return digest, True, ()


# Modules that define or enforce the permission policy.  Implementation changes
# (for example ``_search``) must never alter the permission enforcement digest.
PERMISSION_ENFORCEMENT_PATHS = (
    "nexus/orchestrator/lifecycle_guards.py",
    "nexus/contracts/lifecycle_action.py",
)


def _permission_enforcement_fingerprint(
    *,
    root: Path = LOADED_SOURCE_ROOT,
) -> tuple[str, bool, tuple[str, ...]]:
    """Non-executing AST fingerprint of the permission enforcement surface.

    Hashes the full syntax tree of every module that defines or enforces the
    permission policy without importing or executing them.  ``ok=False`` means
    the enforcement contract cannot be evaluated and permission review must
    fail closed; ``reasons`` carries the explicit cause for ``review_reasons``.
    """
    digest = hashlib.sha256()
    for relative in PERMISSION_ENFORCEMENT_PATHS:
        source_path = root / relative
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            return "", False, (f"permission_enforcement_source_unreadable:{exc.__class__.__name__}",)
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return "", False, (f"permission_enforcement_source_unparseable:{relative}",)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(ast.dump(tree, include_attributes=False).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest(), True, ()


def _evaluate_upstream_freshness(
    *,
    deployed_source_head: str | None,
    observed_upstream_main_head: str | None,
    upstream_observed_at: str | None = None,
    upstream_observation_error: str | None = None,
) -> dict[str, Any]:
    """Derive upstream-main freshness for Gateway status.

    Distinguishes deployment-local drift (repository_drift) from upstream freshness:
    - repository_drift: whether local checkout drifted relative to its baseline at startup.
    - upstream_freshness: whether deployed source equals current GitHub upstream main.

    Outcomes:
    - CURRENT: deployed_source_head == observed_upstream_main_head (both valid 40-hex)
    - STALE: deployed_source_head != observed_upstream_main_head (both valid 40-hex)
    - UNKNOWN: missing, network/timeout/auth failure, or malformed SHA
    """
    deployed_sha = str(deployed_source_head or "").strip().lower()
    upstream_sha = (
        str(observed_upstream_main_head or "").strip().lower()
        if observed_upstream_main_head
        else ""
    )
    error_msg = str(upstream_observation_error or "").strip() if upstream_observation_error else None

    valid_deployed = bool(_SHA_RE.fullmatch(deployed_sha)) if deployed_sha else False
    valid_upstream = bool(_SHA_RE.fullmatch(upstream_sha)) if upstream_sha else False

    if error_msg or not valid_upstream or not valid_deployed:
        freshness = "UNKNOWN"
        observed_head = upstream_sha if valid_upstream else None
        if not error_msg:
            if not valid_deployed and not deployed_sha:
                error_msg = "deployed_source_head_missing"
            elif not valid_deployed:
                error_msg = "deployed_source_head_malformed"
            elif not valid_upstream and not upstream_sha:
                error_msg = "observed_upstream_main_head_missing"
            else:
                error_msg = "observed_upstream_main_head_malformed"
    elif deployed_sha == upstream_sha:
        freshness = "CURRENT"
        observed_head = upstream_sha
    else:
        freshness = "STALE"
        observed_head = upstream_sha

    return {
        "deployed_source_head": deployed_sha if valid_deployed else (deployed_source_head or ""),
        "observed_upstream_main_head": observed_head,
        "upstream_observed_at": upstream_observed_at,
        "upstream_freshness": freshness,
        "upstream_observation_error": error_msg,
    }


def _receipt_only_main_movement(
    *,
    deployed_source_head: str | None,
    observed_upstream_main_head: str | None,
) -> bool:
    """Prove that upstream movement changed only the tracked recovery receipt.

    This is deliberately narrower than generic path-impact analysis.  Any
    missing, divergent, truncated, malformed, or unavailable comparison fails
    closed and preserves the existing recovery request.
    """
    deployed = str(deployed_source_head or "").strip().lower()
    upstream = str(observed_upstream_main_head or "").strip().lower()
    if (
        not _SHA_RE.fullmatch(deployed)
        or not _SHA_RE.fullmatch(upstream)
        or deployed == upstream
    ):
        return False

    github_cli, _resolution_error = _resolve_github_cli()
    if github_cli is None:
        return False
    try:
        result = subprocess.run(
            [
                github_cli,
                "api",
                (
                    f"repos/{GITHUB_REPOSITORY.repository_id}/compare/"
                    f"{deployed}...{upstream}"
                ),
            ],
            cwd=CANONICAL_SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, Mapping):
        return False

    base_commit = payload.get("base_commit")
    head_commit = payload.get("head_commit")
    merge_base = payload.get("merge_base_commit")
    files = payload.get("files")
    if (
        payload.get("status") != "ahead"
        or payload.get("behind_by") != 0
        or not isinstance(payload.get("ahead_by"), int)
        or payload["ahead_by"] <= 0
        or not isinstance(base_commit, Mapping)
        or base_commit.get("sha") != deployed
        or not isinstance(head_commit, Mapping)
        or head_commit.get("sha") != upstream
        or not isinstance(merge_base, Mapping)
        or merge_base.get("sha") != deployed
        or not isinstance(files, list)
        or len(files) != 1
        or not isinstance(files[0], Mapping)
    ):
        return False
    changed = files[0]
    return (
        changed.get("filename") == RECOVERY_RECEIPT_PATH
        and changed.get("status") == "modified"
    )


def _default_observe_upstream_main(
    *,
    timeout_seconds: float = 3.0,
    repo_root: Path | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Pure read-only observation of upstream main ref without mutating local git state.

    Uses `git ls-remote --heads origin main` with a bounded timeout.
    Returns: (upstream_sha_or_none, observed_at_iso, error_or_none)
    """
    root = repo_root or CANONICAL_SOURCE_ROOT
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", "main"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or f"exit_code_{proc.returncode}"
            return None, now_iso, f"upstream_observation_failed:{err[:120]}"
        output = proc.stdout.strip()
        if not output:
            return None, now_iso, "upstream_ref_not_found:refs/heads/main"
        head_sha = output.split()[0].strip().lower()
        if not _SHA_RE.fullmatch(head_sha):
            return None, now_iso, f"upstream_head_malformed:{head_sha[:40]}"
        return head_sha, now_iso, None
    except subprocess.TimeoutExpired:
        return None, now_iso, f"upstream_observation_timeout:exceeded_{timeout_seconds}s"
    except Exception as exc:
        return None, now_iso, f"upstream_observation_error:{exc.__class__.__name__}"


def _evaluate_freshness(
    *,
    repo_head_at_start: str,
    repo_head_current: str,
    runtime_sha_at_start: str,
    runtime_sha_current: str,
    action_sha_at_start: str,
    action_sha_current: str,
    permission_sha_at_start: str = "",
    permission_sha_current: str = "",
    action_contract_ok: bool = True,
    action_contract_reasons: tuple[str, ...] = (),
    permission_contract_ok: bool = True,
    permission_contract_reasons: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Derive the freshness semantics for ``nexus_gateway_status``.

    ``repository_drift`` is informational only; only runtime source drift
    triggers ``reload_required``.  ``reload_reasons`` therefore reports the
    runtime reload decision alone (``runtime_source_changed``).  Action
    definition changes, permission enforcement changes, or a fail-closed
    contract evaluation are review-only concerns: they surface only in
    ``review_reasons`` and never in ``reload_reasons``.
    """
    repository_drift = bool(repo_head_at_start != repo_head_current)
    runtime_source_drift = bool(runtime_sha_at_start != runtime_sha_current)
    reload_required = bool(runtime_source_drift)
    action_definition_changed = bool(action_sha_at_start != action_sha_current)
    permission_changed = bool(permission_sha_at_start != permission_sha_current)
    action_definition_review_required = bool(not action_contract_ok or action_definition_changed)
    permission_review_required = bool(not permission_contract_ok or permission_changed)
    action_review_required = bool(action_definition_review_required or permission_review_required)
    reload_reasons: list[str] = []
    review_reasons: list[str] = []
    if not action_contract_ok:
        review_reasons.extend(action_contract_reasons)
    if action_definition_changed:
        review_reasons.append("action_definition_changed")
    if not permission_contract_ok:
        review_reasons.extend(permission_contract_reasons)
    if permission_changed:
        review_reasons.append("permission_enforcement_changed")
    if runtime_source_drift:
        reload_reasons.append("runtime_source_changed")
    return {
        "repository_drift": repository_drift,
        "runtime_source_sha256_at_start": runtime_sha_at_start,
        "runtime_source_sha256_current": runtime_sha_current,
        "runtime_source_drift": runtime_source_drift,
        "action_definition_sha256_at_start": action_sha_at_start,
        "action_definition_sha256_current": action_sha_current,
        "action_contract_sha256_at_start": action_sha_at_start,
        "action_contract_sha256_current": action_sha_current,
        "permission_enforcement_sha256_at_start": permission_sha_at_start,
        "permission_enforcement_sha256_current": permission_sha_current,
        "action_definition_review_required": action_definition_review_required,
        "permission_review_required": permission_review_required,
        "action_review_required": action_review_required,
        "review_reasons": review_reasons,
        "reload_required": reload_required,
        "reload_reasons": reload_reasons,
    }


def _gateway_recovery_manager() -> Any:
    """Load the repository-owned #526 recovery manager only for recovery actions."""

    return importlib.import_module("scripts.ops.mcp_gateway_durable")


def _gateway_recovery_result(result: Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        return dict(result)
    dump = getattr(result, "model_dump", None)
    if not callable(dump):
        raise GatewayInputError("GATEWAY_RECOVERY_MANAGER_RESULT_INVALID")
    payload = dump()
    if not isinstance(payload, Mapping):
        raise GatewayInputError("GATEWAY_RECOVERY_MANAGER_RESULT_INVALID")
    return dict(payload)


class UnifiedMCPGateway(_CandidateOpsMixin, _MutationAdmissionMixin, _WorkerCandidateMixin, _ModelProbeMixin, _AssistJobsMixin, _AssistResponseMixin, _AssistProbeMixin):
    """JSON-RPC MCP server with one public identity and bounded tools."""

    def __init__(
        self,
        service: Optional[SelfHostedTaskService] = None,
        *,
        model_runner: Any = None,
        apply_runner: Any = None,
        github_issue_observer: Any = None,
        mutation_repository_observer: Any = None,
        upstream_observer: Any = None,
        upstream_cache_ttl_seconds: float = 30.0,
        owner_confirmation_channel: Any = None,
    ):
        # Startup: with a configured Core checkout, Core owns ``product`` in
        # this process before any tool call can import the in-tree package.
        preload_core_transport()
        if service is None:
            # The live service gets the canonical Core seam. It is lazy: only
            # tasks whose hashed card declares an expected-evidence universe
            # ever load Core or open its session DB (#2181).
            service = SelfHostedTaskService(
                ambient_core_port=LazyCanonicalCoreControlPort(
                    SelfHostedTaskService.canonical_state_dir()
                )
            )
        self.service = service
        # Owner confirmation is never a tool argument (#1750). Without a host
        # channel that can ask the human, authority issuance fails closed.
        self._owner_confirmation_injected = owner_confirmation_channel is not None
        self._owner_confirmation_channel = (
            owner_confirmation_channel or UnavailableConfirmationChannel()
        )
        self._stdio_streams: tuple[Any, Any] | None = None
        # These kwargs remain accepted for compatibility with older callers,
        # but neither runner is a gateway authority.  Assisted jobs are
        # provider probes/advice only; governed implementation enters through
        # nexus_worker_candidate.
        self._model_runner = self._run_agy_plan
        self._ignored_model_runner = model_runner
        self._ignored_apply_runner = apply_runner
        self._workforce_loader = WorkforcePolicyLoader()
        self._lineage_registry = ModelCapabilityLineageRegistry()
        self._calibration_planner = CalibrationPlanner(self._lineage_registry)
        self._assist_processes: dict[str, subprocess.Popen[str]] = {}
        self._assist_account_claims: dict[str, Any] = {}
        self._assist_lock = threading.RLock()
        self._github_issue_observer = github_issue_observer or observe_github_issue
        self._mutation_repository_observer = (
            mutation_repository_observer or observe_github_repository_default_head
        )
        admission_state_root = (
            getattr(self.service, "state_dir", None)
            or SelfHostedTaskService.canonical_state_dir()
        )
        self._mutation_admissions = MutationAdmissionStore(admission_state_root)
        self._upstream_observer = upstream_observer or _default_observe_upstream_main
        self._upstream_cache_ttl_seconds = float(upstream_cache_ttl_seconds)
        self._upstream_cache: tuple[float, dict[str, Any]] | None = None
        self._upstream_cache_lock = threading.RLock()

    def _observe_upstream_freshness(self, deployed_head: str) -> dict[str, Any]:
        """Observe upstream-main freshness with bounded caching and fail-closed isolation."""
        with self._upstream_cache_lock:
            now = time.monotonic()
            if self._upstream_cache is not None:
                cached_time, cached_obs = self._upstream_cache
                if (now - cached_time) < self._upstream_cache_ttl_seconds:
                    return _evaluate_upstream_freshness(
                        deployed_source_head=deployed_head,
                        observed_upstream_main_head=cached_obs.get("observed_upstream_main_head"),
                        upstream_observed_at=cached_obs.get("upstream_observed_at"),
                        upstream_observation_error=cached_obs.get("upstream_observation_error"),
                    )

            # Perform fresh observation
            try:
                upstream_head, observed_at, error = self._upstream_observer()
            except subprocess.TimeoutExpired:
                upstream_head = None
                observed_at = self._utc_now()
                error = "upstream_observer_timeout"
            except Exception as exc:
                upstream_head = None
                observed_at = self._utc_now()
                error = f"upstream_observer_exception:{exc.__class__.__name__}"

            evaluated = _evaluate_upstream_freshness(
                deployed_source_head=deployed_head,
                observed_upstream_main_head=upstream_head,
                upstream_observed_at=observed_at,
                upstream_observation_error=error,
            )
            self._upstream_cache = (now, evaluated)
            return evaluated

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

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
        context = bootstrap_agent_authority.delegation_context(
            action,
            source_root=Path(LOADED_SOURCE_ROOT),
            controller_binding=_current_controller_binding(),
            expected_source_head=SERVER_REPO_HEAD_AT_START,
        )
        if context is not None:
            try:
                return bootstrap_agent_authority.authorize_bootstrap_agent_effect(
                    repository=GITHUB_REPOSITORY,
                    action=action,
                    effect=effect,
                    key=key,
                    context=context,
                    record_directory=_standing_grant_store_module.DEFAULT_RECEIPT_PATH.parent,
                    server_instance_id=SERVER_INSTANCE_ID,
                )
            except bootstrap_agent_authority.BootstrapAgentAuthorityError as exc:
                raise GatewayInputError(f"OWNER_AUTHORITY_REQUIRED:{exc}") from exc
        try:
            return authorize_durable_standing_grant_effect(
                repository=GITHUB_REPOSITORY,
                action=action,
                effect=effect,
                key=key,
            )
        except StandingGrantReceiptError as exc:
            raise GatewayInputError(f"OWNER_AUTHORITY_REQUIRED:{exc}") from exc

    @staticmethod
    def _owner_effect_key(arguments: Mapping[str, Any]) -> StandingGrantKey:
        """Resolve the explicit Goal/coordination scope for durable effects."""
        try:
            goal_id = _text(arguments.get("authority_goal_id"), "authority_goal_id", max_length=128)
            scope_id = _text(
                arguments.get("authority_coordination_scope_id"),
                "authority_coordination_scope_id",
                max_length=128,
            )
            return StandingGrantKey(GITHUB_REPOSITORY, goal_id, scope_id)
        except (GatewayInputError, TypeError, ValueError) as exc:
            raise GatewayInputError(f"OWNER_AUTHORITY_KEY_REQUIRED:{exc}") from exc

    @staticmethod
    def _standing_key(goal_id: str, thread_id: str) -> StandingGrantKey:
        try:
            return StandingGrantKey(GITHUB_REPOSITORY, goal_id, thread_id)
        except (TypeError, ValueError) as exc:
            raise GatewayInputError(f"OWNER_AUTHORITY_KEY_REQUIRED:{exc}") from exc

    @staticmethod
    def _assist_command(
        *,
        executable: str,
        provider: str,
        model: str,
        prompt: str,
        explicit_effort: str = "",
        agy_print_timeout: str = AGY_PRINT_TIMEOUT,
    ) -> list[str]:
        if provider == "cline":
            selected = model or "glm-5.2"
            if "/" not in selected:
                selected = f"cline-pass/{selected}"
            return [executable, "--json", "--plan", "--auto-approve", "false", "--thinking", "none", "--timeout", str(CLINE_RUN_TIMEOUT_SECONDS), "--model", selected, prompt]
        if provider == "agy":
            return _compile_agy_command(
                executable=executable,
                model=model,
                prompt=prompt,
                explicit_effort=explicit_effort,
                print_timeout=agy_print_timeout,
            )
        if provider == "gemini":
            return [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", model, "-p", prompt, "--output-format", "json"]
        if provider == "opencode":
            return [executable, "run", "--model", model, prompt]
        if provider == "mimo":
            return [executable, "run", "--never-ask-questions", "--model", model, prompt]
        if provider == "ollama":
            return [executable, "run", model, prompt]
        if provider == "grok":
            return [executable, "--model", model, "--single", prompt, "--output-format", "json", "--no-alt-screen"]
        if provider == "codex":
            return [executable, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "-m", model, prompt]
        raise GatewayInputError("ASSIST_ASYNC_PROVIDER_UNSUPPORTED")

    @staticmethod
    def _safe_slug(value: Any, field: str, *, max_length: int = 80) -> str:
        result = _text(value, field, max_length=max_length)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0," + str(max_length - 1) + r"}", result):
            raise GatewayInputError(f"{field} must be a stable bounded slug")
        return result

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _task_card_create(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments.get("owner_confirmation") is not True:
            raise GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        _require_bound_controller()
        owner_key = self._owner_effect_key(arguments)
        campaign = self._safe_slug(arguments.get("campaign_id"), "campaign_id")
        task_id = self._safe_slug(arguments.get("task_id"), "task_id")
        objective = _text(arguments.get("objective"), "objective", max_length=4000)
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 10:
            raise GatewayInputError("allowed_files must contain 1-10 bounded paths")
        for path in allowed:
            resolved_path = _safe_relative_path(path, "allowed_files")
            # #1750: a card must never authorize authority-bearing paths, named
            # directly or through a symlink. This runs before any authority
            # check, record or file write.
            reason = protected_path_reason(path) or protected_path_reason(
                resolved_path.relative_to(CANONICAL_SOURCE_ROOT).as_posix()
            )
            if reason is not None:
                raise GatewayInputError(f"TASK_CARD_CREATE_PROTECTED_PATH:{reason}:{path}")
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or [] if str(command).strip()]
        if not verifiers:
            raise GatewayInputError("verifier_commands is required")
        universe = self._task_card_expected_evidence(arguments)
        head = self._exact_hash(_git("rev-parse", "HEAD").strip(), "expected_head", 40)
        effect: dict[str, Any] = {
            "campaign_id": campaign,
            "task_id": task_id,
            "expected_head": head,
            "allowed_files": allowed,
            "verifier_commands": verifiers,
            "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
        }
        if universe is not None:
            # Bind the Owner authorization to the exact declared universe.
            effect["expected_evidence_identity"] = universe.universe_identity
        owner_authority = self._require_owner_effect_authority(
            AutonomyActionClass.TASK_CARD_CREATE,
            effect,
            key=owner_key,
        )
        campaign_root = CANONICAL_SOURCE_ROOT / "tasks" / campaign
        index_path = campaign_root / "INDEX.md"
        card_path = campaign_root / f"00-{task_id}.md"
        if campaign_root.exists() or index_path.exists() or card_path.exists():
            raise GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
        card = "\n".join([
            f"# Task Card: {task_id}", "", "artifact_authority: current", f"task_id: `{task_id}`",
            "owner: James Chen", "status: ACTIVE", "execution_lane: GOVERNED",
            "commit_required: true", "candidate_required: true", "worker_may_commit: true",
            "worker_may_approve: false", "worker_may_integrate: false",
            "worker_may_push: false", "AUTO_CHAIN: false", "", "## Objective", "", objective, "",
            "## Allowed files", "", *[f"- `{path}`" for path in allowed], "", "## Verification commands", "",
            "```bash", *verifiers, "```", "",
            *(
                []
                if universe is None
                else [
                    "## Expected evidence", "",
                    "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE, universe.canonical_json(), "```", "",
                ]
            ),
            "## Exit criteria", "", "Owner review of the exact scoped commit.",
            "", "## Block classification", "", "Unverifiable or out-of-scope mutation is a HARD_BLOCK.", "",
        ])
        # The hashed card is the only universe source (#2181): the rendered card
        # must read back as exactly the validated universe, or as none at all.
        # This also stops objective or verifier text from smuggling in a block.
        try:
            declared = parse_task_card_expected_evidence(card)
        except ValueError as exc:
            raise GatewayInputError("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text declares a malformed block") from exc
        if declared != (None if universe is None else universe.model_dump(mode="json")):
            raise GatewayInputError("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text does not round-trip")
        index = "\n".join([
            f"# Campaign Index: {campaign}", "", "artifact_authority: current", "owner: James Chen",
            "status: active, governed and sequential", "AUTO_CHAIN: false", "", "## Objective", "", objective,
            "", "## Ordered cards", "", "| Order | Task ID | Card | Status | Dependency |", "|---:|---|---|---|---|",
            f"| 0 | `{task_id}` | `00-{task_id}.md` | ACTIVE | Owner confirmation |", "",
        ])
        tasks_root = CANONICAL_SOURCE_ROOT / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        temporary_root = tasks_root / f".{campaign}.create-{uuid4().hex}"
        try:
            temporary_root.mkdir(parents=False, exist_ok=False)
            temporary_index = temporary_root / "INDEX.md"
            temporary_card = temporary_root / f"00-{task_id}.md"
            temporary_index.write_text(index, encoding="utf-8")
            temporary_card.write_text(card, encoding="utf-8")
            if not temporary_index.is_file() or not temporary_card.is_file():
                raise RuntimeError("TASK_CARD_CREATE_ATOMIC_WRITE_FAILED")
            hashed = subprocess.run(["git", "hash-object", str(temporary_card)], cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
            card_hash = hashed.stdout.strip()
            if hashed.returncode != 0 or not _SHA_RE.fullmatch(card_hash):
                raise RuntimeError("TASK_CARD_CREATE_HASH_FAILED")
            card_sha256 = hashlib.sha256(card.encode("utf-8")).hexdigest()
            if campaign_root.exists():
                raise GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
            os.replace(temporary_root, campaign_root)
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        diff_lines = list(difflib.unified_diff([], card.splitlines(True), fromfile="/dev/null", tofile=str(card_path.relative_to(CANONICAL_SOURCE_ROOT))))
        index_diff_lines = list(difflib.unified_diff([], index.splitlines(True), fromfile="/dev/null", tofile=str(index_path.relative_to(CANONICAL_SOURCE_ROOT))))
        return {
            "schema": "nexus.task_card_create.v1",
            "status": "CREATED_PENDING_COMMIT",
            "campaign_id": campaign,
            "task_id": task_id,
            "index_path": str(index_path.relative_to(CANONICAL_SOURCE_ROOT)),
            "card_path": str(card_path.relative_to(CANONICAL_SOURCE_ROOT)),
            "card_hash": card_sha256,
            "index_hash": hashlib.sha256(index.encode("utf-8")).hexdigest(),
            "git_blob_sha": card_hash,
            "exact_card_diff": "".join(diff_lines),
            "exact_index_diff": "".join(index_diff_lines),
            "successor_execution": "NOT_STARTED",
            "authority_basis": bootstrap_agent_authority.authority_basis(owner_authority),
            "owner_confirmation": bootstrap_agent_authority.authority_basis(owner_authority)
            == bootstrap_agent_authority.BASIS_OWNER_GRANT,
            "owner_authority": owner_authority,
        }

    @staticmethod
    def _task_card_expected_evidence(arguments: Mapping[str, Any]) -> Optional[ExpectedEvidenceUniverse]:
        """Validate the optional card-declared universe with the card reader's model."""
        raw = arguments.get("expected_evidence")
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise GatewayInputError("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:expected_evidence must be an object")
        try:
            return ExpectedEvidenceUniverse.model_validate(dict(raw))
        except ValueError as exc:
            reason = " ".join(str(exc).split())[:500]
            raise GatewayInputError(f"TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:{reason}") from exc

    def _task_card_commit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments.get("owner_confirmation") is not True:
            raise GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        _require_bound_controller()
        owner_key = self._owner_effect_key(arguments)
        campaign = self._safe_slug(arguments.get("campaign_id"), "campaign_id")
        task_id = self._safe_slug(arguments.get("task_id"), "task_id")
        expected_head = str(arguments.get("expected_head") or "").strip().lower()
        expected_card_hash = str(arguments.get("card_hash") or "").strip().lower()
        expected_index_hash = str(arguments.get("index_hash") or "").strip().lower()
        if not _SHA_RE.fullmatch(expected_head):
            raise GatewayInputError("expected_head must be a lowercase 40-hex SHA")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_card_hash):
            raise GatewayInputError("card_hash must be a lowercase 64-hex SHA-256")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_index_hash):
            raise GatewayInputError("index_hash must be a lowercase 64-hex SHA-256")

        campaign_root = CANONICAL_SOURCE_ROOT / "tasks" / campaign
        index_path = campaign_root / "INDEX.md"
        card_path = campaign_root / f"00-{task_id}.md"
        if not index_path.is_file() or not card_path.is_file():
            raise GatewayInputError("TASK_CARD_COMMIT_SOURCE_MISSING")
        for path in (index_path, card_path):
            if path.is_symlink():
                raise GatewayInputError("TASK_CARD_COMMIT_SYMLINK_FORBIDDEN")
            try:
                path.resolve().relative_to(CANONICAL_SOURCE_ROOT.resolve())
            except ValueError as exc:
                raise GatewayInputError("TASK_CARD_COMMIT_PATH_ESCAPE") from exc

        card_bytes = card_path.read_bytes()
        index_bytes = index_path.read_bytes()
        card_text = card_bytes.decode("utf-8")
        index_text = index_bytes.decode("utf-8")
        if hashlib.sha256(card_bytes).hexdigest() != expected_card_hash:
            raise GatewayInputError("TASK_CARD_COMMIT_HASH_MISMATCH")
        if hashlib.sha256(index_bytes).hexdigest() != expected_index_hash:
            raise GatewayInputError("TASK_CARD_COMMIT_INDEX_HASH_MISMATCH")
        if f"task_id: `{task_id}`" not in card_text or "status: ACTIVE" not in card_text or "AUTO_CHAIN: false" not in card_text:
            raise GatewayInputError("TASK_CARD_COMMIT_CARD_NOT_ACTIVE")
        if f"# Campaign Index: {campaign}" not in index_text or "AUTO_CHAIN: false" not in index_text:
            raise GatewayInputError("TASK_CARD_COMMIT_INDEX_NOT_BOUND")

        current_head = _git("rev-parse", "HEAD").strip()
        if current_head != expected_head:
            raise GatewayInputError("TASK_CARD_COMMIT_HEAD_MISMATCH")
        _require_bound_controller(expected_head)
        owner_authority = self._require_owner_effect_authority(
            AutonomyActionClass.TASK_CARD_COMMIT,
            {
                "campaign_id": campaign,
                "task_id": task_id,
                "expected_head": expected_head,
                "card_hash": expected_card_hash,
                "index_hash": expected_index_hash,
            },
            key=owner_key,
        )
        branch = subprocess.run(
            ["git", "symbolic-ref", "-q", "--short", "HEAD"],
            cwd=CANONICAL_SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if branch.returncode == 0 and branch.stdout.strip():
            raise GatewayInputError("TASK_CARD_COMMIT_REQUIRES_DETACHED_CONTROLLER")
        if branch.returncode not in (0, 1):
            raise RuntimeError(branch.stderr.strip() or "failed to inspect controller branch state")

        index_rel = str(index_path.relative_to(CANONICAL_SOURCE_ROOT))
        card_rel = str(card_path.relative_to(CANONICAL_SOURCE_ROOT))
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=CANONICAL_SOURCE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3.0,
            check=False,
        )
        if status.returncode != 0:
            raise RuntimeError(status.stderr.decode("utf-8", errors="replace").strip() or "git status failed")
        entries = {os.fsdecode(raw) for raw in status.stdout.split(b"\0") if raw}
        expected_entries = {f"?? {index_rel}", f"?? {card_rel}"}
        if entries != expected_entries:
            raise GatewayInputError("TASK_CARD_COMMIT_CONTROLLER_NOT_EXACTLY_PENDING_CARD")

        _git("add", "--", index_rel, card_rel)
        staged = {line for line in _git("diff", "--cached", "--name-only", "--", index_rel, card_rel).splitlines() if line}
        if staged != {index_rel, card_rel}:
            _git("reset", "--", index_rel, card_rel)
            raise RuntimeError("TASK_CARD_COMMIT_STAGE_MISMATCH")

        def staged_sha256(relative: str) -> str:
            result = subprocess.run(
                ["git", "show", f":{relative}"],
                cwd=CANONICAL_SOURCE_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3.0,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "failed to read staged task-card content")
            return hashlib.sha256(result.stdout).hexdigest()

        try:
            if staged_sha256(card_rel) != expected_card_hash or staged_sha256(index_rel) != expected_index_hash:
                raise RuntimeError("TASK_CARD_COMMIT_STAGED_HASH_MISMATCH")
            _git("commit", "-m", f"chore(tasks): bind {task_id}", timeout=30.0)
        except Exception:
            _git("reset", "--", index_rel, card_rel)
            raise

        commit_sha = _git("rev-parse", "HEAD").strip()
        parent_sha = _git("rev-parse", "HEAD^").strip()
        tree_sha = _git("rev-parse", "HEAD^{tree}").strip()
        if parent_sha != expected_head or not _SHA_RE.fullmatch(commit_sha) or not _SHA_RE.fullmatch(tree_sha):
            raise RuntimeError("TASK_CARD_COMMIT_IDENTITY_MISMATCH")
        remaining = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=CANONICAL_SOURCE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3.0,
            check=False,
        )
        if remaining.returncode != 0:
            raise RuntimeError(remaining.stderr.decode("utf-8", errors="replace").strip() or "git status failed")
        if remaining.stdout:
            raise RuntimeError("TASK_CARD_COMMIT_CONTROLLER_NOT_CLEAN_AFTER_COMMIT")
        committed_paths = {
            line for line in _git("diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha).splitlines() if line
        }
        if committed_paths != {index_rel, card_rel}:
            raise RuntimeError("TASK_CARD_COMMIT_SCOPE_MISMATCH")
        return {
            "schema": "nexus.task_card_commit.v1",
            "status": "COMMITTED",
            "campaign_id": campaign,
            "task_id": task_id,
            "previous_head": expected_head,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "index_path": index_rel,
            "card_path": card_rel,
            "card_hash": expected_card_hash,
            "index_hash": expected_index_hash,
            "committed_paths": sorted(committed_paths),
            "controller_clean": True,
            "successor_execution": "READY_FOR_GOVERNED_START",
            "authority_basis": bootstrap_agent_authority.authority_basis(owner_authority),
            "owner_confirmation": bootstrap_agent_authority.authority_basis(owner_authority)
            == bootstrap_agent_authority.BASIS_OWNER_GRANT,
            "owner_authority": owner_authority,
        }

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
            raise GatewayInputError("OWNER_CONFIRMATION_PARAMETER_REMOVED")
        unknown_keys = set(arguments.keys()) - allowed_keys
        if unknown_keys:
            raise GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        if str(arguments.get("repository") or "").strip() != GITHUB_REPOSITORY.repository_id:
            raise GatewayInputError("STANDING_GRANT_REPOSITORY_MISMATCH")

        coordinator_id = _text(arguments.get("coordinatorId"), "coordinatorId", max_length=128)
        goal_id = _text(arguments.get("goalId"), "goalId", max_length=128)
        coordination_scope_id = _text(
            arguments.get("coordinationScopeId"),
            "coordinationScopeId",
            max_length=128,
        )

        raw_actions = arguments.get("allowedActions")
        if not isinstance(raw_actions, list) or not raw_actions or len(raw_actions) > 8:
            raise GatewayInputError("allowedActions must contain between 1 and 8 actions")
        parsed_actions: list[AutonomyActionClass] = []
        for raw_action in raw_actions:
            try:
                action = AutonomyActionClass(str(raw_action))
            except ValueError as exc:
                raise GatewayInputError(f"STANDING_GRANT_ACTION_INVALID:{raw_action}") from exc
            if action in parsed_actions:
                raise GatewayInputError("STANDING_GRANT_ACTION_DUPLICATE")
            if action in _SCOPE_ENFORCEMENT_REQUIRED_ACTIONS:
                raise GatewayInputError(
                    f"STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT:{action.value}"
                )
            parsed_actions.append(action)
        parsed_actions.sort(key=lambda action: action.value)

        raw_ttl = arguments.get("ttlMinutes")
        if isinstance(raw_ttl, bool) or not isinstance(raw_ttl, int) or not 1 <= raw_ttl <= 60:
            raise GatewayInputError("ttlMinutes must be an integer between 1 and 60")

        issued_raw = _text(arguments.get("issuedAt"), "issuedAt", max_length=64)
        try:
            issued_at = datetime.fromisoformat(issued_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GatewayInputError("STANDING_GRANT_ISSUED_AT_INVALID") from exc
        if issued_at.tzinfo is None:
            raise GatewayInputError("STANDING_GRANT_ISSUED_AT_TIMEZONE_REQUIRED")
        issued_at = issued_at.astimezone(timezone.utc)
        expires_at = issued_at + timedelta(minutes=raw_ttl)
        now = datetime.now(timezone.utc)
        if issued_at > now + timedelta(minutes=1):
            raise GatewayInputError("STANDING_GRANT_ISSUED_AT_FUTURE")
        if now >= expires_at:
            raise GatewayInputError("STANDING_GRANT_REQUEST_EXPIRED")

        expected_current = arguments.get("expectedCurrentReceiptHash")
        if expected_current is not None:
            expected_current = _text(
                expected_current,
                "expectedCurrentReceiptHash",
                max_length=64,
            ).lower()
            if not _SHA64_RE.fullmatch(expected_current):
                raise GatewayInputError(
                    "expectedCurrentReceiptHash must be a lowercase 64-hex SHA-256"
                )

        context = StandingGrantContext.issue(
            owner_id="James3014",
            coordinator_id=coordinator_id,
            repository=GITHUB_REPOSITORY,
            thread_id=coordination_scope_id,
            goal_id=goal_id,
            allowed_actions=tuple(parsed_actions),
            issued_at=issued_at,
            expires_at=expires_at,
        )
        request_identity = {
            "repository": GITHUB_REPOSITORY.repository_id,
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
        receipt = StandingGrantReceipt.issue(
            grant_id=f"owner-{request_hash[:24]}",
            context=context,
            supersedes_grant_hash=expected_current,
        )
        def ask_owner() -> dict[str, Any]:
            return self._confirm_with_owner(
                tool="nexus_owner_standing_grant_issue",
                draft={**request_identity, "ownerId": context.owner_id, "receiptHash": receipt.receipt_hash},
                summary_lines=(
                    f"Repository: {GITHUB_REPOSITORY.repository_id}",
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
        key = StandingGrantKey(
            GITHUB_REPOSITORY,
            goal_id,
            coordination_scope_id,
        )

        try:
            current = load_keyed_standing_grant_receipt_structural(key)
            if current is None:
                current_hash = None
            else:
                if current.context.revoked_at is not None:
                    raise StandingGrantReceiptError("REVOKED")
                if now < current.context.issued_at:
                    raise StandingGrantReceiptError("NOT_YET_VALID")
                current_hash = current.receipt_hash

            if current_hash == receipt.receipt_hash:
                status = "REPLAYED"
            else:
                if current_hash is None and expected_current is not None:
                    raise StandingGrantReceiptError("EXPECTED_PREDECESSOR_MISSING")
                if current_hash is not None and expected_current is None:
                    raise StandingGrantReceiptError("CURRENT_RECEIPT_EXISTS_CAS_REQUIRED")
                if (
                    current_hash is not None
                    and expected_current is not None
                    and current_hash != expected_current
                ):
                    raise StandingGrantReceiptError("CAS_MISMATCH")
                # Ask only once the write is otherwise admissible; the store
                # re-checks the predecessor (CAS) when the write happens.
                confirmation = ask_owner()
                write_keyed_standing_grant_receipt(
                    receipt,
                    expected_receipt_hash=expected_current,
                )
                rebound = load_keyed_standing_grant_receipt(key, now=now)
                if rebound is None or rebound.receipt_hash != receipt.receipt_hash:
                    raise StandingGrantReceiptError("ISSUANCE_READBACK_MISMATCH")
                status = "ISSUED"
                self._append_owner_confirmation_audit(
                    {
                        "schema": "nexus.owner_confirmation_outcome.v1",
                        "evidence_hash": confirmation["evidence_hash"],
                        "outcome": status,
                        "receipt_hash": receipt.receipt_hash,
                    }
                )
        except StandingGrantReceiptError as exc:
            raise GatewayInputError(str(exc)) from exc

        return {
            "schema": "nexus.owner_standing_grant_issuance.v1",
            "status": status,
            "repository": GITHUB_REPOSITORY.repository_id,
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
        request = OwnerConfirmationRequest.build(
            tool=tool,
            draft=draft,
            summary_lines=summary_lines,
            now=now,
            not_after=not_after,
        )
        try:
            evidence = self._owner_confirmation_channel.confirm(request)
        except OwnerConfirmationError as exc:
            raise GatewayInputError(str(exc)) from exc
        if evidence.draft_hash != request.draft_hash or evidence.request_id != request.request_id:
            raise GatewayInputError("OWNER_CONFIRMATION_BINDING_MISMATCH")
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
        directory = _standing_grant_store_module.DEFAULT_RECEIPT_PATH.parent
        try:
            _standing_grant_store_module._assert_dir_chain_safe(directory, create=True)
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
        except (OSError, _standing_grant_store_module.StandingGrantReceiptError) as exc:
            raise GatewayInputError("OWNER_CONFIRMATION_AUDIT_WRITE_FAILED") from exc

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
            raise GatewayInputError("OWNER_CONFIRMATION_PARAMETER_REMOVED")
        unknown_keys = set(arguments.keys()) - allowed_keys
        if unknown_keys:
            raise GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        attempt_key = _text(arguments.get("attemptKey"), "attemptKey", max_length=128)
        expected_current_receipt_hash = _text(
            arguments.get("expectedCurrentReceiptHash"),
            "expectedCurrentReceiptHash",
            max_length=64,
        ).lower()
        if not _SHA64_RE.fullmatch(expected_current_receipt_hash):
            raise GatewayInputError("expectedCurrentReceiptHash must be a lowercase 64-hex SHA-256")
        expected_current_goal_id = _text(
            arguments.get("expectedCurrentGoalId"),
            "expectedCurrentGoalId",
            max_length=128,
        )
        expected_current_thread_id = _text(
            arguments.get("expectedCurrentThreadId"),
            "expectedCurrentThreadId",
            max_length=128,
        )
        successor_goal_id = _text(
            arguments.get("successorGoalId"),
            "successorGoalId",
            max_length=128,
        )
        successor_thread_id = _text(
            arguments.get("successorThreadId"),
            "successorThreadId",
            max_length=128,
        )
        raw_ttl = arguments.get("ttlMinutes")
        if raw_ttl is None:
            raise GatewayInputError("ttlMinutes is required")
        if isinstance(raw_ttl, bool) or not isinstance(raw_ttl, int) or raw_ttl < 1 or raw_ttl > 30:
            raise GatewayInputError("ttlMinutes must be an integer between 1 and 30")
        ttl_minutes = raw_ttl
        now = datetime.now(timezone.utc)
        self._confirm_with_owner(
            tool="nexus_task_card_authority_switch",
            draft={
                "repository": GITHUB_REPOSITORY.repository_id,
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
                f"Repository: {GITHUB_REPOSITORY.repository_id}",
                f"From grant: {expected_current_receipt_hash} (goal {expected_current_goal_id})",
                f"New task-card scope: goal {successor_goal_id}, thread {successor_thread_id}",
                "Allowed actions: TASK_CARD_COMMIT, TASK_CARD_CREATE",
                f"Valid for: {ttl_minutes} minutes (never beyond the current grant)",
            ),
            now=now,
            not_after=now + timedelta(minutes=ttl_minutes),
        )

        try:
            return switch_task_card_authority(
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
        except StandingGrantReceiptError as exc:
            raise GatewayInputError(str(exc)) from exc

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
            raise GatewayInputError(f"unknown arguments: {', '.join(sorted(unknown_keys))}")
        owner_confirmation = arguments.get("ownerConfirmation")
        if owner_confirmation is not True:
            raise GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        attempt_key = _text(arguments.get("attemptKey"), "attemptKey", max_length=128)
        switch_operation_id = _text(
            arguments.get("switchOperationId"),
            "switchOperationId",
            max_length=128,
        )
        expected_temporary_receipt_hash = _text(
            arguments.get("expectedTemporaryReceiptHash"),
            "expectedTemporaryReceiptHash",
            max_length=64,
        ).lower()
        expected_current_goal_id = _text(
            arguments.get("expectedCurrentGoalId"), "expectedCurrentGoalId", max_length=128
        )
        expected_current_thread_id = _text(
            arguments.get("expectedCurrentThreadId"), "expectedCurrentThreadId", max_length=128
        )
        if not _SHA64_RE.fullmatch(expected_temporary_receipt_hash):
            raise GatewayInputError(
                "expectedTemporaryReceiptHash must be a lowercase 64-hex SHA-256"
            )

        try:
            return restore_task_card_authority(
                current_key=self._standing_key(
                    expected_current_goal_id, expected_current_thread_id
                ),
                attempt_key=attempt_key,
                switch_operation_id=switch_operation_id,
                expected_temporary_receipt_hash=expected_temporary_receipt_hash,
                owner_confirmation=True,
            )
        except StandingGrantReceiptError as exc:
            raise GatewayInputError(str(exc)) from exc

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        recovery_request_schema = {
            "type": "object",
            "required": [
                "request_id",
                "idempotency_fence",
                "operation",
                "effect_class",
                "recovery_authority_id",
                "recovery_authority_hash",
                "desired_manifest_id",
                "desired_manifest_hash",
                "predecessor_manifest_id",
                "predecessor_manifest_hash",
                "request_hash",
                "schema",
            ],
            "properties": {
                "request_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                },
                "idempotency_fence": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                },
                "operation": {"type": "string", "enum": ["gateway-recover"]},
                "effect_class": {
                    "type": "string",
                    "enum": ["GATEWAY_DURABLE_RECOVERY"],
                },
                "recovery_authority_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                },
                "recovery_authority_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "desired_manifest_id": {
                    "type": "string",
                    "pattern": "^r1-[0-9a-f]{40}$",
                },
                "desired_manifest_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "predecessor_manifest_id": {
                    "type": "string",
                    "pattern": "^r1-[0-9a-f]{40}$",
                },
                "predecessor_manifest_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "request_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "schema": {
                    "type": "string",
                    "enum": ["nexus.gateway.durable_recovery_request.v2"],
                },
            },
            "additionalProperties": False,
        }
        materialization_request_schema = {
            "type": "object",
            "required": [
                "request_id",
                "idempotency_fence",
                "operation",
                "effect_class",
                "recovery_authority_id",
                "recovery_authority_hash",
                "request_hash",
                "schema",
            ],
            "properties": {
                "request_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                },
                "idempotency_fence": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                },
                "operation": {
                    "type": "string",
                    "enum": ["gateway-recovery-materialize"],
                },
                "effect_class": {
                    "type": "string",
                    "enum": ["GATEWAY_RECOVERY_MATERIALIZATION"],
                },
                "recovery_authority_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                },
                "recovery_authority_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "request_hash": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "schema": {
                    "type": "string",
                    "enum": [
                        "nexus.gateway.durable_recovery_materialization_request.v1"
                    ],
                },
            },
            "additionalProperties": False,
        }
        return [
            {
                "name": "nexus_gateway_status",
                "description": "Read the single gateway identity, manifest, route stages, and lifecycle counts.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_gateway_recovery_materialize",
                "description": (
                    "Materialize one exact protected #526 recovery authority into the "
                    "repository-owned manager stores. This starts no Gateway host effect."
                ),
                "inputSchema": materialization_request_schema,
            },
            {
                "name": "nexus_gateway_recovery_preflight",
                "description": (
                    "Run the existing repository-owned #526 recovery manager to the "
                    "effect-free TARGET_READY + ROLLBACK_READY checkpoint."
                ),
                "inputSchema": copy.deepcopy(recovery_request_schema),
            },
            {
                "name": "nexus_gateway_recover",
                "description": (
                    "Execute or reconcile one exact protected #526 Gateway recovery "
                    "request through the existing durable manager state machine."
                ),
                "inputSchema": copy.deepcopy(recovery_request_schema),
            },
            {
                "name": "nexus_project_entry",
                "description": (
                    "Freshly observe one GitHub Issue and rehydrate only its exact "
                    "canonical task binding; observe-only."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["repository_owner", "repository_name", "issue_number"],
                    "properties": {
                        "repository_owner": {"type": "string", "maxLength": 128},
                        "repository_name": {"type": "string", "maxLength": 128},
                        "issue_number": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_mutation_admit",
                "description": (
                    "Issue one durable Nexus-owned, transport-neutral repository mutation admission. "
                    "This records repo/base/lane/authority/scope only and grants no route, execution, "
                    "verification, acceptance, merge, release, deployment, or production authority."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": [
                        "operation_id",
                        "repository",
                        "base_sha",
                        "execution_lane",
                        "authority_kind",
                        "allowed_paths",
                    ],
                    "properties": {
                        "operation_id": {"type": "string", "maxLength": 128},
                        "repository": {
                            "type": "string",
                            "enum": ["James3014/devspace","James3014/Nexus-new","James3014/nexus-core","James3014/nexus-learning","James3014/nexus-open-swe-runtime","James3014/repository-intelligence-engine","James3014/nexus-runtime","James3014/nexus-opencli-reviewer","James3014/nexus-deployment-lab"],
                        },
                        "base_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "execution_lane": {
                            "type": "string",
                            "enum": ["DIRECT_CANONICAL", "DIRECT_DELEGATED", "GOVERNED"],
                        },
                        "authority_kind": {
                            "type": "string",
                            "enum": ["OWNER_INLINE", "TRACKED_TASK_CARD"],
                        },
                        "allowed_paths": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 1024},
                            "minItems": 1,
                            "maxItems": 64,
                        },
                        "authority_goal_id": {"type": "string", "maxLength": 128},
                        "authority_coordination_scope_id": {"type": "string", "maxLength": 128},
                        "issue_number": {"type": "integer", "minimum": 1},
                        "task_id": {"type": "string", "maxLength": 128},
                        "attempt_id": {"type": "string", "maxLength": 128},
                        "task_card_path": {"type": "string", "maxLength": 1024},
                        "task_card_hash": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{64}$",
                        },
                        "ttl_minutes": {
                            "type": "integer",
                            "minimum": 5,
                            "maximum": 43200,
                            "default": 10080,
                        },
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_mutation_admission_status",
                "description": (
                    "Read and revalidate one exact durable Nexus mutation admission receipt. "
                    "Observe-only; this grants no new mutation or integration authority."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["admission_id", "receipt_hash"],
                    "properties": {
                        "admission_id": {"type": "string", "maxLength": 64},
                        "receipt_hash": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{64}$",
                        },
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_gateway_convergence",
                "description": (
                    "Classify one policy-driven desired-vs-loaded Gateway convergence generation. "
                    "Decision-only: never reloads, restarts, grants recovery authority, or retries "
                    "an ambiguous effect. Routine deploys are the #2153 auto-deployer's (no Owner "
                    "activation, #2155); its recovery next actions name the manual issue #526 "
                    "emergency path."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": ["policy", "readiness_state", "quiescence_state"],
                    "properties": {
                        "policy": {
                            "type": "object",
                            "required": ["mode", "desired_commit", "desired_tree"],
                            "properties": {
                                "mode": {
                                    "type": "string",
                                    "enum": ["PINNED", "TRACK_ACCEPTED_MAIN"],
                                },
                                "desired_commit": {
                                    "type": "string",
                                    "pattern": "^[0-9a-f]{40}$",
                                },
                                "desired_tree": {
                                    "type": "string",
                                    "pattern": "^[0-9a-f]{40}$",
                                },
                            },
                            "additionalProperties": False,
                        },
                        "readiness_state": {
                            "type": "string",
                            "enum": ["SAFE", "BLOCKED", "UNKNOWN"],
                        },
                        "quiescence_state": {
                            "type": "string",
                            "enum": ["SAFE", "BLOCKED", "UNKNOWN"],
                        },
                        "active_effect": {
                            "type": ["object", "null"],
                        },
                        "not_before": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_execution_readiness",
                "description": (
                    "Evaluate the pre-execution readiness convergence gate: exactly one typed "
                    "result, READY_TO_EXECUTE or one primary blocker with a canonical next "
                    "action. Observe-only; never repairs, reloads, routes, admits, or certifies."
                ),
                "inputSchema": {
                    "type": "object",
                    "required": [
                        "repository_owner",
                        "repository_name",
                        "intended_source_commit",
                        "intended_source_tree",
                        "execution_realm",
                        "required_action_family",
                        "execution_contract_kind",
                    ],
                    "properties": {
                        "repository_owner": {"type": "string", "maxLength": 128},
                        "repository_name": {"type": "string", "maxLength": 128},
                        "intended_source_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "intended_source_tree": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "task_campaign_goal_identity": {"type": "string", "maxLength": 4096},
                        "durable_coordination_scope_id": {"type": "string", "maxLength": 4096},
                        "durable_repository_canonical_remote": {"type": "string", "maxLength": 4096},
                        "desired_deployment_identity": {"type": "string", "maxLength": 4096},
                        "execution_realm": {"type": "string", "enum": ["in_process_preflight"]},
                        "required_action_family": {"type": "string", "maxLength": 128},
                        "execution_contract_kind": {"type": "string", "maxLength": 128},
                        "worker_constraints": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 256},
                            "maxItems": 8,
                        },
                        "workforce_dispatch_binding": {
                            "type": "object",
                            "required": [
                                "planner_output", "workforce_demands", "workforce_admission",
                                "canonical_dispatch_envelope", "task_id", "attempt_id",
                                "task_card_path", "task_card_hash",
                            ],
                            "properties": {
                                "planner_output": {"type": "object"},
                                "workforce_demands": {"type": "object"},
                                "workforce_admission": {"type": "object"},
                                "canonical_dispatch_envelope": {"type": "object"},
                                "task_id": {"type": "string"},
                                "attempt_id": {"type": "string"},
                                "task_card_path": {"type": "string"},
                                "task_card_hash": {"type": "string"},
                            },
                            "additionalProperties": False,
                        },
                        "required_completion_contract": {
                            "type": "object",
                            "required": [
                                "authority_kind",
                                "repository",
                                "artifact_or_source_identity",
                                "interface_revision",
                            ],
                            "properties": {
                                "authority_kind": {"type": "string"},
                                "repository": {"type": "string"},
                                "artifact_or_source_identity": {"type": "string"},
                                "interface_revision": {"type": "string"},
                                "required_capabilities": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 8,
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_workspace_snapshot",
                "description": "Read the canonical checkout snapshot without creating state or a Target.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "nexus_read",
                "description": "Read a bounded UTF-8 file inside the canonical checkout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "minimum": 1, "default": 1},
                        "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
                    },
                },
            },
            {
                "name": "nexus_search",
                "description": "Search bounded literal text inside one canonical relative path.",
                "inputSchema": {
                    "type": "object",
                    "required": ["pattern"],
                    "properties": {
                        "pattern": {"type": "string", "maxLength": 200},
                        "path": {"type": "string", "default": "."},
                    },
                },
            },
            {
                "name": "nexus_git_diff",
                "description": "Read a bounded canonical diff; no arbitrary Git flags are accepted.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "base_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "staged": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_task_run",
                "description": "Run one bounded task through the canonical Planner, Online/Local runtime, verifier, and RootReceipt path.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "maxItems": 1},
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "nexus_worker_candidate",
                "description": "Submit one tracked-card worker candidate through canonical planner/admission dispatch.",
                "inputSchema": {
                    "type": "object",
                    "required": [
                        "what", "why", "allowed_files", "verifier_commands",
                        "owner_confirmation", "task_card_path", "task_card_hash",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "task_id": {"type": "string", "maxLength": 80},
                        "what": {"type": "string", "maxLength": 4000},
                        "why": {"type": "string", "maxLength": 4000},
                        "worker": {"type": "string", "maxLength": 128},
                        "provider": {"type": "string", "maxLength": 128},
                        "model": {"type": "string", "maxLength": 256},
                        "task_card_path": {"type": "string", "pattern": "^tasks/.+\\.md$"},
                        "task_card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                        "owner_confirmation": {"type": "boolean", "const": True},
                        "authority_change_candidate_confirmation": {"type": "boolean", "default": False},
                        "fail_to_pass_required": {"type": "boolean", "default": False},
                        "workforce_demands": {"type": "object"},
                        "workforce_admission": {"type": "object"},
                        "planner_output": {"type": "object"},
                    },
                },
            },
            {
                "name": "nexus_task_status",
                "description": "Read one durable task's status and next action.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_wait",
                "description": "Poll one bounded lifecycle task until attention, terminal, or timeout.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 60, "default": 10},
                        "poll_interval_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 5, "default": 0.25},
                    },
                },
            },
            {
                "name": "nexus_task_finish",
                "description": "Finish a Direct receipt or owner-finish an exact isolated Candidate binding.",
                "inputSchema": {
                    "type": "object",
                    "required": ["execution_lane"],
                    "properties": {
                        "execution_lane": {"type": "string", "enum": ["DIRECT_CANONICAL", "ISOLATED_TARGET"]},
                        "request": {"type": "object"},
                        "base_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "controller_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "expected_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            {
                "name": "nexus_task_cancel",
                "description": "Cancel one non-running lifecycle task through formal cleanup authority.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_list_actionable",
                "description": "List durable tasks that require exactly one recovery or owner action.",
                "inputSchema": {"type": "object", "properties": {"include_details": {"type": "boolean", "default": False}}},
            },
            {
                "name": "nexus_task_reconcile",
                "description": "Reconcile one uncertain task from durable evidence without replaying a mutation.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_retry",
                "description": "Retry one terminal task with the same task_id and a new attempt_id after cleanup.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_task_resume",
                "description": "Resume one durable task only from its recorded execution evidence.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_assist_submit",
                "description": "Submit a durable Assisted Cline provider job and return immediately.",
                "inputSchema": {
                    "type": "object",
                    "required": ["what", "why", "allowed_files"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "what": {"type": "string"},
                        "why": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "provider": {"type": "string", "enum": ["cline"], "default": "cline"},
                        "model": {"type": "string", "default": "glm-5.2"},
                        "apply": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "nexus_assist_result",
                "description": "Read the durable Assisted provider result for one task after disconnect or timeout.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_assist_cancel",
                "description": "Cancel one running Assisted provider job without applying a candidate.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_provider_preflight",
                "description": "Verify a registered provider binary, version, identity, and optional exact-model probe.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider"],
                    "properties": {
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "probe": {"type": "boolean", "default": False},
                        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 60, "default": 30},
                    },
                },
            },
            {
                "name": "nexus_task_card_create",
                "description": "Create exactly one new governed campaign INDEX and Task Card after explicit owner confirmation.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["owner_confirmation", "campaign_id", "task_id", "objective", "allowed_files", "verifier_commands", "authority_goal_id", "authority_coordination_scope_id"],
                    "properties": {
                        "owner_confirmation": {"type": "boolean"},
                        "campaign_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "objective": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "authority_goal_id": {"type": "string", "maxLength": 128},
                        "authority_coordination_scope_id": {"type": "string", "maxLength": 128},
                        "expected_evidence": {
                            "type": "object",
                            "description": "Optional expected evidence universe, written into the hashed card as one nexus-expected-evidence block.",
                            "additionalProperties": False,
                            "required": ["universe_generation", "subjects"],
                            "properties": {
                                "universe_generation": {"type": "integer", "minimum": 0},
                                "subjects": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": 256,
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["logical_subject_id", "evidence_kind", "requirement_mode", "applicability"],
                                        "properties": {
                                            "logical_subject_id": {"type": "string", "minLength": 1},
                                            "evidence_kind": {"type": "string", "minLength": 1},
                                            "requirement_mode": {"type": "string", "enum": [mode.value for mode in EvidenceRequirementMode]},
                                            "applicability": {"type": "string", "enum": [value.value for value in EvidenceSubjectApplicability]},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            {
                "name": "nexus_task_card_commit",
                "description": "Commit exactly one pending Task Card and INDEX on a detached clean Controller after explicit owner confirmation.",
                "inputSchema": {
                    "type": "object",
                    "required": ["owner_confirmation", "campaign_id", "task_id", "expected_head", "card_hash", "index_hash", "authority_goal_id", "authority_coordination_scope_id"],
                    "additionalProperties": False,
                    "properties": {
                        "owner_confirmation": {"type": "boolean"},
                        "campaign_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "expected_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "index_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "authority_goal_id": {"type": "string", "maxLength": 128},
                        "authority_coordination_scope_id": {"type": "string", "maxLength": 128},
                    },
                },
            },
            {
                "name": "nexus_owner_standing_grant_issue",
                "description": (
                    "Draft one keyed standing grant and ask the Owner to confirm it through "
                    "the host (MCP elicitation); the grant is written only after the host "
                    "returns the Owner's acceptance. Fails closed when the host cannot ask. "
                    "Merge, integration, release, activation and grant-issuing actions are "
                    "not grantable yet. Never executes merge, push, route, approval, release, "
                    "or production effects."
                ),
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "repository",
                        "coordinatorId",
                        "goalId",
                        "coordinationScopeId",
                        "allowedActions",
                        "ttlMinutes",
                        "issuedAt",
                    ],
                    "properties": {
                        "repository": {
                            "type": "string",
                            "const": "James3014/Nexus-new",
                        },
                        "coordinatorId": {"type": "string", "maxLength": 128},
                        "goalId": {"type": "string", "maxLength": 128},
                        "coordinationScopeId": {"type": "string", "maxLength": 128},
                        "allowedActions": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [action.value for action in AutonomyActionClass],
                            },
                            "minItems": 1,
                            "maxItems": 8,
                            "uniqueItems": True,
                        },
                        "ttlMinutes": {"type": "integer", "minimum": 1, "maximum": 60},
                        "issuedAt": {"type": "string", "maxLength": 64},
                        "expectedCurrentReceiptHash": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{64}$",
                        },
                    },
                },
            },
            {
                "name": "nexus_task_card_authority_switch",
                "description": "Switch canonical standing grant to a bounded temporary task-card authority scope after the Owner confirms it through the host (MCP elicitation); fails closed when the host cannot ask.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "attemptKey",
                        "expectedCurrentReceiptHash",
                        "expectedCurrentGoalId",
                        "expectedCurrentThreadId",
                        "successorGoalId",
                        "successorThreadId",
                        "ttlMinutes",
                    ],
                    "properties": {
                        "attemptKey": {"type": "string", "maxLength": 128},
                        "expectedCurrentReceiptHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "expectedCurrentGoalId": {"type": "string", "maxLength": 128},
                        "expectedCurrentThreadId": {"type": "string", "maxLength": 128},
                        "successorGoalId": {"type": "string", "maxLength": 128},
                        "successorThreadId": {"type": "string", "maxLength": 128},
                        "ttlMinutes": {"type": "integer", "minimum": 1, "maximum": 30},
                    },
                },
            },
            {
                "name": "nexus_task_card_authority_restore",
                "description": "Restore canonical standing grant from a temporary task-card authority scope to exact predecessor.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "ownerConfirmation",
                        "attemptKey",
                        "switchOperationId",
                        "expectedTemporaryReceiptHash",
                        "expectedCurrentGoalId",
                        "expectedCurrentThreadId",
                    ],
                    "properties": {
                        "ownerConfirmation": {"type": "boolean", "const": True},
                        "attemptKey": {"type": "string", "maxLength": 128},
                        "switchOperationId": {"type": "string", "maxLength": 128},
                        "expectedTemporaryReceiptHash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "expectedCurrentGoalId": {"type": "string", "maxLength": 128},
                        "expectedCurrentThreadId": {"type": "string", "maxLength": 128},
                    },
                },
            },
            {
                "name": "nexus_model_probe",
                "description": "Run one schema-bound model probe in an isolated workspace and return a durable job.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider", "model", "prompt", "output_schema"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "prompt": {"type": "string", "maxLength": 16000},
                        "output_schema": {"type": "object"},
                        "tools_allowed": {"type": "array", "items": {"type": "string"}, "maxItems": 16, "description": "Requested policy only; provider-specific enforcement is not claimed."},
                        "workspace_mode": {"type": "string", "enum": ["isolated"], "default": "isolated"},
                        "context_arm": {"type": "string", "enum": ["bare", "nexus_bounded", "nexus_full"], "description": "Recorded for future calibration only; not applied to the probe prompt in this version."},
                    },
                },
            },
            {
                "name": "nexus_model_probe_result",
                "description": "Retrieve one durable schema-bound model probe result and filesystem/process receipt.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}},
            },
            {
                "name": "nexus_model_calibration_evidence",
                "description": "Read-only model capability lineage evidence; calibration only, NOT Workforce Admission.",
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "lineage_id": {"type": "string"},
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                    },
                },
            },
            {
                "name": "nexus_model_calibration_plan",
                "description": "Read-only minimum-requalification plan for one model lineage; reuses still-valid lower-tier evidence instead of restarting from L1. Does not grant admission, select a route, or call a provider.",
                "inputSchema": {
                    "type": "object",
                    "required": ["provider", "model", "target_role"],
                    "additionalProperties": False,
                    "properties": {
                        "provider": {"type": "string"},
                        "model": {"type": "string"},
                        "target_role": {"type": "string"},
                        "change_kind": {"type": "string", "enum": list(CHANGE_KIND_VALUES)},
                        "description": {"type": "string", "maxLength": 512},
                    },
                },
            },
            {
                "name": "nexus_candidate_adopt_external",
                "description": "Adopt one immutable externally accepted Candidate and stop at pending human approval.",
                "inputSchema": {
                    "type": "object",
                    "required": [
                        "server_instance_id", "lifecycle_revision",
                        "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash", "controller_repo_root",
                        "controller_branch", "controller_head", "schema", "repository", "task_id",
                        "attempt_id", "action_id", "idempotency_key", "task_card_path", "task_card_hash",
                        "controller_revision", "target_base_revision", "candidate_commit_sha",
                        "candidate_tree_sha", "candidate_diff_sha256", "validation_receipt_sha256",
                        "acceptance_receipt_sha256", "validation_receipt_b64", "acceptance_receipt_b64",
                        "allowed_files", "forbidden_files", "authorized_deletions",
                        "verifier_commands", "protected_contracts", "action",
                        "authority_goal_id", "authority_coordination_scope_id",
                    ],
                    "additionalProperties": False,
                    "properties": {
                        "campaign_id": {"type": "string", "minLength": 1, "maxLength": 256},
                        "spec_id": {"type": "string", "minLength": 1, "maxLength": 256},
                        "server_instance_id": {"type": "string"}, "lifecycle_revision": {"type": "string"},
                        "spec_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "full_tool_schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "permission_policy_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "controller_repo_root": {"type": "string"}, "controller_branch": {"type": "string"},
                        "controller_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "schema": {"type": "string", "const": "nexus.external_candidate_adoption_request.v1"},
                        "repository": {"type": "string", "const": GITHUB_REPOSITORY.repository_id},
                        "task_id": {"type": "string"}, "attempt_id": {"type": "string"},
                        "action_id": {"type": "string"}, "idempotency_key": {"type": "string"},
                        "task_card_path": {"type": "string"}, "task_card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "controller_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "target_base_revision": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_diff_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "validation_receipt_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "acceptance_receipt_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "validation_receipt_b64": {"type": "string"}, "acceptance_receipt_b64": {"type": "string"},
                        "allowed_files": {"type": "array", "items": {"type": "string"}},
                        "forbidden_files": {"type": "array", "items": {"type": "string"}},
                        "authorized_deletions": {"type": "array", "items": {"type": "string"}},
                        "verifier_commands": {"type": "array", "items": {"type": "string"}},
                        "protected_contracts": {"type": "array", "items": {"type": "string"}},
                        "authority_goal_id": {"type": "string", "maxLength": 128},
                        "authority_coordination_scope_id": {"type": "string", "maxLength": 128},
                        "action": {
                            "type": "object", "additionalProperties": False,
                            "required": ["schema", "task_id", "attempt_id", "action_id", "idempotency_key", "action_type", "task_card_path", "task_card_hash", "contract_kind", "expected_head", "allowed_paths", "permission_profile", "approval_scope", "mutation_domain", "tool_manifest_hash", "request_hash", "mutation"],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.lifecycle_action.v1"},
                                "task_id": {"type": "string"}, "attempt_id": {"type": "string"}, "action_id": {"type": "string"}, "idempotency_key": {"type": "string"},
                                "action_type": {"type": "string", "const": "CANDIDATE_ADOPT_EXTERNAL"},
                                "task_card_path": {"type": "string"}, "task_card_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "contract_kind": {"type": "string", "const": "TRACKED_TASK_CARD"}, "contract_hash": {"type": ["string", "null"]},
                                "expected_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"}, "allowed_paths": {"type": "array", "items": {"type": "string"}},
                                "permission_profile": {"type": "string", "const": "CANDIDATE"}, "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE"},
                                "mutation_domain": {"type": "string", "const": "CANDIDATE_REF"}, "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "request_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "mutation": {"type": "boolean", "const": True},
                            },
                        },
                    },
                },
            },
            {
                "name": "nexus_learning_policy_adopt",
                "description": "Apply one exact, Owner-authorized governed Learning policy adoption through single-file CAS.",
                "inputSchema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["artifact", "recommendation", "validation", "expected_current_digest", "operation_id", "idempotency_key", "source_revision", "task_family", "model_name", "runtime_identity", "authority_goal_id", "authority_coordination_scope_id"],
                    "properties": {
                        "artifact": {"type": "object"}, "recommendation": {"type": "object"}, "validation": {"type": "object"},
                        "expected_current_digest": {"type": ["string", "null"]}, "operation_id": {"type": "string"}, "idempotency_key": {"type": "string"},
                        "source_revision": {"type": "string"}, "task_family": {"type": "string"}, "model_name": {"type": "string"}, "runtime_identity": {"type": "string"},
                        "authority_goal_id": {"type": "string", "maxLength": 128}, "authority_coordination_scope_id": {"type": "string", "maxLength": 128},
                    },
                },
            },
            {
                "name": "nexus_learning_policy_rollback",
                "description": "Apply one exact, Owner-authorized governed Learning policy rollback through single-file CAS.",
                "inputSchema": {
                    "type": "object", "additionalProperties": False,
                    "required": ["artifact", "previous_adoption", "expected_current_digest", "operation_id", "idempotency_key", "authority_goal_id", "authority_coordination_scope_id"],
                    "properties": {
                        "artifact": {"type": "object"}, "previous_adoption": {"type": "object"},
                        "expected_current_digest": {"type": ["string", "null"]}, "operation_id": {"type": "string"}, "idempotency_key": {"type": "string"},
                        "source_revision": {"type": "string"}, "task_family": {"type": "string"}, "model_name": {"type": "string"}, "runtime_identity": {"type": "string"},
                        "authority_goal_id": {"type": "string", "maxLength": 128}, "authority_coordination_scope_id": {"type": "string", "maxLength": 128},
                    },
                },
            },
            {
                "name": "nexus_candidate_approve",
                "description": "Approve an exact Candidate binding; approval does not integrate or push.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "approval"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "approval": {
                            "type": "object",
                            "description": "Versioned, expiring approval bound to the persisted task attempt and runtime identity.",
                            "required": [
                                "schema", "approval_id", "approved_by", "issued_at", "expires_at",
                                "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind", "contract_hash", "task_card_hash",
                                "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash",
                                "lifecycle_revision", "server_instance_id",
                            ],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.approval.v2"},
                                "approval_id": {"type": "string"},
                                "approved_by": {"type": "string"},
                                "issued_at": {"type": "string", "format": "date-time"},
                                "expires_at": {"type": "string", "format": "date-time"},
                                "bound_task_id": {"type": "string"},
                                "bound_attempt_id": {"type": "string"},
                                "bound_action_type": {"type": "string", "const": "CANDIDATE_APPROVE"},
                                "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE", "default": "ALLOW_ACTION_ONCE"},
                                "contract_kind": {"type": "string", "enum": ["TRACKED_TASK_CARD", "OWNER_INLINE"]},
                                "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "task_card_hash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"},
                                "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "full_tool_schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "permission_policy_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "lifecycle_revision": {"type": "string"},
                                "server_instance_id": {"type": "string"},
                                "consumed_at": {"type": ["string", "null"], "format": "date-time"},
                                "architecture_approval": {
                                    "type": ["object", "null"],
                                    "description": "Exact, one-shot Owner acknowledgement for the pending repository authority findings.",
                                    "required": ["schema", "approval_id", "approved_by", "issued_at", "expires_at", "approval_scope", "bound_task_id", "bound_attempt_id", "candidate_commit_sha", "candidate_tree_sha", "authority_findings_sha256"],
                                    "properties": {
                                        "schema": {"type": "string", "const": "nexus.architecture_approval.v1"},
                                        "approval_id": {"type": "string"},
                                        "approved_by": {"type": "string"},
                                        "issued_at": {"type": "string", "format": "date-time"},
                                        "expires_at": {"type": "string", "format": "date-time"},
                                        "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE"},
                                        "bound_task_id": {"type": "string"},
                                        "bound_attempt_id": {"type": "string"},
                                        "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                        "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                        "authority_findings_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                        "consumed_at": {"type": ["string", "null"], "format": "date-time"},
                                    },
                                    "additionalProperties": False,
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
                },
            },
            {
                "name": "nexus_candidate_bind_integration",
                "description": "Bind an independently accepted exact Candidate to a fresh CANDIDATE_INTEGRATE approval; prepares but does not apply integration.",
                "inputSchema": {
                    "type": "object",
                    "required": ["task_id", "expected_canonical_head", "external_acceptance", "approval"],
                    "additionalProperties": False,
                    "properties": {
                        "task_id": {"type": "string"},
                        "integration_branch": {"type": "string", "default": "nexus/integration/main"},
                        "expected_canonical_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                        "external_acceptance": {
                            "type": "object", "additionalProperties": False,
                            "required": ["schema", "task_id", "attempt_id", "candidate_commit", "receipt_hash", "reviewer_id", "passed", "verifier_artifact"],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.external_acceptance_receipt.v1"},
                                "task_id": {"type": "string"}, "attempt_id": {"type": "string"},
                                "candidate_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                "receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                                "reviewer_id": {"type": "string"}, "passed": {"type": "boolean", "const": True},
                                "verifier_artifact": {"type": "string"},
                            },
                        },
                        "approval": {
                            "type": "object", "additionalProperties": False,
                            "required": ["schema", "approval_id", "approved_by", "issued_at", "expires_at", "bound_task_id", "bound_attempt_id", "bound_action_type", "contract_kind", "contract_hash", "task_card_hash", "tool_manifest_hash", "full_tool_schema_hash", "permission_policy_hash", "lifecycle_revision", "server_instance_id", "expected_canonical_head", "integration_branch", "candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash", "acceptance_receipt_hash"],
                            "properties": {
                                "schema": {"type": "string", "const": "nexus.approval.v2"}, "approval_id": {"type": "string"}, "approved_by": {"type": "string"},
                                "issued_at": {"type": "string", "format": "date-time"}, "expires_at": {"type": "string", "format": "date-time"},
                                "bound_task_id": {"type": "string"}, "bound_attempt_id": {"type": "string"},
                                "bound_action_type": {"type": "string", "const": "CANDIDATE_INTEGRATE"},
                                "approval_scope": {"type": "string", "const": "ALLOW_ACTION_ONCE", "default": "ALLOW_ACTION_ONCE"},
                                "contract_kind": {"type": "string", "enum": ["TRACKED_TASK_CARD", "OWNER_INLINE"]}, "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "task_card_hash": {"type": ["string", "null"]},
                                "tool_manifest_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "full_tool_schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "permission_policy_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "lifecycle_revision": {"type": "string"}, "server_instance_id": {"type": "string"},
                                "expected_canonical_head": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                                "integration_branch": {"type": "string"},
                                "candidate_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}, "candidate_tree_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}, "candidate_state_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "verified_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "acceptance_receipt_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                            },
                        },
                    },
                },
            },
            {
                "name": "nexus_candidate_integrate",
                "description": "Integrate an already approved exact Candidate binding without pushing.",
                "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}, "integration_branch": {"type": "string", "default": "nexus/integration/main"}}},
            },
            {
                "name": "nexus_candidate_dispose",
                "description": "Dispose a pending Candidate as REJECTED or SUPERSEDED through cleanup authority.",
                "inputSchema": {"type": "object", "additionalProperties": False, "required": ["task_id", "disposition", "authority_goal_id", "authority_coordination_scope_id"], "properties": {"task_id": {"type": "string"}, "disposition": {"type": "string", "enum": ["REJECTED", "SUPERSEDED"]}, "superseded_by": {"type": "string"}, "authority_goal_id": {"type": "string", "maxLength": 128}, "authority_coordination_scope_id": {"type": "string", "maxLength": 128}}},
            },
        ]

    @staticmethod
    def _success(request_id: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "structuredContent": dict(payload), "isError": False}}

    @staticmethod
    def _task_not_found(
        task_id: str,
        *,
        operation: str,
        timeout_seconds: Optional[float] = None,
        poll_interval_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": "nexus.self_hosted_task_status.v1",
            "task_id": task_id,
            "status": "NOT_FOUND",
            "found": False,
            "state_valid": False,
            "retry_authorized": False,
            "blocker": {"code": "TASK_NOT_FOUND", "detail": "no lifecycle state exists for task_id"},
            "task_action": {
                "schema": "nexus.self_hosted_task_action.v1",
                "task_id": task_id,
                "task_status": "NOT_FOUND",
                "action_state": "NOT_FOUND",
                "attention_required": False,
                "next_action": "none",
                "recommended_tool": None,
            },
            "operation": operation,
        }
        if operation == "wait":
            payload["wait"] = {
                "timed_out": False,
                "not_found": True,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            }
        return payload

    @staticmethod
    def _error(request_id: Any, error: Exception | str) -> dict[str, Any]:
        payload = error.as_dict() if isinstance(error, LifecycleGuardError) else {"schema": "nexus.mcp_gateway_error.v1", "error": str(error)}
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "structuredContent": payload, "isError": True}}

    def _gateway_status(self) -> dict[str, Any]:
        lifecycle = self.service.lifecycle_status()
        current_head = _loaded_git("rev-parse", "HEAD").strip()
        formal_actionable = self.service.list_actionable_tasks()
        pending_actions = int(formal_actionable.get("actionable_count", 0) or 0)
        for job_path in self._assist_root().glob("*.json"):
            try:
                job = json.loads(job_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(job, Mapping):
                action = self._assist_action(job)
                if action["pending"] or action["attention_required"]:
                    pending_actions += 1
        action_sha_current, action_contract_ok, action_contract_reasons = _action_contract_fingerprint()
        permission_sha_current, permission_contract_ok, permission_contract_reasons = _permission_enforcement_fingerprint()
        upstream_info = self._observe_upstream_freshness(deployed_head=current_head)
        freshness = _evaluate_freshness(
            repo_head_at_start=SERVER_REPO_HEAD_AT_START,
            repo_head_current=current_head,
            runtime_sha_at_start=RUNTIME_SOURCE_SHA256_AT_START,
            runtime_sha_current=_hash_source_paths(RUNTIME_SOURCE_PATHS),
            action_sha_at_start=ACTION_CONTRACT_SHA256_AT_START,
            action_sha_current=action_sha_current,
            permission_sha_at_start=PERMISSION_ENFORCEMENT_SHA256_AT_START,
            permission_sha_current=permission_sha_current,
            action_contract_ok=action_contract_ok,
            action_contract_reasons=action_contract_reasons,
            permission_contract_ok=permission_contract_ok,
            permission_contract_reasons=permission_contract_reasons,
        )
        return {
            "schema": "nexus.mcp_gateway_status.v1",
            "public_app_name": PUBLIC_APP_NAME,
            "namespace_policy": "stable_public_name_with_manifest_revision",
            "server": GATEWAY_NAME,
            "version": GATEWAY_VERSION,
            "tool_manifest_revision": TOOL_MANIFEST_REVISION,
            "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
            "permission_policy_hash": PERMISSION_POLICY_HASH,
            "permission_policy_revision": PERMISSION_POLICY_REVISION,
            "task_contract_revision": TASK_CONTRACT_REVISION,
            "lifecycle_revision": LIFECYCLE_REVISION,
            "lifecycle_state_schema_revision": LIFECYCLE_STATE_SCHEMA_REVISION,
            "server_instance_id": SERVER_INSTANCE_ID,
            "server_started_at": SERVER_STARTED_AT,
            "repo_head_at_start": SERVER_REPO_HEAD_AT_START,
            "repo_head_current": current_head,
            "freshness_semantics_revision": FRESHNESS_SEMANTICS_REVISION,
            **freshness,
            **upstream_info,
            "session_tracking": "unsupported",
            "active_sessions": None,
            "pending_actions": pending_actions,
            "tool_count": len(PUBLIC_TOOL_NAMES),
            "route_authority": "CapabilityPlanner",
            "execution_lanes": ["DIRECT_CANONICAL", "ASSISTED_CANONICAL", "ISOLATED_TARGET"],
            "canonical_repo_root": str(CANONICAL_SOURCE_ROOT),
            "controller_binding": controller_binding_status(),
            "github_observer": github_observer_runtime_identity(),
            "core_provenance": gateway_core_provenance(),
            "lifecycle": lifecycle,
        }

    @staticmethod
    def _gateway_recovery_materialize(
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        manager = _gateway_recovery_manager()
        return _gateway_recovery_result(
            manager.gateway_recovery_materialize(dict(arguments))
        )

    @staticmethod
    def _gateway_recovery_preflight(
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        manager = _gateway_recovery_manager()
        return _gateway_recovery_result(manager.gateway_recover(dict(arguments)))

    @staticmethod
    def _gateway_recover_exact(
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        manager = _gateway_recovery_manager()
        return _gateway_recovery_result(manager._gateway_recover_live(dict(arguments)))

    def _gateway_convergence(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Classify one #1064 convergence generation without performing effects."""

        policy = arguments.get("policy")
        if not isinstance(policy, Mapping):
            raise GatewayInputError("policy must be an object")
        readiness_state = _text(
            arguments.get("readiness_state"),
            "readiness_state",
            max_length=32,
        ).upper()
        quiescence_state = _text(
            arguments.get("quiescence_state"),
            "quiescence_state",
            max_length=32,
        ).upper()
        if readiness_state not in {"SAFE", "BLOCKED", "UNKNOWN"}:
            raise GatewayInputError("readiness_state must be SAFE, BLOCKED, or UNKNOWN")
        if quiescence_state not in {"SAFE", "BLOCKED", "UNKNOWN"}:
            raise GatewayInputError("quiescence_state must be SAFE, BLOCKED, or UNKNOWN")

        status = self._gateway_status()
        try:
            loaded_tree = _loaded_git("rev-parse", "HEAD^{tree}").strip()
        except RuntimeError as exc:
            raise GatewayInputError("loaded Gateway tree is unavailable") from exc

        request_payload: dict[str, Any] = {
            "policy": dict(policy),
            "observation": {
                "loaded_commit": status.get("repo_head_current"),
                "loaded_tree": loaded_tree,
                "upstream_freshness": status.get("upstream_freshness"),
                "observed_upstream_main_head": status.get("observed_upstream_main_head"),
                "readiness_state": readiness_state,
                "quiescence_state": quiescence_state,
                "server_instance_id": status.get("server_instance_id"),
            },
            "active_effect": arguments.get("active_effect"),
            "not_before": arguments.get("not_before"),
        }
        try:
            request = GatewayConvergenceRequest.model_validate(request_payload)
            result = evaluate_gateway_convergence(request)
        except ValueError as exc:
            raise GatewayInputError(str(exc)) from exc

        if (
            result.action is ConvergenceAction.REQUEST_RECOVERY
            and request.policy.mode is DesiredDeploymentMode.TRACK_ACCEPTED_MAIN
            and (
                request.active_effect is None
                or request.active_effect.state is RecoveryEffectState.TERMINAL_SUCCESS
            )
            and status.get("upstream_freshness") == "STALE"
            and _receipt_only_main_movement(
                deployed_source_head=result.observed_loaded_commit,
                observed_upstream_main_head=status.get("observed_upstream_main_head"),
            )
        ):
            # Keep exact Git freshness telemetry as STALE.  The NOOP applies
            # only to the recovery decision because the sole upstream delta is
            # the tracked recovery authority receipt itself.
            result = result.model_copy(
                update={
                    "action": ConvergenceAction.NOOP,
                    "reason": ConvergenceReason.ALREADY_CONVERGED,
                    "next_generation_required": False,
                }
            )

        next_action = {
            ConvergenceAction.NOOP: "none",
            ConvergenceAction.BLOCKED: "reobserve_or_rebind",
            ConvergenceAction.REQUEST_RECOVERY: "prepare_issue_526_recovery",
            ConvergenceAction.START_PREPARED_RECOVERY: "issue_526_gateway_recover",
            ConvergenceAction.COALESCE_PRE_EFFECT_TARGET: "prepare_latest_issue_526_recovery",
            ConvergenceAction.RECONCILE_RECOVERY: "operation_reconcile",
        }[result.action]
        payload = result.model_dump(mode="json")
        payload.update(
            {
                "canonical_next_action": next_action,
                "decision_only": True,
                "host_effect_performed": False,
                "observed_gateway_instance_id": status.get("server_instance_id"),
                "observed_upstream_freshness": status.get("upstream_freshness"),
            }
        )
        return payload

    def _gateway_execution_readiness(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Evaluate the #807 pre-execution readiness convergence gate.

        One typed request in, one typed result out (READY_TO_EXECUTE or
        BLOCKED with exactly one primary blocker).  This tool observes and
        reports only: it never repairs, reloads, routes, admits, grants,
        approves, or certifies.
        """

        required_fields = (
            "repository_owner",
            "repository_name",
            "intended_source_commit",
            "intended_source_tree",
            "execution_realm",
            "required_action_family",
            "execution_contract_kind",
        )
        fields: dict[str, str] = {}
        for field in required_fields:
            raw = arguments.get(field)
            if raw is None:
                raise GatewayInputError(f"{field} is required")
            fields[field] = _text(raw, field, max_length=4096)
        optional_fields = (
            "task_campaign_goal_identity",
            "durable_coordination_scope_id",
            "durable_repository_canonical_remote",
            "desired_deployment_identity",
        )
        optionals: dict[str, str] = {}
        for field in optional_fields:
            raw = arguments.get(field)
            if raw is not None:
                optionals[field] = _text(raw, field, max_length=4096)
        worker_constraints = arguments.get("worker_constraints") or []
        if not isinstance(worker_constraints, (list, tuple)):
            raise GatewayInputError("worker_constraints must be an array of strings")
        worker_constraint_values = tuple(
            _text(item, "worker_constraints[]", max_length=256) for item in worker_constraints
        )
        completion_contract = arguments.get("required_completion_contract")
        if completion_contract is not None and not isinstance(completion_contract, Mapping):
            raise GatewayInputError("required_completion_contract must be an object")

        try:
            request = ExecutionReadinessRequest(
                repository_owner=fields["repository_owner"],
                repository_name=fields["repository_name"],
                intended_source_commit=fields["intended_source_commit"],
                intended_source_tree=fields["intended_source_tree"],
                execution_realm=fields["execution_realm"],
                required_action_family=fields["required_action_family"],
                execution_contract_kind=fields["execution_contract_kind"],
                task_campaign_goal_identity=optionals.get("task_campaign_goal_identity"),
                durable_coordination_scope_id=optionals.get("durable_coordination_scope_id"),
                durable_repository_canonical_remote=optionals.get(
                    "durable_repository_canonical_remote"
                ),
                desired_deployment_identity=optionals.get("desired_deployment_identity"),
                worker_constraints=worker_constraint_values,
                workforce_dispatch_binding=arguments.get("workforce_dispatch_binding"),
                required_completion_contract=completion_contract,
            )
        except ValueError as exc:
            raise GatewayInputError(str(exc)) from exc

        realm = fields["execution_realm"]
        if realm == "in_process_preflight":
            observed_runtime_sha256 = _hash_source_paths(RUNTIME_SOURCE_PATHS)
            try:
                observed_repo_head = _git("rev-parse", "HEAD").strip()
                observed_repo_tree = _git("rev-parse", "HEAD^{tree}").strip()
            except RuntimeError:
                observed_repo_head = ""
                observed_repo_tree = ""
            gateway_observation = GatewayReadinessObservation(
                gateway_instance_id=SERVER_INSTANCE_ID,
                observed_repo_head=observed_repo_head,
                observed_repo_tree=observed_repo_tree,
                observed_runtime_sha256=observed_runtime_sha256,
                runtime_sha256_at_start=RUNTIME_SOURCE_SHA256_AT_START,
                tool_manifest_revision=TOOL_MANIFEST_REVISION,
                full_tool_schema_hash=FULL_TOOL_SCHEMA_HASH,
                permission_policy_hash=PERMISSION_POLICY_HASH,
                reload_required=observed_runtime_sha256 != RUNTIME_SOURCE_SHA256_AT_START,
            )
            completion_observation = _completion_authority_observation_from_environment()
            plane_observations = _in_process_readiness_plane_observations(
                gateway_observation,
                request=request,
                completion_observation=completion_observation,
                required_completion_contract=request.required_completion_contract,
            )
        else:
            raise GatewayInputError(f"execution_realm {realm!r} is not a supported observation realm")

        result = evaluate_execution_readiness(
            request,
            plane_observations,
            completion_observation=completion_observation,
            provider_preflight_observer=lambda provider, model: self._provider_preflight(
                {"provider": provider, "model": model}
            ),
            provider_authentication_required_observer=self._provider_requires_authentication,
        )
        payload = result.model_dump(mode="json")
        payload["certification_fence"] = {
            "ready_vocabulary": ["READY_TO_EXECUTE"],
            "forbidden_vocabulary_ref": "NEXUS_EXECUTION_READINESS_FORBIDDEN_CERTIFICATION_VOCABULARY",
            "satisfied": result.request_satisfies_certification_fence(),
        }
        return payload

    @staticmethod
    def _recovery_payload(state: Mapping[str, Any], *, operation: str = "status", include_state: bool = False) -> dict[str, Any]:
        """Normalize every recovery response to one actionable contract."""
        action = state.get("task_action") if isinstance(state.get("task_action"), Mapping) else {}
        action = dict(action)
        task_id = str(state.get("task_id") or action.get("task_id") or "")
        status = str(state.get("status") or action.get("task_status") or "UNKNOWN")
        terminal = status in {"CANCELLED", "INTEGRATED", "REJECTED", "SUPERSEDED", "FINAL_BLOCK"} and not bool(state.get("reconciliation_required"))
        next_action = str(action.get("next_action") or ("none" if terminal else "nexus_task_reconcile"))
        candidate = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        if not candidate and isinstance(action.get("candidate"), Mapping):
            candidate = action.get("candidate") or {}
        cleanup = state.get("cleanup_status") if isinstance(state.get("cleanup_status"), Mapping) else {}
        cleanup = dict(cleanup)
        if not cleanup:
            cleanup = {
                "state_retention_status": state.get("state_retention_status"),
                "cleanup_eligible": state.get("cleanup_eligible"),
                "cleanup_performed": state.get("cleanup_performed"),
                "cleanup_decision": state.get("cleanup_decision"),
                "cleanup_blocker": state.get("cleanup_blocker"),
            }
        action_id = state.get("action_id")
        if not action_id and isinstance(state.get("action"), Mapping):
            action_id = state["action"].get("action_id")
        if not action_id and isinstance(state.get("request"), Mapping) and isinstance(state["request"].get("action"), Mapping):
            action_id = state["request"]["action"].get("action_id")
        recommended = action.get("recommended_tool") or next_action
        if recommended not in PUBLIC_TOOL_NAMES:
            if status in {"DIRECT_RECONCILE_REQUIRED", "UNKNOWN_REQUIRES_RECONCILE"} or state.get("reconciliation_required"):
                recommended = "nexus_task_reconcile"
            elif status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW", "INTEGRATION_FAILED"}:
                recommended = "nexus_task_status"
            else:
                recommended = "nexus_task_wait"
        result: dict[str, Any] = {
            "schema": "nexus.lifecycle_recovery.v1",
            "operation": operation,
            "task_id": task_id,
            "attempt_id": state.get("attempt_id") or action.get("attempt_id"),
            "last_action_id": action_id,
            "status": status,
            "attention_required": bool(action.get("attention_required", not terminal)),
            "next_action": next_action,
            "recommended_tool": recommended,
            "candidate_binding": {
                "candidate_commit_sha": state.get("candidate_commit_sha") or candidate.get("candidate_commit_sha"),
                "candidate_tree_sha": state.get("candidate_tree_sha") or candidate.get("candidate_tree_sha"),
                "candidate_state_hash": state.get("candidate_state_hash") or candidate.get("candidate_state_hash"),
                "verified_receipt_hash": state.get("verified_receipt_hash") or candidate.get("verified_receipt_hash"),
                "candidate_ref": state.get("candidate_ref"),
            },
            "cleanup_status": cleanup,
            "uncertain_mutation": status in {"DIRECT_RECONCILE_REQUIRED", "UNKNOWN_REQUIRES_RECONCILE"} or bool(state.get("reconciliation_required")),
        }
        if include_state:
            result["state"] = dict(state)
        return result

    def _task_list_actionable(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        include_details = bool(arguments.get("include_details", False))
        raw = self.service.list_actionable_tasks(include_details=include_details)
        tasks = [self._recovery_payload(item, operation="list", include_state=include_details) for item in raw.get("tasks", []) if isinstance(item, Mapping)]
        for path in sorted(self._assist_root().glob("*.json")):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(job, Mapping):
                continue
            response = self._assist_response(self._assist_refresh(str(job.get("task_id"))) or job, operation="list")
            if response.get("attention_required") is True:
                tasks.append(response)
        return {
            "schema": "nexus.task_actionable_list.v1",
            "actionable_count": len(tasks),
            "details_included": include_details,
            "tasks": tasks,
        }

    def _task_reconcile(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            current = self._assist_refresh(task_id) or assisted
            needs_reconcile = (
                current.get("status") == "UNKNOWN_REQUIRES_RECONCILE"
                or bool(current.get("reconciliation_required"))
            )
            if needs_reconcile:
                lease_hash = str(current.get("account_lease_id_hash") or "")
                if lease_hash and current.get("account_lease_cleanup_status") != "RELEASED":
                    coordinator = CrossProcessLeaseCoordinator(get_account_pool_manager())
                    lease_result = coordinator.reconcile_claim_receipt(
                        account_alias_hash=str(current.get("account_alias_hash") or ""),
                        lease_id_hash=lease_hash,
                        owner_pid=int(current.get("account_lease_owner_pid") or 0),
                    )
                    current["account_lease_reconciliation_result"] = lease_result.get("result")
                    if lease_result.get("result") not in {"ALREADY_ABSENT", "LEASE_RECEIPT_REMOVED"}:
                        current.update({
                            "status": "UNKNOWN_REQUIRES_RECONCILE",
                            "blocker": "ASSIST_ACCOUNT_LEASE_RECONCILIATION_REQUIRED",
                            "reconciliation_required": True,
                            "account_lease_released": False,
                            "account_lease_cleanup_status": "RECONCILIATION_REQUIRED",
                            "last_polled_at": self._utc_now(),
                        })
                        current = self._assist_write(current)
                        return self._assist_response(current, operation="reconcile")
                    current["account_lease_released"] = True
                    current["account_lease_cleanup_status"] = "RELEASED"

                # No durable exit marker means the provider outcome is not
                # recoverable from output alone.  Only after lease cleanup is
                # proven may reconciliation converge to a retryable failure;
                # output alone never upgrades the result to success.
                current.update({
                    "status": "FAILED",
                    "blocker": "ASSIST_PROVIDER_PROCESS_LOST",
                    "reconciliation_required": False,
                    "reconciled_from": "UNKNOWN_REQUIRES_RECONCILE",
                    "reconciled_at": self._utc_now(),
                    "finished_at": current.get("finished_at") or self._utc_now(),
                })
                self._cleanup_assist_workspace(current)
                current = self._assist_write(current)
            return self._assist_response(current, operation="reconcile")
        result = self.service.reconcile_task(task_id)
        if result is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return self._recovery_payload(result, operation="reconcile", include_state=True)

    def _task_retry(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _require_bound_controller()
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            return self._assist_retry(task_id)
        return self._recovery_payload(self.service.retry_task(task_id), operation="retry", include_state=True)

    def _task_resume(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _require_bound_controller()
        task_id = _text(arguments.get("task_id"), "task_id")
        assisted = self._assist_read(task_id)
        if assisted is not None:
            return self._assist_wait(task_id, timeout_seconds=0.0)
        result = self.service.resume_task(task_id)
        if result is None:
            raise KeyError(f"unknown task_id: {task_id}")
        return self._recovery_payload(result, operation="resume", include_state=True)

    @staticmethod
    def _exact_hash(value: Any, field: str, length: int) -> str:
        text = _text(value, field)
        pattern = rf"^[0-9a-f]{{{length}}}$"
        if not re.fullmatch(pattern, text):
            raise GatewayInputError(f"{field} must be an exact lowercase Git hash")
        return text

    def _learning_policy_control(
        self,
        arguments: Mapping[str, Any],
        *,
        action: AutonomyActionClass,
    ) -> dict[str, Any]:
        """Validate one closed Learning effect, authorize it, then CAS it."""
        _require_bound_controller()
        common = {
            "artifact", "expected_current_digest", "operation_id", "idempotency_key",
            "source_revision", "task_family", "model_name", "runtime_identity",
            "authority_goal_id", "authority_coordination_scope_id",
        }
        allowed = common | ({"recommendation", "validation"} if action is AutonomyActionClass.LEARNING_POLICY_ADOPT else {"previous_adoption"})
        unknown = set(arguments) - allowed
        if unknown:
            raise GatewayInputError("LEARNING_POLICY_CONTROL_SCHEMA_CLOSED")
        missing = common - set(arguments)
        if missing:
            raise GatewayInputError("LEARNING_POLICY_CONTROL_FIELDS_REQUIRED:" + ",".join(sorted(missing)))
        if action is AutonomyActionClass.LEARNING_POLICY_ADOPT and not {"recommendation", "validation"} <= set(arguments):
            raise GatewayInputError("LEARNING_POLICY_PROVENANCE_REQUIRED")
        if action is AutonomyActionClass.LEARNING_POLICY_ROLLBACK and "previous_adoption" not in arguments:
            raise GatewayInputError("LEARNING_POLICY_ROLLBACK_ADOPTION_BINDING_REQUIRED")
        # Freeze every nested request object before hashing or authority lookup.
        arguments = copy.deepcopy(dict(arguments))
        artifact = arguments.get("artifact")
        if not isinstance(artifact, Mapping):
            raise GatewayInputError("LEARNING_POLICY_ARTIFACT_INVALID")
        previous = arguments.get("previous_adoption")
        if previous is not None and not isinstance(previous, Mapping):
            raise GatewayInputError("LEARNING_POLICY_ROLLBACK_ADOPTION_INVALID")
        artifact_hash = hashlib.sha256(json.dumps(dict(artifact), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        def input_hash(value: Any) -> str | None:
            if not isinstance(value, Mapping):
                return None
            return hashlib.sha256(json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        effect = {
            "repository": GITHUB_REPOSITORY.repository_id,
            "action": action.value,
            "operation_id": str(arguments["operation_id"]),
            "idempotency_key": str(arguments["idempotency_key"]),
            "artifact_hash": artifact_hash,
            "target_path": str(CANONICAL_SOURCE_ROOT / (DEFAULT_GOVERNED_ADOPTION_PATH if action is AutonomyActionClass.LEARNING_POLICY_ADOPT else DEFAULT_GOVERNED_ROLLBACK_PATH)),
            "expected_current_digest": arguments.get("expected_current_digest"),
            "source_revision": str(arguments["source_revision"]),
            "task_family": str(arguments["task_family"]),
            "model_name": str(arguments["model_name"]),
            "runtime_identity": str(arguments["runtime_identity"]),
            "recommendation_input_hash": input_hash(arguments.get("recommendation")),
            "validation_input_hash": input_hash(arguments.get("validation")),
            "previous_adoption_input_hash": input_hash(previous),
        }
        owner_authority = self._require_owner_effect_authority(
            action, effect, key=self._owner_effect_key(arguments)
        )
        try:
            result = apply_learning_policy_effect(
                action=action,
                project_root=CANONICAL_SOURCE_ROOT,
                artifact=artifact,
                recommendation=arguments.get("recommendation"),
                validation=arguments.get("validation"),
                expected_current_digest=arguments.get("expected_current_digest"),
                operation_id=str(arguments["operation_id"]),
                idempotency_key=str(arguments["idempotency_key"]),
                source_revision=str(arguments["source_revision"]),
                task_family=str(arguments["task_family"]),
                model_name=str(arguments["model_name"]),
                runtime_identity=str(arguments["runtime_identity"]),
                previous_adoption_id=(str(previous.get("adoption_id")) if isinstance(previous, Mapping) else None),
                previous_adoption_hash=(str(previous.get("adoption_hash")) if isinstance(previous, Mapping) else None),
                previous_adoption=previous,
            )
        except Exception as exc:
            raise GatewayInputError(str(exc)) from exc
        return {**result, "owner_authority": owner_authority}

    def _candidate_integrate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _require_bound_controller()
        task_id = _text(arguments.get("task_id"), "task_id")
        branch = str(arguments.get("integration_branch") or "nexus/integration/main").strip()
        if not branch or branch.startswith("-") or any(char in branch for char in "\n\r"):
            raise GatewayInputError("integration_branch is invalid")
        state = self.service.get_task_snapshot(task_id, include_details=True)
        if not isinstance(state, Mapping):
            raise GatewayInputError("CANDIDATE_TASK_STATE_REQUIRED")
        base = str(state.get("controller_revision") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise GatewayInputError("CANDIDATE_CONTROLLER_REVISION_REQUIRED")
        contract = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        allowed_files = [str(path) for path in contract.get("allowed_files") or [] if str(path).strip()]
        if not allowed_files:
            raise GatewayInputError("CANDIDATE_ALLOWED_PATHS_REQUIRED")
        packet = state.get("promotion_packet") if isinstance(state.get("promotion_packet"), Mapping) else {}
        try:
            identity = resolve_contract_identity(state, expected_task_id=task_id, expected_head=base)
        except RuntimeError as exc:
            raise LifecycleGuardError("CONTRACT_HASH_MISMATCH", str(exc)) from exc
        contract_kind = identity["contract_kind"]
        contract_hash = identity["contract_hash"]
        task_card_hash = identity["task_card_hash"]
        owner_inline_contract = identity["owner_inline_contract"]
        binding = state.get("approved_binding") if isinstance(state.get("approved_binding"), Mapping) else {}
        approval_grant = (state.get("integration_approval_grant") if isinstance(state.get("integration_approval_grant"), Mapping) else None) or (binding.get("approval_grant") if isinstance(binding.get("approval_grant"), Mapping) else None)
        persisted_authorization = state.get("integration_authorization") if isinstance(state.get("integration_authorization"), Mapping) else {}
        expected_integration_head = str(persisted_authorization.get("expected_canonical_head") or base)
        live_head = base
        if isinstance(state.get("integration_approval_grant"), Mapping):
            controller_root = Path(str(contract.get("controller_repo_root") or CANONICAL_SOURCE_ROOT)).expanduser().resolve()
            live_head_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=controller_root, capture_output=True, text=True, check=False)
            live_head = live_head_result.stdout.strip()
            if live_head_result.returncode != 0 or live_head != expected_integration_head:
                raise GatewayInputError("CANDIDATE_INTEGRATE_HEAD_DRIFT")
        if contract_kind == ContractKind.TRACKED_TASK_CARD.value and not re.fullmatch(r"[0-9a-f]{64}", task_card_hash):
            raise LifecycleGuardError("CANDIDATE_TASK_CARD_HASH_REQUIRED", "tracked candidate integration requires a task card hash")
        if contract_kind == ContractKind.OWNER_INLINE.value and not contract_hash:
            raise LifecycleGuardError("CANDIDATE_OWNER_INLINE_CONTRACT_REQUIRED", "Owner Inline integration requires a contract hash")
        if not approval_grant:
            raise LifecycleGuardError("APPROVAL_REVALIDATION_REQUIRED", "integration requires a persisted versioned approval binding")
        approval_receipt = validate_approval_grant(
            approval_grant,
            task_id=task_id,
            attempt_id=str(state.get("attempt_id") or ""),
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE.value if isinstance(state.get("integration_approval_grant"), Mapping) else LifecycleActionType.CANDIDATE_APPROVE.value,
            task_card_hash=task_card_hash,
            contract_kind=contract_kind,
            contract_hash=contract_hash,
            owner_inline_contract=owner_inline_contract,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            full_tool_schema_hash=FULL_TOOL_SCHEMA_HASH,
            permission_policy_hash=PERMISSION_POLICY_HASH,
            lifecycle_revision=LIFECYCLE_REVISION,
            server_instance_id=SERVER_INSTANCE_ID,
            allow_consumed=True,
        )
        action_request = {**dict(arguments), "allowed_files": allowed_files, "source_attempt_id": state.get("attempt_id"), "candidate_binding": {
            "candidate_commit_sha": packet.get("candidate_commit_sha") or state.get("candidate_commit_sha"),
            "candidate_tree_sha": packet.get("candidate_tree_sha") or state.get("candidate_tree_sha"),
            "candidate_state_hash": packet.get("candidate_state_hash") or state.get("candidate_state_hash"),
            "verified_receipt_hash": packet.get("verified_receipt_hash") or state.get("verified_receipt_hash"),
        }}
        action = build_action_envelope(
            task_id=task_id,
            action_type=LifecycleActionType.CANDIDATE_INTEGRATE,
            request=action_request,
            tool_manifest_hash=TOOL_MANIFEST_REVISION,
            expected_head=live_head,
            allowed_paths=allowed_files,
            mutation=True,
            permission_profile=PermissionProfile.INTEGRATE,
            mutation_domain=MutationDomain.INTEGRATION,
        )
        guard_receipt = pre_action_guard(action, request={"allowed_files": allowed_files}, current_head=live_head, tool_manifest_hash=TOOL_MANIFEST_REVISION)
        result = self.service.integrate_approved(
            task_id,
            integration_branch=branch,
            runtime_identity={
                **identity,
                "tool_manifest_hash": TOOL_MANIFEST_REVISION,
                "full_tool_schema_hash": FULL_TOOL_SCHEMA_HASH,
                "permission_policy_hash": PERMISSION_POLICY_HASH,
                "lifecycle_revision": LIFECYCLE_REVISION,
                "server_instance_id": SERVER_INSTANCE_ID,
            },
        )
        payload = self._recovery_payload(result, operation="candidate_integrate", include_state=True)
        payload["guard_receipt"] = guard_receipt
        payload["approval_revalidation"] = approval_receipt
        return payload

    def _workspace_snapshot(self) -> dict[str, Any]:
        status = _git("status", "--porcelain=v1")
        branch = _git("branch", "--show-current").strip()
        head = _git("rev-parse", "HEAD").strip()
        worktree_lines = _git("worktree", "list", "--porcelain").splitlines()
        worktrees = [line.removeprefix("worktree ") for line in worktree_lines if line.startswith("worktree ")]
        actionable = self.service.list_actionable_tasks()
        return {
            "schema": "nexus.workspace_snapshot.v1",
            "root": str(CANONICAL_SOURCE_ROOT),
            "branch": branch,
            "head": head,
            "clean": not bool(status.strip()),
            "registered_worktrees": worktrees,
            "registered_worktree_count": len(worktrees),
            "actionable_count": int(actionable.get("actionable_count", 0)),
            "target_root": str(CANONICAL_SOURCE_ROOT.parent / "nexus-runtime-targets"),
        }

    def _read(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        path = _safe_relative_path(arguments.get("path"))
        if not path.is_file():
            raise GatewayInputError("path is not a regular file")
        if path.stat().st_size > MAX_READ_BYTES:
            raise GatewayInputError(f"path exceeds {MAX_READ_BYTES} bytes")
        start = max(1, int(arguments.get("start_line", 1)))
        limit = min(1000, max(1, int(arguments.get("max_lines", 200))))
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = lines[start - 1 : start - 1 + limit]
        return {"schema": "nexus.workspace_read.v1", "path": str(path.relative_to(CANONICAL_SOURCE_ROOT)), "start_line": start, "lines": selected, "truncated": start - 1 + limit < len(lines)}

    def _search(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pattern = _text(arguments.get("pattern"), "pattern", max_length=200)
        _, path = _safe_search_target(arguments.get("path", "."))
        relative = str(path.relative_to(CANONICAL_SOURCE_ROOT)) or "."
        rg = shutil.which("rg")
        if rg is None:
            matches, truncated = _python_literal_search(root=CANONICAL_SOURCE_ROOT, target=path, pattern=pattern)
            backend = "python"
        else:
            try:
                matches, truncated = _run_rg_literal_search(
                    executable=rg, root=CANONICAL_SOURCE_ROOT, relative=relative, pattern=pattern
                )
            except FileNotFoundError:
                matches, truncated = _python_literal_search(root=CANONICAL_SOURCE_ROOT, target=path, pattern=pattern)
                backend = "python"
            else:
                backend = "ripgrep"
        return {"schema": "nexus.workspace_search.v1", "pattern": pattern, "path": relative, "matches": matches, "truncated": truncated, "backend": backend}

    def _diff(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        base = arguments.get("base_revision")
        if base is not None and not _SHA_RE.fullmatch(str(base)):
            raise GatewayInputError("base_revision must be an exact lowercase Git SHA")
        args = ["diff", "--no-ext-diff", "--unified=3"]
        if bool(arguments.get("staged", False)):
            args.append("--cached")
        if base:
            args.append(str(base))
        output = _bounded_text(_git(*args), "git diff")
        return {"schema": "nexus.workspace_diff.v1", "base_revision": base, "staged": bool(arguments.get("staged", False)), "diff": output}

    @staticmethod
    def _task_id(arguments: Mapping[str, Any], what: str, why: str, allowed: list[str]) -> str:
        explicit = str(arguments.get("task_id") or "").strip()
        if explicit:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", explicit):
                raise GatewayInputError("task_id must be a stable bounded slug")
            return explicit
        seed = json.dumps([what, why, sorted(allowed)], ensure_ascii=False, separators=(",", ":"))
        return "dispatch-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def _task_run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _require_bound_controller()
        try:
            reject_caller_route_overrides(arguments)
        except ValueError as exc:
            raise GatewayInputError(str(exc)) from exc
        what = _text(arguments.get("what"), "what")
        why = _text(arguments.get("why"), "why")
        allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
        if not allowed or len(allowed) > 4:
            raise GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            _safe_relative_path(path, "allowed_files")
        verifiers = [str(command).strip() for command in (arguments.get("verifier_commands") or []) if str(command).strip()]
        task_id = self._task_id(arguments, what, why, allowed)
        if len(verifiers) > 1:
            raise GatewayInputError("verifier_commands supports exactly one isolated command")
        revision = _git("rev-parse", "HEAD").strip()
        try:
            execution_context = build_mcp_execution_context(
                task_id=task_id,
                workspace_revision=revision,
                allowed_files=allowed,
                verifier_commands=verifiers,
            )
            result = execute_canonical_product_task(
                f"{what}\n\nAcceptance context: {why}",
                CANONICAL_SOURCE_ROOT,
                execution_context=execution_context,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise GatewayInputError(f"canonical_product_runtime_failed_closed:{exc}") from exc
        receipt = dict(result.receipt)
        canonical_execution = (
            dict(receipt.get("canonical_execution"))
            if isinstance(receipt.get("canonical_execution"), Mapping)
            else {}
        )
        return {
            "schema": "nexus.mcp_canonical_runtime.v1",
            "status": "SUCCEEDED" if bool(result) else "BLOCKED",
            "task_id": str(receipt.get("task_id") or task_id),
            "execution_decision_authority": result.execution_decision_authority,
            "canonical_execution": canonical_execution,
            "execution_world": str(canonical_execution.get("execution_world") or ""),
            "canonical_execution_topology": str(
                canonical_execution.get("canonical_execution_topology") or ""
            ),
            "root_receipt": dict(result.root_receipt),
            "root_receipt_valid": result.root_receipt_valid,
            "root_receipt_blockers": list(result.root_receipt_blockers),
            "runtime_receipt_path": result.receipt_path,
            "runtime_dispatched": True,
            "formal_workspace_mutated": False,
            "production_ingress_count": result.production_ingress_count,
            "production_runtime_entry_count": result.production_runtime_entry_count,
            "public_claim_allowed": False,
        }

    @staticmethod
    def _canonical_request(task_id: str, what: str, why: str, allowed: list[str], verifiers: list[str], base: str, *, action: Optional[Mapping[str, Any]] = None, contract_binding: Optional[Mapping[str, Any]] = None, controller_dirty_baseline_authorization: Optional[Mapping[str, Any]] = None, bound_action_request: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        target_worktree_root = CANONICAL_SOURCE_ROOT.parent / "nexus-runtime-targets"
        request = {
            "task_id": task_id, "what": what, "why": why,
            "controller_revision": base, "target_base_revision": base,
            "controller_repo_root": str(CANONICAL_SOURCE_ROOT),
            "target_repo_root": str(target_worktree_root / task_id),
            "target_worktree_root": str(target_worktree_root),
            "allowed_files": allowed, "verifier_commands": verifiers,
        }
        if contract_binding:
            request.update({
                "contract_kind": contract_binding.get("contract_kind"),
                "contract_hash": contract_binding.get("contract_hash"),
                "owner_inline_contract": contract_binding.get("owner_inline_contract"),
                "task_card_path": contract_binding.get("task_card_path"),
                "task_card_hash": contract_binding.get("task_card_hash"),
            })
        if controller_dirty_baseline_authorization:
            request["controller_dirty_baseline_authorization"] = dict(controller_dirty_baseline_authorization)
        if action:
            request["action"] = dict(action)
            request["action_id"] = action.get("action_id")
            request["attempt_id"] = action.get("attempt_id")
            request["idempotency_key"] = action.get("idempotency_key")
            request["action_request_hash"] = action.get("request_hash")
        if bound_action_request is not None:
            request["bound_action_request"] = dict(bound_action_request)
        return request

    @staticmethod
    def _assist_prompt(what: str, why: str, allowed: list[str], verifiers: list[str]) -> str:
        context: list[str] = []
        for raw in allowed:
            path = _safe_relative_path(raw, "allowed_files")
            if path.is_file() and path.stat().st_size <= 128 * 1024:
                context.append(f"FILE {raw}\n{path.read_text(encoding='utf-8')}\nEND FILE")
        return (
            "You are a bounded patch proposer. Use plan/read-only mode. Do not edit files, run tools, or commit. "
            "Return only JSON matching the requested schema, with a unified diff in patch. "
            "The patch string must begin exactly with diff --git and must not use markdown fences. "
            f"WHAT: {what}\nWHY: {why}\nALLOWED FILES: {', '.join(allowed)}\nVERIFIERS: {verifiers}\n" + "\n".join(context)
        )

    @staticmethod
    def _run_agy_plan(*, prompt: str, allowed_files: list[str], provider: str, model: str = "", explicit_effort: str = "") -> dict[str, Any]:
        """Run any registered assisted provider with one bounded JSON contract.

        The historical name is retained for compatibility, but the provider
        edge is no longer hard-coded to Agy. Unknown providers fail closed;
        registered providers still require an installed executable and return
        parser/transport failures as non-success receipts.
        """
        requested = str(provider or "auto").strip().lower() or "auto"
        if requested == "auto":
            requested = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
        metadata = ONLINE_CLI_SPEC_REGISTRY.get(requested)
        if metadata is None:
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_NOT_REGISTERED"}
        binary_env = metadata.get("binary_env", "")
        configured = os.environ.get(binary_env, "").strip() if binary_env else ""
        executable = configured or shutil.which(metadata.get("binary_name", requested))
        if not executable or not Path(executable).is_file():
            return {"provider": requested, "blocker": "ASSIST_PROVIDER_UNAVAILABLE"}
        schema = json.dumps({"type": "object", "required": ["patch"], "properties": {"patch": {"type": "string"}, "summary": {"type": "string"}, "tests": {"type": "array", "items": {"type": "string"}}}}, separators=(",", ":"))
        selected_model = str(model or os.environ.get("NEXUS_ASSIST_MODEL", "") or metadata.get("default_model", "")).strip()
        if requested == "agy":
            try:
                command = _compile_agy_command(
                    executable=executable,
                    model=selected_model,
                    prompt=prompt,
                    json_schema=schema,
                    explicit_effort=explicit_effort,
                )
            except GatewayInputError as exc:
                return {
                    "provider": requested,
                    "model": selected_model,
                    "blocker": "AGY_ARGUMENT_COMPILATION_CONFLICT",
                    "error": str(exc),
                }
        elif requested == "cline":
            # Cline's JSON mode is non-interactive; yolo is restricted to the
            # bounded canonical apply path or an isolated Target by the caller.
            cline_model = selected_model or "glm-5.2"
            if "/" not in cline_model:
                cline_model = f"cline-pass/{cline_model}"
            command = [executable, "--json", "--plan", "--auto-approve", "false", "--thinking", "none", "--timeout", str(CLINE_RUN_TIMEOUT_SECONDS), "--model", cline_model, prompt]
        elif requested == "gemini":
            command = [executable, "--skip-trust", "--approval-mode", "auto_edit", "-m", selected_model, "-p", prompt, "--output-format", "json"]
        elif requested == "opencode":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "codex":
            command = [
                executable,
                "exec",
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-m",
                selected_model,
                prompt,
            ]
        elif requested == "mimo":
            command = [executable, "run", "--model", selected_model, prompt]
        elif requested == "ollama":
            command = [executable, "run", selected_model, prompt]
        elif requested == "grok":
            command = [executable, "--model", selected_model, "--single", prompt, "--output-format", "json", "--no-alt-screen"]
        else:
            command = [executable, "--model", selected_model, "--prompt", prompt]
        provider_timeout = CLINE_RUN_TIMEOUT_SECONDS + 5 if requested == "cline" else 30
        try:
            result = subprocess.run(command, cwd=CANONICAL_SOURCE_ROOT, capture_output=True, text=True, timeout=provider_timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            return {
                "provider": requested,
                "model": selected_model,
                "blocker": "ASSIST_PROVIDER_TIMEOUT",
                "timeout_seconds": provider_timeout,
                "error": str(exc),
                "tool_policy_enforcement": "cline_plan_auto_approve_false_allowlist_not_enforced" if requested == "cline" else "provider_specific",
            }
        if result.returncode != 0:
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_FAILED", "error": result.stderr.strip()[-1000:]}
        def decode_object(text: str) -> dict[str, Any] | None:
            candidates = [text.strip()]
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match and match.group(0) not in candidates:
                candidates.append(match.group(0))
            for candidate_text in candidates:
                try:
                    candidate = json.loads(candidate_text)
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict):
                    return candidate
            return None

        payload = decode_object(result.stdout)
        if requested == "cline" and isinstance(payload, dict) and "patch" not in payload:
            payload = None
        if payload is None:
            for line in reversed(result.stdout.splitlines()):
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(candidate, dict):
                    continue
                nested_texts = [str(candidate.get("text") or "")]
                event = candidate.get("event")
                if isinstance(event, dict):
                    nested_texts.append(str(event.get("text") or ""))
                for nested_text in nested_texts:
                    if nested_text:
                        payload = decode_object(nested_text)
                        if payload is not None:
                            break
                if payload is not None:
                    break
                if requested != "cline":
                    payload = candidate
                    break
            if payload is None:
                return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if not isinstance(payload, dict):
            return {"provider": requested, "model": selected_model, "blocker": "ASSIST_PROVIDER_MALFORMED_OUTPUT"}
        payload["provider"] = requested
        payload["model"] = selected_model
        if requested == "cline":
            payload["tool_policy_enforcement"] = "cline_plan_auto_approve_false_allowlist_not_enforced"
        return payload

    def _finish(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        _require_bound_controller()
        lane = _text(arguments.get("execution_lane"), "execution_lane").upper()
        if lane == "DIRECT_CANONICAL":
            if CONTROLLER_IS_SEPARATE:
                # #2230: a Direct commit puts non-tasks/ code into the Controller,
                # which the next Gateway start would refuse.  Use ISOLATED_TARGET.
                raise GatewayInputError("DIRECT_CANONICAL_FORBIDDEN_WITH_SEPARATE_CONTROLLER")
            request = dict(arguments.get("request") or {})
            if not request:
                task_id = _text(arguments.get("task_id"), "task_id")
                base = arguments.get("base_sha") or arguments.get("controller_revision")
                if not isinstance(base, str) or not _SHA_RE.fullmatch(base):
                    raise GatewayInputError("base_sha is required for minimal Direct finish")
                allowed = [str(path).strip() for path in (arguments.get("allowed_files") or []) if str(path).strip()]
                if not allowed or len(allowed) > 4:
                    raise GatewayInputError("allowed_files is required for minimal Direct finish")
                for path in allowed:
                    _safe_relative_path(path, "allowed_files")
                request = self._canonical_request(
                    task_id,
                    "Complete bounded canonical task",
                    "Finish the prior gateway Direct handoff",
                    allowed,
                    list(arguments.get("verifier_commands") or ["git diff --check"]),
                    base,
                )
            request.setdefault("execution_lane", "DIRECT_CANONICAL")
            request.setdefault("primary_agent", True)
            request.setdefault("worker", "primary")
            result = self.service.complete_direct_canonical(request, expected_commit_sha=arguments.get("expected_commit_sha"))
            action_payload = request.get("action") if isinstance(request.get("action"), Mapping) else None
            if action_payload is not None:
                result["guard_receipt"] = post_action_receipt_formatter(
                    action=action_payload,
                    status="COMPLETED",
                    commit_sha=result.get("commit_sha"),
                    receipt=result,
                )
            return result
        if lane == "ISOLATED_TARGET":
            task_id = _text(arguments.get("task_id"), "task_id")
            fields = ("candidate_commit_sha", "candidate_tree_sha", "candidate_state_hash", "verified_receipt_hash")
            values = {field: _text(arguments.get(field), field) for field in fields}
            return self.service.owner_finish(task_id, **values)
        raise GatewayInputError("execution_lane is unsupported")

    def _call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name == "nexus_gateway_status":
            return self._gateway_status()
        if name == "nexus_gateway_recovery_materialize":
            return self._gateway_recovery_materialize(arguments)
        if name == "nexus_gateway_recovery_preflight":
            return self._gateway_recovery_preflight(arguments)
        if name == "nexus_gateway_recover":
            return self._gateway_recover_exact(arguments)
        if name == "nexus_gateway_convergence":
            return self._gateway_convergence(arguments)
        if name == EXECUTION_READINESS_TOOL_NAME:
            return self._gateway_execution_readiness(arguments)
        if name == "nexus_project_entry":
            return self._project_entry(arguments)
        if name == "nexus_mutation_admit":
            return self._mutation_admit(arguments)
        if name == "nexus_mutation_admission_status":
            return self._mutation_admission_status(arguments)
        if name == "nexus_workspace_snapshot":
            return self._workspace_snapshot()
        if name == "nexus_read":
            return self._read(arguments)
        if name == "nexus_search":
            return self._search(arguments)
        if name == "nexus_git_diff":
            return self._diff(arguments)
        if name == "nexus_task_run":
            return self._task_run(arguments)
        if name == "nexus_worker_candidate":
            return self._worker_candidate(arguments)
        if name == "nexus_task_status":
            task_id = _text(arguments.get("task_id"), "task_id")
            assisted = self._assist_read(task_id)
            if assisted is not None:
                return self._assist_response(self._assist_refresh(task_id) or assisted, operation="status")
            status = self.service.get_task_snapshot(task_id)
            return status or self._task_not_found(task_id, operation="status")
        if name == "nexus_task_wait":
            task_id = _text(arguments.get("task_id"), "task_id")
            timeout = min(60.0, max(0.0, float(arguments.get("timeout_seconds", 10.0))))
            poll = min(5.0, max(0.01, float(arguments.get("poll_interval_seconds", 0.25))))
            if self._assist_read(task_id) is not None:
                return self._assist_wait(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
            waited = self.service.wait_task(task_id, timeout_seconds=timeout, poll_interval_seconds=poll)
            return waited or self._task_not_found(
                task_id,
                operation="wait",
                timeout_seconds=timeout,
                poll_interval_seconds=poll,
            )
        if name == "nexus_task_finish":
            return self._finish(arguments)
        if name == "nexus_task_cancel":
            task_id = _text(arguments.get("task_id"), "task_id")
            if self._assist_read(task_id) is not None:
                return self._assist_cancel(task_id)
            return self.service.cancel_task(task_id)
        if name == "nexus_task_list_actionable":
            return self._task_list_actionable(arguments)
        if name == "nexus_task_reconcile":
            return self._task_reconcile(arguments)
        if name == "nexus_task_retry":
            return self._task_retry(arguments)
        if name == "nexus_task_resume":
            return self._task_resume(arguments)
        if name == "nexus_assist_submit":
            return self._assist_submit(arguments)
        if name == "nexus_assist_result":
            task_id = _text(arguments.get("task_id"), "task_id")
            job = self._assist_read(task_id)
            if job is None:
                raise KeyError(f"unknown task_id: {task_id}")
            return self._assist_response(self._assist_refresh(task_id) or job, operation="result")
        if name == "nexus_assist_cancel":
            return self._assist_cancel(_text(arguments.get("task_id"), "task_id"))
        if name == "nexus_provider_preflight":
            return self._provider_preflight(arguments)
        if name == "nexus_task_card_create":
            return self._task_card_create(arguments)
        if name == "nexus_task_card_commit":
            return self._task_card_commit(arguments)
        if name == "nexus_owner_standing_grant_issue":
            return self._owner_standing_grant_issue(arguments)
        if name == "nexus_task_card_authority_switch":
            return self._task_card_authority_switch(arguments)
        if name == "nexus_task_card_authority_restore":
            return self._task_card_authority_restore(arguments)
        if name == "nexus_model_probe":
            return self._model_probe_submit(arguments)
        if name == "nexus_model_probe_result":
            task_id = _text(arguments.get("task_id"), "task_id")
            job = self._assist_read(task_id)
            if job is None or job.get("job_kind") != "model_probe":
                raise KeyError(f"unknown model_probe task_id: {task_id}")
            return self._assist_response(self._assist_refresh(task_id) or job, operation="result")
        if name == "nexus_model_calibration_evidence":
            return self._model_calibration_evidence(arguments)
        if name == "nexus_model_calibration_plan":
            return self._model_calibration_plan(arguments)
        if name == "nexus_candidate_approve":
            return self._candidate_approve(arguments)
        if name == "nexus_candidate_adopt_external":
            return self._candidate_adopt_external(arguments)
        if name == "nexus_learning_policy_adopt":
            return self._learning_policy_control(
                arguments, action=AutonomyActionClass.LEARNING_POLICY_ADOPT
            )
        if name == "nexus_learning_policy_rollback":
            return self._learning_policy_control(
                arguments, action=AutonomyActionClass.LEARNING_POLICY_ROLLBACK
            )
        if name == "nexus_candidate_bind_integration":
            return self._candidate_bind_integration(arguments)
        if name == "nexus_candidate_integrate":
            return self._candidate_integrate(arguments)
        if name == "nexus_candidate_dispose":
            return self._candidate_dispose(arguments)
        raise GatewayInputError(f"unknown public tool: {name}")

    def handle(self, request: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        method = request.get("method")
        request_id = request.get("id")
        if method is None or method == "notifications/initialized" or request_id is None:
            # Responses to gateway-initiated requests are consumed by the
            # confirmation channel; a stray one is never a new request.
            return None
        if method == "initialize":
            protocol_version = self._negotiate_initialize(request.get("params"))
            return {
                "jsonrpc": "2.0", "id": request_id,
                "result": {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": GATEWAY_NAME,
                        "title": PUBLIC_APP_NAME,
                        "version": GATEWAY_VERSION,
                        "toolManifestRevision": TOOL_MANIFEST_REVISION,
                        "fullToolSchemaHash": FULL_TOOL_SCHEMA_HASH,
                        "permissionPolicyHash": PERMISSION_POLICY_HASH,
                        "taskContractRevision": TASK_CONTRACT_REVISION,
                        "lifecycleRevision": LIFECYCLE_REVISION,
                        "serverInstanceId": SERVER_INSTANCE_ID,
                        "serverStartedAt": SERVER_STARTED_AT,
                        "githubObserver": github_observer_runtime_identity(),
                    },
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tool_specs()}}
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                return self._success(request_id, self._call_tool(str(params.get("name", "")), params.get("arguments") or {}))
            except Exception as exc:
                return self._error(request_id, exc)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def _negotiate_initialize(self, params: Any) -> str:
        params = params if isinstance(params, Mapping) else {}
        requested = str(params.get("protocolVersion") or "")
        capabilities = params.get("capabilities")
        client_info = params.get("clientInfo")
        if (
            self._stdio_streams is not None
            and not self._owner_confirmation_injected
            and client_supports_form_elicitation(requested, capabilities)
        ):
            input_stream, output_stream = self._stdio_streams
            self._owner_confirmation_channel = StdioElicitationChannel(
                input_stream=input_stream,
                output_stream=output_stream,
                protocol_version=NEGOTIATED_ELICITATION_PROTOCOL,
                client_info=client_info if isinstance(client_info, Mapping) else {},
            )
            return NEGOTIATED_ELICITATION_PROTOCOL
        if not self._owner_confirmation_injected:
            self._owner_confirmation_channel = UnavailableConfirmationChannel()
        return LEGACY_PROTOCOL_VERSION

    def serve(self, input_stream, output_stream) -> None:
        # One stdio session: the confirmation channel reads its answer from the
        # same stream, so lines are pulled with readline rather than iteration.
        self._stdio_streams = (input_stream, output_stream)
        while True:
            line = input_stream.readline()
            if not line:
                break
            if not line.strip():
                continue
            response = self.handle(json.loads(line))
            if response is not None:
                output_stream.write(json.dumps(response, sort_keys=True, ensure_ascii=False) + "\n")
                output_stream.flush()


# Single manifest truth: every public name is derived from the actual MCP
# schema returned by tools/list.  No second hand-maintained inventory can drift
# from connector discovery, status, health, or recommended-tool validation.
PUBLIC_TOOL_NAMES = tuple(spec["name"] for spec in UnifiedMCPGateway.tool_specs())
TOOL_MANIFEST_REVISION = hashlib.sha256(
    json.dumps(PUBLIC_TOOL_NAMES, separators=(",", ":")).encode("utf-8")
).hexdigest()
FULL_TOOL_SCHEMA_HASH = hashlib.sha256(
    json.dumps(UnifiedMCPGateway.tool_specs(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
).hexdigest()
try:
    SERVER_REPO_HEAD_AT_START = _loaded_git("rev-parse", "HEAD").strip() or "unknown"
except Exception:
    SERVER_REPO_HEAD_AT_START = "unknown"
# Freeze the runtime source comparison set and its digests at gateway load so
# the freshness baseline never drifts just because a later import loads another
# Nexus module.  A failed start fingerprint is treated as unknown and therefore
# drifts against any readable current fingerprint (fail closed).
RUNTIME_SOURCE_PATHS = _loaded_runtime_source_paths()
try:
    RUNTIME_SOURCE_SHA256_AT_START = _hash_source_paths(RUNTIME_SOURCE_PATHS)
except Exception:
    RUNTIME_SOURCE_SHA256_AT_START = ""
ACTION_CONTRACT_SHA256_AT_START, _ACTION_CONTRACT_OK, _ACTION_CONTRACT_REASONS = _action_contract_fingerprint()
PERMISSION_ENFORCEMENT_SHA256_AT_START, _PERMISSION_ENFORCEMENT_OK, _PERMISSION_ENFORCEMENT_REASONS = _permission_enforcement_fingerprint()
configure_runtime_manifest_hash(TOOL_MANIFEST_REVISION)
