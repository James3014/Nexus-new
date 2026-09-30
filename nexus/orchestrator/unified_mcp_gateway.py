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
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit
from uuid import uuid4

from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.contracts.execution_readiness import (
    COMPLETION_AUTHORITY_KIND,
    HOST_GATEWAY_SERVICE_LABEL,
    ExecutionReadinessBlockerCode,
    ExecutionReadinessPlane,
    ExecutionReadinessRequest,
    ExecutionReadinessStatus,
)
from nexus.contracts.gateway_convergence import (
    ConvergenceAction,
    GatewayConvergenceRequest,
)
from nexus.contracts.lifecycle_action import (
    ContractKind,
    ExternalCandidateAdoptionRequest,
    LifecycleActionEnvelope,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
)
from nexus.contracts.target_integration_lifecycle import ExternalAcceptanceReceipt
from nexus.engine.canonical_task_seam import (
    VerifiedTaskCardIdentity,
    build_canonical_dispatch_envelope,
    build_canonical_planner_admission,
    execute_canonical_product_task,
)
from nexus.engine.learning_policy_loader import (
    DEFAULT_GOVERNED_ADOPTION_PATH,
    DEFAULT_GOVERNED_ROLLBACK_PATH,
)
from nexus.orchestrator.canonical_mcp_ingress import (
    build_mcp_execution_context,
    reject_caller_route_overrides,
)
from nexus.orchestrator.execution_readiness import (
    _COMPLETION_REQUIRED_CAPABILITIES,
    COMPLETION_INTERFACE_REVISION,
    COMPLETION_REPOSITORY,
    CompletionAuthorityObservation,
    GatewayReadinessObservation,
    PlaneObservation,
    evaluate_completion_contract,
    evaluate_execution_readiness,
    evaluate_source_binding,
)
from nexus.orchestrator.gateway_convergence import evaluate_gateway_convergence
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
from nexus.orchestrator.self_hosted_task_service import (
    CANONICAL_SOURCE_ROOT,
    SelfHostedTaskService,
    resolve_contract_identity,
    resolve_lifecycle_identity,
    validate_task_card_binding,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantKey,
    StandingGrantReceipt,
    StandingGrantReceiptError,
    authorize_durable_standing_grant_effect,
    inspect_keyed_standing_grant_receipt,
    load_keyed_standing_grant_receipt,
    restore_task_card_authority,
    switch_task_card_authority,
    write_keyed_standing_grant_receipt,
)
from nexus.services.model_capability_lineage import (
    CHANGE_KIND_VALUES,
    CalibrationPlanner,
    LineageResolutionError,
    ModelCapabilityLineageRegistry,
)
from nexus.services.model_workforce_policy import NON_ADMISSIBLE_STATES, WorkforcePolicyLoader
from nexus.services.unified_runtime import (
    LOCAL_ONLY_PROVIDERS,
    ONLINE_CLI_SPEC_REGISTRY,
    resolve_registered_provider_executable,
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
EPB_CAMPAIGN_ID = "CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01"
EPB_SPEC_ID = "SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001"
EPB_SPEC_SHA256 = "9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1"
MAX_READ_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 1024 * 1024
MAX_SEARCH_RESULTS = 200
MAX_SEARCH_FILE_BYTES = 1024 * 1024
MAX_SEARCH_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SEARCH_FILES = 10000
MAX_SEARCH_SECONDS = 3
MAX_SEARCH_LINE_BYTES = 4096
MAX_SEARCH_STDERR_BYTES = 64 * 1024
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
    command.extend(["--print-timeout", AGY_PRINT_TIMEOUT, "--prompt", prompt])
    return command


class GatewayInputError(ValueError):
    """Raised when a public gateway request is outside its bounded contract."""


def _text(value: Any, field: str, *, max_length: int = 4096) -> str:
    result = str(value or "").strip()
    if not result:
        raise GatewayInputError(f"{field} is required")
    if len(result) > max_length:
        raise GatewayInputError(f"{field} exceeds {max_length} characters")
    return result


EXECUTION_READINESS_TOOL_NAME = "nexus_execution_readiness"
# In-process preflight realm only: each status variable accepts exactly
# "PASSED" or "BLOCKED"; anything else fails closed.
_READINESS_ENV_STATUS_VARS: dict[ExecutionReadinessPlane, str] = {
    ExecutionReadinessPlane.GOVERNANCE: "NEXUS_READINESS_GOVERNANCE_STATUS",
    ExecutionReadinessPlane.AUTHORITY: "NEXUS_READINESS_AUTHORITY_STATUS",
    ExecutionReadinessPlane.REPLAY_FENCE: "NEXUS_READINESS_REPLAY_FENCE_STATUS",
    ExecutionReadinessPlane.WORKFORCE: "NEXUS_READINESS_WORKFORCE_STATUS",
}
# Planes that default to PASSED in the in-process preflight realm, each with an
# explicit evidence identity.  Source is never defaulted: it is derived from
# the exact requested commit/tree versus the canonical checkout.  Gateway,
# host-binding, and action-surface planes carry derived evidence separately.
_READINESS_DEFAULTED_PASSED_PLANES = {
    ExecutionReadinessPlane.GOVERNANCE: "governance_plane:default_no_open_recovery",
    ExecutionReadinessPlane.AUTHORITY: "authority_plane:in_process_caller_context",
    ExecutionReadinessPlane.REPLAY_FENCE: "replay_fence_plane:in_process_first_observation",
}


def _in_process_readiness_plane_observations(
    gateway_observation: GatewayReadinessObservation,
    *,
    request: ExecutionReadinessRequest,
    completion_observation: CompletionAuthorityObservation | None = None,
    required_completion_contract: object | None = None,
) -> dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]]:
    """Gather in-process plane observations for the local preflight realm.

    The gateway plane reuses the exact freshness primitives that
    ``nexus_gateway_status`` uses (same digest, same ``reload_required``
    semantics), so the readiness gate can never disagree with the running
    instance's own status payload.  Remaining env-declared planes accept
    exactly ``PASSED`` or ``BLOCKED``; anything else fails closed.
    """

    observations: dict[ExecutionReadinessPlane, tuple[PlaneObservation, ...]] = {
        ExecutionReadinessPlane.SOURCE: (evaluate_source_binding(request, gateway_observation),)
    }

    if gateway_observation.reload_required:
        observations[ExecutionReadinessPlane.GATEWAY] = (
            PlaneObservation(
                plane=ExecutionReadinessPlane.GATEWAY,
                status=ExecutionReadinessStatus.BLOCKED,
                blocker_code=ExecutionReadinessBlockerCode.GATEWAY_REBIND_REQUIRED,
                evidence_identities=gateway_observation.to_observation_payload(),
            ),
        )
    else:
        observations[ExecutionReadinessPlane.GATEWAY] = (
            PlaneObservation(
                plane=ExecutionReadinessPlane.GATEWAY,
                status=ExecutionReadinessStatus.PASSED,
                evidence_identities=(
                    f"gateway_instance={gateway_observation.gateway_instance_id}",
                    "gateway_reload_required=false",
                    f"gateway_runtime_sha256={gateway_observation.observed_runtime_sha256}",
                ),
            ),
        )

    observations[ExecutionReadinessPlane.HOST_BINDING] = (
        PlaneObservation(
            plane=ExecutionReadinessPlane.HOST_BINDING,
            status=ExecutionReadinessStatus.PASSED,
            evidence_identities=(f"host_binding:{HOST_GATEWAY_SERVICE_LABEL}:in_process",),
        ),
    )
    if required_completion_contract is not None:
        completion_ok, completion_code, completion_evidence = evaluate_completion_contract(
            required_completion_contract, completion_observation
        )
        surface_evidence = (
            f"action_surface:manifest={gateway_observation.tool_manifest_revision}",
            f"action_surface:schema={gateway_observation.full_tool_schema_hash}",
            f"action_surface:permission={gateway_observation.permission_policy_hash}",
        )
        if completion_ok:
            observations[ExecutionReadinessPlane.ACTION_SURFACE] = (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.ACTION_SURFACE,
                    status=ExecutionReadinessStatus.PASSED,
                    evidence_identities=surface_evidence + tuple(completion_evidence),
                ),
            )
        else:
            observations[ExecutionReadinessPlane.ACTION_SURFACE] = (
                PlaneObservation(
                    plane=ExecutionReadinessPlane.ACTION_SURFACE,
                    status=ExecutionReadinessStatus.BLOCKED,
                    blocker_code=(
                        completion_code
                        or ExecutionReadinessBlockerCode.COMPLETION_CONTRACT_BINDING_REQUIRED
                    ),
                    evidence_identities=surface_evidence + tuple(completion_evidence),
                ),
            )
    else:
        observations[ExecutionReadinessPlane.ACTION_SURFACE] = (
            PlaneObservation(
                plane=ExecutionReadinessPlane.ACTION_SURFACE,
                status=ExecutionReadinessStatus.PASSED,
                evidence_identities=(
                    f"action_surface:manifest={gateway_observation.tool_manifest_revision}",
                    f"action_surface:schema={gateway_observation.full_tool_schema_hash}",
                    f"action_surface:permission={gateway_observation.permission_policy_hash}",
                ),
            ),
        )

    _env_declared_blockers = {
        ExecutionReadinessPlane.GOVERNANCE: (
            ExecutionReadinessBlockerCode.GOVERNANCE_PLANE_RECOVERY_REQUIRED
        ),
        ExecutionReadinessPlane.AUTHORITY: ExecutionReadinessBlockerCode.TASK_AUTHORITY_MISSING,
        ExecutionReadinessPlane.REPLAY_FENCE: ExecutionReadinessBlockerCode.SEMANTIC_REPLAY_FENCE,
        ExecutionReadinessPlane.WORKFORCE: ExecutionReadinessBlockerCode.WORKFORCE_NOT_READY,
    }
    # Banded env statuses are processed in G0 precedence order.  An unset
    # status for a plane that has no default (workforce) is UNPROVEN whenever
    # any higher-precedence plane already observed a BLOCK, and fails closed
    # otherwise (a READY verdict can never be fabricated from missing evidence).
    for plane in tuple(_READINESS_ENV_STATUS_VARS):
        env_var = _READINESS_ENV_STATUS_VARS[plane]
        raw = os.environ.get(env_var)
        if raw is None:
            if plane is ExecutionReadinessPlane.WORKFORCE and request.workforce_dispatch_binding:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=("workforce_plane:canonical_binding_supplied",),
                        workforce_dispatch_binding=request.workforce_dispatch_binding,
                    ),
                )
                continue
            # Workforce evidence is completed by the canonical evaluator.  A
            # missing env status must not prevent the evaluator from proving
            # the non-material case or returning WORKFORCE_NOT_READY for
            # material constraints without a typed binding.
            if plane is ExecutionReadinessPlane.WORKFORCE:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=("workforce_plane:canonical_evaluator_pending",),
                    ),
                )
                continue
            default_identity = _READINESS_DEFAULTED_PASSED_PLANES.get(plane)
            if default_identity is not None:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.PASSED,
                        evidence_identities=(default_identity,),
                    ),
                )
                continue
            higher_unproven = any(
                observation.status is ExecutionReadinessStatus.BLOCKED
                for higher_plane, higher_observations in observations.items()
                for observation in higher_observations
                if higher_plane.precedence < plane.precedence
            )
            if higher_unproven:
                observations[plane] = (
                    PlaneObservation(
                        plane=plane,
                        status=ExecutionReadinessStatus.UNPROVEN,
                        evidence_identities=(),
                    ),
                )
                continue
            raise GatewayInputError(f"{env_var} is required for in-process preflight")
        normalized = raw.strip().upper()
        if normalized == "PASSED":
            observations[plane] = (
                PlaneObservation(
                    plane=plane,
                    status=ExecutionReadinessStatus.PASSED,
                    evidence_identities=(f"{env_var}=PASSED",),
                    workforce_dispatch_binding=(
                        request.workforce_dispatch_binding
                        if plane is ExecutionReadinessPlane.WORKFORCE
                        else None
                    ),
                ),
            )
            continue
        if normalized != "BLOCKED":
            raise GatewayInputError(f"{env_var} must be PASSED or BLOCKED")
        blocker = _env_declared_blockers.get(plane)
        if blocker is None:
            raise GatewayInputError(f"{env_var}=BLOCKED is not evaluable in-process")
        observations[plane] = (
            PlaneObservation(
                plane=plane,
                status=ExecutionReadinessStatus.BLOCKED,
                blocker_code=blocker,
                evidence_identities=(f"{env_var}=BLOCKED",),
            ),
        )
    return observations


def _completion_authority_observation_from_environment() -> (
    CompletionAuthorityObservation | None
):
    """Read the observed completion authority identity from the environment.

    Returns ``None`` when no completion environment is configured, which is
    itself a fail-closed blocker whenever the request requires one.
    """

    artifact = os.environ.get("NEXUS_READINESS_COMPLETION_ARTIFACT_IDENTITY")
    if not artifact:
        return None
    return CompletionAuthorityObservation(
        observed_authority_kind=os.environ.get(
            "NEXUS_READINESS_COMPLETION_AUTHORITY_KIND",
            COMPLETION_AUTHORITY_KIND,
        ),
        observed_repository=os.environ.get(
            "NEXUS_READINESS_COMPLETION_REPOSITORY", COMPLETION_REPOSITORY
        ),
        observed_artifact_identity=artifact.strip(),
        observed_interface_revision=os.environ.get(
            "NEXUS_READINESS_COMPLETION_INTERFACE_REVISION",
            COMPLETION_INTERFACE_REVISION,
        ),
        observed_capabilities=tuple(
            item.strip()
            for item in os.environ.get(
                "NEXUS_READINESS_COMPLETION_CAPABILITIES",
                ",".join(_COMPLETION_REQUIRED_CAPABILITIES),
            ).split(",")
            if item.strip()
        ),
    )


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


_GITHUB_CLI_ENV = "NEXUS_GITHUB_CLI"


def _resolve_github_cli() -> tuple[str | None, str | None]:
    """Resolve the GitHub CLI to one executable absolute path before use."""
    configured = os.environ.get(_GITHUB_CLI_ENV, "").strip()
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            return None, f"{_GITHUB_CLI_ENV} must be an absolute path"
    else:
        discovered = shutil.which("gh")
        if not discovered:
            return None, "GitHub CLI executable could not be resolved"
        candidate = Path(discovered)

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        return None, f"GitHub CLI executable could not be resolved: {exc}"
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None, "GitHub CLI resolved path is not an executable file"
    return str(resolved), None


def github_observer_runtime_identity() -> dict[str, Any]:
    """Expose the non-secret executable identity required by Project Entry."""
    executable, _error = _resolve_github_cli()
    if executable is None:
        return {
            "schema": "nexus.github_observer_dependency.v1",
            "ready": False,
            "executable_path": None,
            "executable_sha256": None,
            "failure_code": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        }
    try:
        digest = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
    except OSError:
        return {
            "schema": "nexus.github_observer_dependency.v1",
            "ready": False,
            "executable_path": executable,
            "executable_sha256": None,
            "failure_code": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
        }
    return {
        "schema": "nexus.github_observer_dependency.v1",
        "ready": True,
        "executable_path": executable,
        "executable_sha256": digest,
        "failure_code": None,
    }


def observe_github_issue(repository: str, issue_number: int) -> dict[str, Any]:
    """Fresh, bounded GitHub observation; never writes or infers missing state."""
    github_cli, resolution_error = _resolve_github_cli()
    if github_cli is None:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
            "detail": resolution_error or "GitHub CLI executable unavailable",
        }
    try:
        result = subprocess.run(
            [
                github_cli, "issue", "view", str(issue_number), "--repo", repository,
                "--json", "number,state,updatedAt,url",
            ],
            cwd=CANONICAL_SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_TIMEOUT",
            "detail": str(exc),
        }
    except OSError as exc:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_EXECUTABLE_UNAVAILABLE",
            "detail": str(exc),
        }
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        lowered = detail.lower()
        auth_failure = any(
            marker in lowered
            for marker in (
                "auth login",
                "authentication",
                "not logged into",
                "gh_token",
                "github_token",
            )
        )
        return {
            "ok": False,
            "blocker": (
                "GITHUB_OBSERVER_AUTH_UNAVAILABLE"
                if auth_failure
                else "GITHUB_OBSERVER_REQUEST_FAILED"
            ),
            "detail": detail,
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": str(exc),
        }
    if not isinstance(payload, Mapping) or str(payload.get("number")) != str(issue_number):
        return {
            "ok": False,
            "blocker": "GITHUB_OBSERVER_MALFORMED_RESPONSE",
            "detail": "issue identity mismatch",
        }
    return {
        "ok": True,
        "issue": dict(payload),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def _canonical_remote_matches(origin: str, repository: str) -> bool:
    value = str(origin).strip()
    if value.startswith("git@"):
        host_path = value[4:]
        host, sep, path = host_path.partition(":")
        return sep == ":" and host.lower() == "github.com" and path.removesuffix(".git") == repository
    parsed = urlsplit(value)
    return (
        parsed.scheme.lower() == "https" and parsed.hostname
        and parsed.hostname.lower() == "github.com" and not parsed.username
        and not parsed.password and not parsed.query and not parsed.fragment
        and parsed.path.removesuffix("/").removesuffix(".git").lstrip("/") == repository
    )


def _bounded_text(value: str, field: str) -> str:
    if len(value.encode("utf-8")) > MAX_RESULT_BYTES:
        raise RuntimeError(f"{field} exceeds {MAX_RESULT_BYTES} bytes")
    return value


def _bounded_match_line(line: str) -> tuple[str, bool]:
    """Deterministically cap one search match line so a single oversized line
    cannot blow through the response byte budget.

    Returns ``(bounded_line, truncated)`` where ``truncated`` is true when the
    line was trimmed to ``MAX_SEARCH_LINE_BYTES`` and must surface as a global
    truncation flag.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= MAX_SEARCH_LINE_BYTES:
        return line, False
    return encoded[:MAX_SEARCH_LINE_BYTES].decode("utf-8", errors="ignore"), True


def _git_ls_files(*, root: Path, relative: str) -> list[str]:
    """List Git-tracked and non-ignored untracked files under one relative path.

    Parsing is NUL-safe: the ``-z`` flag emits each path name verbatim (newlines
    and surrounding whitespace preserved) and non-UTF-8 names survive via
    ``os.fsdecode`` surrogateescape.
    """
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--deduplicate", "-z", "--", relative],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=MAX_SEARCH_SECONDS, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed")
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        paths.append(os.fsdecode(raw))
    return paths


def _search_candidate_files(*, root: Path, target: Path) -> list[Path]:
    """Return the ordered candidate files for a literal search target.

    A single regular file scans only that file.  A directory resolves to the
    Git-tracked and non-ignored untracked file list so the search never runs an
    unbounded whole-filesystem recursion.
    """
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError:
        return []
    if not target_resolved.is_symlink() and target_resolved.is_file():
        return [target_resolved]
    try:
        relative = str(target_resolved.relative_to(root_resolved)) or "."
    except ValueError:
        return []
    candidates: list[Path] = []
    for raw in _git_ls_files(root=root_resolved, relative=relative):
        raw_path = root_resolved / raw
        if raw_path.is_symlink():
            continue
        resolved = raw_path.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        candidates.append(resolved)
    candidates.sort(key=lambda path: path.relative_to(root_resolved).as_posix())
    return candidates


def _searchable_file(*, root: Path, candidate: Path) -> bool:
    """Re-validate one candidate file before reading it."""
    if candidate.is_symlink():
        return False
    if ".git" in candidate.parts:
        return False
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    if not candidate.is_file():
        return False
    try:
        if candidate.stat().st_size > MAX_SEARCH_FILE_BYTES:
            return False
    except OSError:
        return False
    return True


def _display_search_path(path: Path, *, root: Path) -> str:
    """Render a canonical-relative path safely when its name bytes are not UTF-8.

    Non-UTF-8 filename bytes are escaped deterministically (e.g. ``caf\xe9.txt``)
    so the displayed path never contains surrogate code points, survives UTF-8
    re-encoding, and stays JSON-serializable.
    """
    relative = path.relative_to(root)
    raw = os.fsencode(relative)
    return raw.decode("utf-8", errors="backslashreplace")


def _literal_matches_in_file(*, root: Path, candidate: Path, pattern: str) -> tuple[list[str], bool]:
    """Literal substring match over one UTF-8 file, skipping unreadable or
    binary content.  Output lines use ``relative/path.py:line:content`` and
    ``truncated`` is true when any matching line was capped."""
    try:
        raw = candidate.read_bytes()
    except OSError:
        return [], False
    if b"\x00" in raw:
        return [], False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [], False
    relative = _display_search_path(candidate, root=root)
    found: list[str] = []
    truncated = False
    for lineno, line in enumerate(text.split("\n"), start=1):
        if pattern not in line:
            continue
        if line.endswith("\r"):
            line = line[:-1]
        bounded, line_truncated = _bounded_match_line(f"{relative}:{lineno}:{line}")
        truncated = truncated or line_truncated
        found.append(bounded)
    return found, truncated


def _python_literal_search(
    *,
    root: Path,
    target: Path,
    pattern: str,
) -> tuple[list[str], bool]:
    """Standard-library literal search fallback used when ripgrep is absent.

    Enforces the named search resource limits and returns ``(matches, truncated)``
    where the match lines are always canonical-root-relative.
    """
    root_resolved = root.resolve()
    candidates = _search_candidate_files(root=root_resolved, target=target)
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    matches: list[str] = []
    output_bytes = 0
    scanned = 0
    total_bytes = 0
    truncated = False
    for candidate in candidates:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        if scanned >= MAX_SEARCH_FILES:
            truncated = True
            break
        if time.monotonic() >= deadline:
            truncated = True
            break
        scanned += 1
        if not _searchable_file(root=root_resolved, candidate=candidate):
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            continue
        if total_bytes + size > MAX_SEARCH_TOTAL_BYTES:
            truncated = True
            break
        total_bytes += size
        file_matches, file_truncated = _literal_matches_in_file(root=root_resolved, candidate=candidate, pattern=pattern)
        truncated = truncated or file_truncated
        for matched in file_matches:
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                break
            matched_bytes = len(matched.encode("utf-8"))
            if output_bytes + matched_bytes > MAX_RESULT_BYTES:
                truncated = True
                break
            matches.append(matched)
            output_bytes += matched_bytes
        if truncated:
            break
    return matches, truncated


def _bounded_rg_matches(lines: list[str]) -> tuple[list[str], bool]:
    """Apply the same result and byte caps to ripgrep output lines."""
    matches: list[str] = []
    truncated = bool(len(lines) > MAX_SEARCH_RESULTS)
    output_bytes = 0
    for line in lines:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        bounded, line_truncated = _bounded_match_line(line)
        truncated = truncated or line_truncated
        matched_bytes = len(bounded.encode("utf-8"))
        if output_bytes + matched_bytes > MAX_RESULT_BYTES:
            truncated = True
            break
        matches.append(bounded)
        output_bytes += matched_bytes
    return matches, truncated


def _terminate_and_reap_search_process(process: subprocess.Popen) -> str:
    """Force a search child to exit and reap it, failing closed on refusal.

    Returns one of ``already_exited``, ``sigterm``, or ``sigkill`` describing
    the action actually taken so the caller only accepts a return code when it
    matches the signal this helper really sent.  terminate -> wait(0.5) ->
    kill -> wait(1.0) bounds the total wait; if the process still refuses to
    die the second wait timeout raises so a leaked child can never pass as a
    successful cleanup.

    If the child exits between ``poll`` and ``terminate``/``kill``
    (``ProcessLookupError``) it is reaped with a bounded ``wait`` and reported
    as ``already_exited`` rather than falsely claiming a signal was sent.
    """
    if process.poll() is not None:
        process.wait()
        return "already_exited"
    try:
        process.terminate()
    except ProcessLookupError:
        process.wait()
        return "already_exited"
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            process.wait()
            return "already_exited"
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            raise RuntimeError("search process cleanup failed") from None
        return "sigkill"
    return "sigterm"


def _run_rg_literal_search(
    *,
    executable: str,
    root: Path,
    relative: str,
    pattern: str,
) -> tuple[list[str], bool]:
    """Run one literal ripgrep search under hard process-level resource limits.

    Reads stdout and stderr in bounded binary chunks (never ``communicate()``
    or a whole ``stdout.read()``) with ``select``-bounded reads so
    ``MAX_SEARCH_SECONDS`` is enforced while the process runs, and counts raw
    streamed bytes so ``MAX_RESULT_BYTES`` caps the process output itself.  The
    stderr pipe is drained simultaneously (never left to backpressure) and
    retained only up to ``MAX_SEARCH_STDERR_BYTES`` for error reporting.

    The process is never force-terminated just because its pipes reached EOF:
    a normally exiting child that outlives its last output gets a bounded
    natural ``wait`` for its own exit.  Only a result limit, an output-byte
    limit, or the deadline may force termination, and the caller only accepts
    a forced exit whose return code matches the signal the helper actually
    sent.  A returning ``_terminate_and_reap_search_process`` of
    ``already_exited`` is classified by the natural return-code rules instead.
    A genuine ripgrep failure (exit code outside the normal 0=matches /
    1=no-matches contract, an unforced signal exit, or a cleanup failure)
    raises ``RuntimeError`` and is never masked by the Python fallback or by a
    truncated-read state.
    """
    process = subprocess.Popen(
        [
            executable,
            "-n",
            "--fixed-strings",
            "--no-heading",
            "--color",
            "never",
            "--with-filename",
            "--max-count",
            str(MAX_SEARCH_RESULTS),
            "--",
            pattern,
            relative,
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stdout_fd = process.stdout.fileno()
    stderr_fd = process.stderr.fileno()
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    matches: list[str] = []
    raw_output_bytes = 0
    truncated = False
    rejected_match_line = False
    line_buffer = bytearray()
    stderr_bytes = bytearray()
    stderr_overflow = False
    forced_termination = False
    termination_reason: str | None = None
    termination_method: str | None = None
    stdout_open = True
    stderr_open = True
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                returncode = process.poll()
                if returncode is not None:
                    process.wait()
                    break
                truncated = True
                forced_termination = True
                termination_reason = "deadline"
                break
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                forced_termination = True
                termination_reason = "result_limit"
                break
            if raw_output_bytes > MAX_RESULT_BYTES:
                truncated = True
                forced_termination = True
                termination_reason = "output_byte_limit"
                break
            active_fds: list[int] = []
            if stdout_open:
                active_fds.append(stdout_fd)
            if stderr_open:
                active_fds.append(stderr_fd)
            if not active_fds:
                natural_remaining = max(0.0, deadline - time.monotonic())
                try:
                    process.wait(timeout=natural_remaining)
                except subprocess.TimeoutExpired:
                    truncated = True
                    forced_termination = True
                    termination_reason = "deadline"
                break
            readable, _, _ = select.select(active_fds, [], [], min(remaining, 0.1))
            if not readable:
                continue
            for fd in readable:
                if fd == stdout_fd:
                    try:
                        chunk = os.read(stdout_fd, 64 * 1024)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stdout_open = False
                        continue
                    raw_output_bytes += len(chunk)
                    if raw_output_bytes > MAX_RESULT_BYTES:
                        truncated = True
                        forced_termination = True
                        termination_reason = "output_byte_limit"
                        break
                    line_buffer.extend(chunk)
                    while b"\n" in line_buffer:
                        raw_line, _, rest = line_buffer.partition(b"\n")
                        line_buffer = bytearray(rest)
                        if rejected_match_line:
                            continue
                        if len(matches) >= MAX_SEARCH_RESULTS:
                            truncated = True
                            rejected_match_line = True
                            continue
                        bounded, line_truncated = _bounded_match_line(
                            raw_line.decode("utf-8", errors="replace")
                        )
                        truncated = truncated or line_truncated
                        matches.append(bounded)
                else:
                    try:
                        chunk = os.read(stderr_fd, 64 * 1024)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stderr_open = False
                        continue
                    room = MAX_SEARCH_STDERR_BYTES - len(stderr_bytes)
                    if room > 0:
                        stderr_bytes.extend(chunk[:room])
                    if len(chunk) > room:
                        stderr_overflow = True
            if termination_reason is not None:
                break
        if line_buffer and not truncated:
            bounded, line_truncated = _bounded_match_line(
                bytes(line_buffer).decode("utf-8", errors="replace")
            )
            truncated = truncated or line_truncated
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
            else:
                matches.append(bounded)
        if forced_termination:
            termination_method = _terminate_and_reap_search_process(process)
        else:
            assert process.returncode is not None
    finally:
        for cleanup_stream in (process.stdout, process.stderr):
            try:
                cleanup_stream.close()
            except Exception:
                pass

    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    if stderr_overflow:
        stderr_text += "[stderr truncated]"
    stderr_text = stderr_text.strip()

    returncode = process.returncode
    if forced_termination:
        if termination_method == "already_exited":
            if returncode not in (0, 1):
                raise RuntimeError(stderr_text or f"search failed (exit {returncode})")
        elif termination_method == "sigterm":
            if returncode != -signal.SIGTERM:
                raise RuntimeError(stderr_text or "search process exited unexpectedly")
        elif termination_method == "sigkill":
            if returncode != -signal.SIGKILL:
                raise RuntimeError(stderr_text or "search process exited unexpectedly")
        else:  # pragma: no cover - defensive; helper only returns documented values
            raise RuntimeError("search process cleanup failed")
    elif returncode not in (0, 1):
        raise RuntimeError(stderr_text or f"search failed (exit {returncode})")
    return matches, truncated


def _loaded_runtime_source_paths() -> tuple[Path, ...]:
    """Collect the Nexus Python modules already loaded inside the canonical repo.

    The comparison set must be frozen at gateway start; later imports of other
    modules must never change it.
    """
    root_resolved = CANONICAL_SOURCE_ROOT.resolve()
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


def _hash_source_paths(paths: tuple[Path, ...], *, root: Path = CANONICAL_SOURCE_ROOT) -> str:
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
    root: Path = CANONICAL_SOURCE_ROOT,
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
    root: Path = CANONICAL_SOURCE_ROOT,
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

[Showing lines 1-1315 of 6578 (50.0KB limit). Use offset=1316 to continue.]