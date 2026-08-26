"""Pure, fail-closed bindings for the Gateway deployment owner.

The module deliberately has no filesystem, process, network, or clock access.
It describes the only identities that the durable adapter may act on and keeps
the state machine/hash rules deterministic.  The adapter in
``scripts/ops/mcp_gateway_durable.py`` is the sole effect owner.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import re
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Mapping, TypeVar

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

REPOSITORY = "James3014/Nexus-new"
REMOTE = "https://github.com/James3014/Nexus-new.git"
LABEL = "com.nexus.mcp.gateway.direct"
PLIST = "/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist"
STDOUT = "/Users/jameschen/Library/Logs/Nexus/gateway.log"
STDERR = "/Users/jameschen/Library/Logs/Nexus/gateway.err.log"
ENDPOINT = "http://127.0.0.1:8766"
CURRENT_ROOT = "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe"
DESIRED_ROOT = "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-935a9dd3"
ENV_FILE = "/Users/jameschen/Library/Application Support/Nexus/mcp-gateway.env"
STATE_DIR = "/Users/jameschen/Workspace/Nexus-new-self-hosted-state"
CURRENT_WRAPPER_PLIST_SHA256 = "082c7786f9b7254949a6fdb38d905414a78c1b1979aabf7f434dd7019c09e100"
# The exact loaded `.direct` plist uses a fixed `/bin/zsh -c` wrapper.  The
# command literals are immutable; the desired form changes only the root and
# entrypoint which are derived from the frozen desired profile.
CURRENT_WRAPPER_COMMAND = (
    "cd /Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe "
    '; source "/Users/jameschen/Library/Application Support/Nexus/mcp-gateway.env" '
    "; export PYTHONDONTWRITEBYTECODE=1 "
    "; export NEXUS_CANONICAL_SOURCE_ROOT=/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe "
    "; export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR=/Users/jameschen/Workspace/Nexus-new-self-hosted-state "
    "; exec /Users/jameschen/Workspace/Nexus-new/.venv/bin/python "
    "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"
)
INTERPRETER = "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python"
INTERPRETER_TARGET = (
    "/Users/jameschen/.local/share/uv/python/cpython-3.14.0-macos-aarch64-none/bin/python3.14"
)
INTERPRETER_SHA256 = "c89af0b037c601180919ca5fd8a936bd2568cbb4976f91a208c10f54c17a1b78"
ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
GATEWAY_ACTION = "gateway-rebind"
GATEWAY_TASK_ID = "TASK-526-A"
GATEWAY_LIFECYCLE_REVISION = "nexus.lifecycle.gateway.v2"


def _gateway_wrapper_command(root: str, entrypoint: str) -> str:
    """Build the sole permitted fixed-literal Gateway shell wrapper."""
    frozen = {
        CURRENT_ROOT: str(Path(CURRENT_ROOT) / ENTRYPOINT),
        DESIRED_ROOT: str(Path(DESIRED_ROOT) / ENTRYPOINT),
    }
    if root not in frozen or entrypoint != frozen[root]:
        raise ContractError("wrapper profile root invalid")
    if any(
        token in root or token in entrypoint
        for token in (";", "&&", "|", "$", "`", "\n", "\r", "\x00")
    ):
        raise ContractError("wrapper path contains shell metacharacter")
    executable = entrypoint
    return (
        f'cd {root} ; source "{ENV_FILE}" ; export PYTHONDONTWRITEBYTECODE=1 ; '
        f"export NEXUS_CANONICAL_SOURCE_ROOT={root} ; "
        f"export NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR={STATE_DIR} ; "
        f"exec {INTERPRETER} {executable}"
    )


CURRENT_WRAPPER_COMMAND = _gateway_wrapper_command(
    CURRENT_ROOT, str(Path(CURRENT_ROOT) / ENTRYPOINT)
)
SCHEMA = "nexus.gateway.deployment.v1"
HOST_AUTHORITY_SCHEMA = "nexus.gateway.host_effect_authority.v1"
HOST_AUTHORITY_SCOPE = "NEXUS_GATEWAY_REBIND_HOST_EFFECT_ONLY"
HOST_AUTHORITY_BUNDLE_SCHEMA = "nexus.gateway.host_effect_authority_bundle.v1"
HOST_AUTHORITY_BUNDLE_SCOPE = "NEXUS_GATEWAY_REBIND_HOST_EFFECT_BUNDLE_ONLY"
HOST_CARD_ID = "TASK-526-HOST-1"
HOST_CARD_PATH = (
    "tasks/github-issue-526-host-authority-and-canary-20260823/01-gateway-host-local-canary.md"
)
HOST_CARD_SHA256 = "f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514"
RECOVERY_CARD_PATH = (
    "tasks/github-issue-526-host-authority-and-canary-20260823/"
    "09-durable-deployment-reconciliation.md"
)
RECOVERY_CARD_SHA256 = "b316a07965b070d1b76fa11fa20105d40bd2be1de325576e719a127bdc1d8609"
RECOVERY_RECEIPT_PATH = (
    "tasks/github-issue-526-host-authority-and-canary-20260823/"
    "10-durable-recovery-authority-receipt.json"
)
OWNER_ACTIVATION_ID = "OWNER_ISSUE526_CONTINUE_20260823"
OWNER_ACTIVATION_SHA256 = "f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322"
OWNER_SOURCE_THREAD = "01a02a17-691c-7a20-ad0f-9166456416dc"
TASK002_RECOVERY_ACTIVATION_ID = "OWNER_ISSUE526_TASK002_GATEWAY_REBIND_20260826"
TASK002_RECOVERY_ACTIVATION_SHA256 = (
    "61ebd493c8a405213043382dc1bb0d225185c5528126573311de2cba9cff4eb9"
)
TASK002_RECOVERY_SOURCE_COMMENT = "5418927784"
TASK002_RECOVERY_DESIRED_COMMIT = "b2a9cca573580d2edbd5531bb9e4bf92479e0e3a"
TASK002_RECOVERY_DESIRED_TREE = "747d9dcecd47dff3d063e7948496d8adb33f50bc"
TASK002_RECOVERY_PREDECESSOR_COMMIT = "3d28fa7b65df30e207e53de7caadf93a2b7a8fc0"
TASK002_RECOVERY_PREDECESSOR_TREE = "5e6476b2b12211e7cdcfe9294942b633ffbcef59"
STANDING_GRANT_ID = "OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW"
STANDING_GRANT_RECEIPT_SHA256 = "3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5"
SOURCE_BASE_MERGE = "ac4a9ab1e0180170ca062cdc81f2142bca8bd80f"
SOURCE_BASE_TREE = "db329f4931b55b74f1e1f9fe61f7edf4ca8422bc"


class ContractError(ValueError):
    """Invalid, stale, substituted, or otherwise untrusted contract data."""


class DeploymentState(StrEnum):
    REQUESTED = "REQUESTED"
    PREFLIGHTED = "PREFLIGHTED"
    TARGET_READY = "TARGET_READY"
    ROLLBACK_READY = "ROLLBACK_READY"
    ROLLBACK_UNAVAILABLE = "ROLLBACK_UNAVAILABLE"
    STARTED = "STARTED"
    EFFECT_STARTED = "EFFECT_STARTED"
    SERVICE_OBSERVED = "SERVICE_OBSERVED"
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    CLIENT_BOUND = "CLIENT_BOUND"
    VERIFIED = "VERIFIED"
    UNCERTAIN_EFFECT = "UNCERTAIN_EFFECT"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"


class EffectClass(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    INSTALL_ARTIFACT = "INSTALL_ARTIFACT"
    GATEWAY_RELOAD = "GATEWAY_RELOAD"
    GATEWAY_ROLLBACK = "GATEWAY_ROLLBACK"
    STATUS = "STATUS"
    GATEWAY_DURABLE_RECOVERY = "GATEWAY_DURABLE_RECOVERY"


class ResultClass(StrEnum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    UNCERTAIN_EFFECT = "UNCERTAIN_EFFECT"
    ROLLED_BACK = "ROLLED_BACK"


class DeploymentReadiness(StrEnum):
    TARGET_READY = "TARGET_READY"
    ROLLBACK_READY = "ROLLBACK_READY"
    ROLLBACK_UNAVAILABLE = "ROLLBACK_UNAVAILABLE"


T = TypeVar("T")


class StrictRecord:
    """Small dataclass equivalent of a frozen ``extra=forbid`` model.

    Pydantic is intentionally not imported here: this module is also used by
    the tiny manager bootstrap.  ``model_validate``/``model_dump`` provide the
    familiar strict typed-schema surface for callers and tests.
    """

    _converters: ClassVar[Mapping[str, Any]] = {}

    @classmethod
    def model_validate(cls: type[T], value: Any) -> T:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ContractError(f"{cls.__name__} must be an object")
        names = {item.name for item in fields(cls)}
        unknown = set(value) - names
        required = {
            item.name
            for item in fields(cls)
            if item.default is MISSING and item.default_factory is MISSING
        }
        if unknown or not required.issubset(value):
            raise ContractError(f"{cls.__name__} schema mismatch")
        converted = {}
        for name, item in ((item.name, item) for item in fields(cls)):
            if name not in value:
                continue
            raw = value[name]
            converter = cls._converters.get(name)
            if converter is not None:
                try:
                    raw = converter(raw)
                except (TypeError, ValueError, KeyError) as exc:
                    raise ContractError(f"{cls.__name__}.{name} invalid") from exc
            converted[name] = raw
        result = cls(**converted)  # type: ignore[arg-type]
        _strict_types(result)
        return result

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        return _plain(self)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _strict_types(value: Any) -> None:
    """Reject the common bool-as-int and collection coercions of loose schemas."""
    if not is_dataclass(value):
        return
    for item in fields(value):
        raw = getattr(value, item.name)
        numeric_fields = {
            "uid",
            "gid",
            "pid",
            "sequence",
            "owner_uid",
            "owner_gid",
            "bundle_size",
        } | (
            {"mode"}
            if type(value).__name__
            in {"StableArtifactIdentity", "DeploymentManifest", "BareStoreEvidence"}
            else set()
        )
        if (
            item.name in numeric_fields
            and raw is not None
            and (not isinstance(raw, int) or isinstance(raw, bool))
        ):
            raise ContractError(f"{type(value).__name__}.{item.name} type mismatch")
        if item.name in {
            "clean",
            "loaded",
            "client_bound",
            "token_bound",
            "is_bare",
            "alternates_absent",
            "bundle_verified",
            "effect_started",
            "acknowledged",
            "applied",
            "already_desired",
        } and not isinstance(raw, bool):
            raise ContractError(f"{type(value).__name__}.{item.name} type mismatch")
        if item.name in {
            "required_actions",
            "observed_actions",
            "pending_actions",
            "receipts",
        } and not isinstance(raw, tuple):
            raise ContractError(f"{type(value).__name__}.{item.name} type mismatch")


def canonical_hash(value: Any) -> str:
    """Canonical SHA-256 used for every request, ledger, and identity fence."""
    encoded = json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hash(value: Any, name: str, length: int = 64) -> None:
    pattern = HEX64 if length == 64 else HEX40
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ContractError(f"invalid {name}")


def _id(value: str, name: str) -> None:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise ContractError(f"invalid {name}")


def _absolute(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or not Path(value).is_absolute() or "\x00" in value:
        raise ContractError(f"invalid {name}")


@dataclass(frozen=True)
class RepositoryProfile(StrictRecord):
    repository: str = REPOSITORY
    remote: str = REMOTE
    label: str = LABEL
    plist: str = PLIST
    stdout: str = STDOUT
    stderr: str = STDERR
    endpoint: str = ENDPOINT


@dataclass(frozen=True)
class GitIdentity(StrictRecord):
    root: str
    toplevel: str
    head: str
    tree: str
    remote: str = REMOTE
    clean: bool = True


@dataclass(frozen=True)
class InterpreterIdentity(StrictRecord):
    path: str = INTERPRETER
    resolved_path: str = INTERPRETER_TARGET
    sha256: str = INTERPRETER_SHA256
    uid: int = 501
    gid: int = 20
    mode: str = "lrwxr-xr-x"


@dataclass(frozen=True)
class RecoveryEntrypointIdentity(StrictRecord):
    """One role's complete, tracked Git entrypoint identity."""

    path: str
    blob_oid: str
    sha256: str
    tracked_mode: str = "100644"


@dataclass(frozen=True)
class RecoverySourceSet(StrictRecord):
    """Pure semantic identity; physical bundle and receipt observations are excluded."""

    repository: str
    accepted_commit: str
    accepted_tree: str
    accepted_entrypoint: RecoveryEntrypointIdentity
    desired_commit: str
    desired_tree: str
    desired_entrypoint: RecoveryEntrypointIdentity
    predecessor_commit: str
    predecessor_tree: str
    predecessor_entrypoint: RecoveryEntrypointIdentity
    interpreter: InterpreterIdentity
    source_set_sha256: str

    _converters: ClassVar[Mapping[str, Any]] = {
        "accepted_entrypoint": RecoveryEntrypointIdentity.model_validate,
        "desired_entrypoint": RecoveryEntrypointIdentity.model_validate,
        "predecessor_entrypoint": RecoveryEntrypointIdentity.model_validate,
        "interpreter": InterpreterIdentity.model_validate,
    }


@dataclass(frozen=True)
class DeploymentManifest(StrictRecord):
    """Manager-derived deployment identity for one semantic source-set role."""

    deployment_id: str
    role: str
    repository: str
    source_set_sha256: str
    commit: str
    tree: str
    entrypoint: str
    entrypoint_blob_oid: str
    entrypoint_sha256: str
    tracked_mode: str
    interpreter: InterpreterIdentity
    content_sha256: str
    manifest_sha256: str
    owner_uid: int
    owner_gid: int
    mode: int = 0o644

    _converters: ClassVar[Mapping[str, Any]] = {
        "interpreter": InterpreterIdentity.model_validate,
    }


@dataclass(frozen=True)
class BundleRoleHead(StrictRecord):
    role: str
    ref: str
    commit: str


@dataclass(frozen=True)
class BareStoreEvidence(StrictRecord):
    path: str
    repository: str
    origin: str
    is_bare: bool
    alternates_absent: bool
    owner_uid: int
    owner_gid: int
    mode: int
    object_set_sha256: str


@dataclass(frozen=True)
class SourceBundleEvidence(StrictRecord):
    """Post-receipt physical evidence.  It is never an authority record."""

    request_id: str
    request_hash: str
    idempotency_fence: str
    receipt_id: str
    receipt_hash: str
    source_set_sha256: str
    observed_fresh_main_commit: str
    observed_fresh_main_tree: str
    role_heads: tuple[BundleRoleHead, ...]
    bundle_sha256: str
    bundle_size: int
    bundle_verified: bool
    bare_store: BareStoreEvidence
    observed_at: str
    evidence_hash: str

    _converters: ClassVar[Mapping[str, Any]] = {
        "role_heads": lambda value: tuple(BundleRoleHead.model_validate(item) for item in value),
        "bare_store": BareStoreEvidence.model_validate,
    }


@dataclass(frozen=True)
class RecoveryLedgerRecord(StrictRecord):
    schema: str
    request_id: str
    request_hash: str
    state: DeploymentState
    sequence: int
    parent_hash: str
    record_hash: str
    authority_schema: str
    receipt_id: str
    receipt_hash: str
    card_sha256: str
    accepted_source_merge: str
    accepted_source_tree: str
    final_manager_sha256: str
    independent_acceptance_receipt_hash: str
    source_set_sha256: str
    desired_manifest_id: str
    desired_manifest_hash: str
    predecessor_manifest_id: str
    predecessor_manifest_hash: str
    source_bundle_evidence_hash: str | None
    operation: str
    effect_class: EffectClass
    idempotency_fence: str
    pre_effect_identity: Mapping[str, Any]
    observed_identity: Mapping[str, Any]

    _converters: ClassVar[Mapping[str, Any]] = {
        "state": DeploymentState,
        "effect_class": EffectClass,
    }


@dataclass(frozen=True)
class RecoveryEffectPlan(StrictRecord):
    request_id: str
    request_hash: str
    idempotency_fence: str
    receipt_id: str
    receipt_hash: str
    source_set_sha256: str
    desired_manifest_id: str
    desired_manifest_hash: str
    predecessor_manifest_id: str
    predecessor_manifest_hash: str
    desired_root: str
    predecessor_root: str
    service_label: str
    plist_path: str
    endpoint: str
    pre_effect_identity_hash: str
    plan_hash: str


@dataclass(frozen=True)
class RecoveryEffectAck(StrictRecord):
    plan_hash: str
    acknowledged: bool
    applied: bool
    already_desired: bool
    effect_kind: str
    evidence_hash: str


@dataclass(frozen=True)
class RecoveryPhysicalIdentity(StrictRecord):
    loaded: bool
    service_label: str
    pid: int | None
    start_identity: str
    listener: Any
    plist_sha256: str
    deployment_id: str
    root: str
    head: str
    tree: str
    server_instance: str
    observed_at: str
    evidence_hash: str


@dataclass(frozen=True)
class GatewayReconcileOutcome(StrictRecord):
    """Read-only continuation result for the original recovery request."""

    request_id: str
    request_hash: str
    idempotency_fence: str
    desired_manifest_id: str
    predecessor_manifest_id: str
    physical_observation: Mapping[str, Any]
    effect_started: bool
    result: ResultClass
    evidence_hash: str

    _converters: ClassVar[Mapping[str, Any]] = {"result": ResultClass}


@dataclass(frozen=True)
class DeploymentProfile(StrictRecord):
    git: GitIdentity
    entrypoint: str = ENTRYPOINT
    entrypoint_sha256: str = ""
    interpreter: InterpreterIdentity = field(default_factory=InterpreterIdentity)
    trust_class: str = ""
    repository: RepositoryProfile = field(default_factory=RepositoryProfile)

    _converters: ClassVar[Mapping[str, Any]] = {
        "git": GitIdentity.model_validate,
        "interpreter": InterpreterIdentity.model_validate,
        "repository": RepositoryProfile.model_validate,
    }


TrustedDeploymentProfile = DeploymentProfile


@dataclass(frozen=True)
class AuthorityReceipt(StrictRecord):
    issuer: str
    receipt_id: str
    repository: str = REPOSITORY
    action: str = "gateway-rebind"
    scope: str = "NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY"
    issued_at: str = ""
    expires_at: str = ""
    request_id: str = ""
    receipt_hash: str = ""


@dataclass(frozen=True)
class HostEffectAuthorityReceipt(StrictRecord):
    """The independent, owner-issued authority for one physical Gateway effect.

    This receipt is deliberately a different type and hash domain from
    :class:`AuthorityReceipt`.  A source Candidate can therefore never be
    upgraded by copying its scope or issuer into a host request.
    """

    schema: str
    receipt_version: int
    receipt_id: str
    receipt_hash: str
    scope: str
    issuer_id: str
    coordinator_id: str
    authorized_actor_id: str
    owner_activation_id: str
    owner_activation_sha256: str
    source_thread: str
    standing_grant_id: str
    standing_grant_receipt_sha256: str
    source_base_merge: str
    source_base_tree: str
    correction_merge_sha: str
    correction_tree_sha: str
    independent_acceptance_receipt_hash: str
    final_manager_sha256: str
    current_main_sha: str
    host_card_path: str
    host_card_id: str
    host_card_sha256: str
    repository: str
    operation: str
    effect_class: EffectClass
    service_label: str
    plist_path: str
    endpoint: str
    current_profile_hash: str
    desired_profile_hash: str
    request_id: str
    idempotency_fence: str
    issued_at: str
    expires_at: str
    revocation_state: str
    revoked_at: str | None
    revocation_reason: str | None

    _converters: ClassVar[Mapping[str, Any]] = {"effect_class": EffectClass}


@dataclass(frozen=True)
class RecoveryAuthorityReceipt(StrictRecord):
    """Separate R1 source authority; never parsed as the legacy host bundle."""

    SCHEMA: ClassVar[str] = "nexus.gateway.durable_recovery_authority.v1"
    schema: str
    receipt_version: int
    receipt_id: str
    receipt_hash: str
    card_sha256: str
    source_base_merge: str
    source_base_tree: str
    current_main_sha: str
    operation: str
    effect_class: EffectClass
    service_label: str
    plist_path: str
    endpoint: str
    desired_manifest_id: str
    desired_manifest_sha256: str
    predecessor_manifest_id: str
    predecessor_manifest_sha256: str
    request_id: str
    idempotency_fence: str
    issued_at: str
    expires_at: str
    revocation_state: str
    revoked_at: str | None
    revocation_reason: str | None
    issuer_id: str
    coordinator_id: str
    authorized_actor_id: str
    owner_activation_id: str
    owner_activation_sha256: str
    source_thread: str
    standing_grant_id: str
    standing_grant_receipt_sha256: str
    repository: str
    host_card_path: str
    accepted_source_merge: str
    accepted_source_tree: str
    final_manager_sha256: str
    independent_acceptance_receipt_hash: str
    authority_floor_commit: str
    authority_floor_tree: str
    desired_commit: str
    desired_tree: str
    predecessor_commit: str
    predecessor_tree: str
    source_set: RecoverySourceSet
    desired_manifest: DeploymentManifest
    predecessor_manifest: DeploymentManifest

    _converters: ClassVar[Mapping[str, Any]] = {
        "effect_class": EffectClass,
        "source_set": RecoverySourceSet.model_validate,
        "desired_manifest": DeploymentManifest.model_validate,
        "predecessor_manifest": DeploymentManifest.model_validate,
    }


@dataclass(frozen=True)
class HostEffectAuthorityBundle(StrictRecord):
    """Immutable pre-authority for the complete host effect sequence.

    The tuple order is part of the bundle hash.  A bundle is evidence until
    :func:`select_host_effect_authority_receipt` proves that exactly one child
    is an active, byte-equal authority for the request.
    """

    schema: str
    bundle_version: int
    bundle_id: str
    bundle_hash: str
    scope: str
    repository: str
    host_card_path: str
    host_card_id: str
    host_card_sha256: str
    source_base_merge: str
    source_base_tree: str
    correction_merge_sha: str
    correction_tree_sha: str
    independent_acceptance_receipt_hash: str
    final_manager_sha256: str
    current_main_sha: str
    issued_at: str
    expires_at: str
    revocation_state: str
    revoked_at: str | None
    revocation_reason: str | None
    receipts: tuple[HostEffectAuthorityReceipt, ...]

    _converters: ClassVar[Mapping[str, Any]] = {
        "receipts": lambda value: tuple(
            HostEffectAuthorityReceipt.model_validate(item) for item in value
        ),
    }


@dataclass(frozen=True)
class IdentityEvidence(StrictRecord):
    label: str = LABEL
    plist_sha256: str = ""
    pid: int | None = None
    server_instance: str = ""
    root: str = ""
    head: str = ""
    tree: str = ""
    source_sha256: str = ""
    tool_manifest_sha256: str = ""
    schema_sha256: str = ""
    permission_sha256: str = ""
    action: str = ""
    task_id: str = ""
    lifecycle: str = ""
    loaded: bool = False
    endpoint: str = ENDPOINT
    client_bound: bool = False
    plist_bytes_sha256: str = ""


@dataclass(frozen=True)
class QuiescenceEvidence(StrictRecord):
    disposition: str
    lifecycle_state: str = ""
    assist_state: str = ""
    evidence_sha256: str = ""
    pending_actions: tuple[str, ...] = ()
    reacquisition_receipt: str = ""

    _converters: ClassVar[Mapping[str, Any]] = {"pending_actions": lambda value: tuple(value)}


@dataclass(frozen=True)
class StableArtifactIdentity(StrictRecord):
    source_root: str
    source_head: str
    source_tree: str
    source_path: str
    source_blob_sha256: str
    artifact_sha256: str
    uid: int
    mode: int
    predecessor_sha256: str = ""
    request_id: str = ""
    card_id: str = "TASK-526-A"
    authority_receipt_id: str = ""
    install_fence: str = ""
    rollback_receipt: str = ""


@dataclass(frozen=True)
class RollbackCapture(StrictRecord):
    plist_sha256: str
    plist_bytes_sha256: str
    plist_bytes_hex: str
    artifact_sha256: str
    source_sha256: str
    loaded: bool
    server_instance: str = ""
    source_root: str = ""
    source_head: str = ""
    source_tree: str = ""
    interpreter_sha256: str = INTERPRETER_SHA256
    label: str = LABEL
    program_arguments_hash: str = ""
    root: str = ""
    stdout: str = STDOUT
    stderr: str = STDERR
    environment_hash: str = ""


@dataclass(frozen=True)
class PostflightIdentity(StrictRecord):
    server_instance: str
    root: str
    head: str
    tree: str
    tool_manifest_sha256: str
    schema_sha256: str
    permission_sha256: str
    action: str
    task_id: str
    lifecycle: str
    client_bound: bool
    required_actions: tuple[str, ...]
    observed_actions: tuple[str, ...]
    token_bound: bool

    _converters: ClassVar[Mapping[str, Any]] = {
        "required_actions": lambda value: tuple(value),
        "observed_actions": lambda value: tuple(value),
    }


@dataclass(frozen=True)
class LedgerRecord(StrictRecord):
    schema: str
    request_id: str
    request_hash: str
    state: DeploymentState
    sequence: int
    parent_hash: str
    record_hash: str
    pre_effect_identity: Mapping[str, Any] = field(default_factory=dict)
    observed_identity: Mapping[str, Any] = field(default_factory=dict)

    _converters: ClassVar[Mapping[str, Any]] = {"state": DeploymentState}


@dataclass(frozen=True)
class GatewayDeploymentRequest(StrictRecord):
    request_id: str
    idempotency_fence: str
    operation: str
    authority: AuthorityReceipt
    current: DeploymentProfile
    desired: DeploymentProfile
    current_identity: IdentityEvidence
    rollback: RollbackCapture
    quiescence: QuiescenceEvidence
    postflight: PostflightIdentity
    effect_class: EffectClass
    request_hash: str = ""
    schema: str = SCHEMA
    stable_artifact: StableArtifactIdentity | None = None
    host_authority: HostEffectAuthorityReceipt | None = None

    _converters: ClassVar[Mapping[str, Any]] = {
        "authority": AuthorityReceipt.model_validate,
        "current": DeploymentProfile.model_validate,
        "desired": DeploymentProfile.model_validate,
        "current_identity": IdentityEvidence.model_validate,
        "rollback": RollbackCapture.model_validate,
        "quiescence": QuiescenceEvidence.model_validate,
        "effect_class": EffectClass,
        "postflight": PostflightIdentity.model_validate,
        "stable_artifact": lambda value: (
            None if value is None else StableArtifactIdentity.model_validate(value)
        ),
        "host_authority": lambda value: (
            None if value is None else HostEffectAuthorityReceipt.model_validate(value)
        ),
    }


@dataclass(frozen=True)
class GatewayRecoveryRequest(StrictRecord):
    """R1-B request: references authority and manifests, never their bodies."""

    request_id: str
    idempotency_fence: str
    operation: str
    effect_class: EffectClass
    recovery_authority_id: str
    recovery_authority_hash: str
    desired_manifest_id: str
    desired_manifest_hash: str
    predecessor_manifest_id: str
    predecessor_manifest_hash: str
    request_hash: str = ""
    schema: str = "nexus.gateway.durable_recovery_request.v1"

    _converters: ClassVar[Mapping[str, Any]] = {"effect_class": EffectClass}


def validate_repository(profile: RepositoryProfile) -> RepositoryProfile:
    if not isinstance(profile, RepositoryProfile):
        raise ContractError("repository profile must be typed")
    if profile.repository != REPOSITORY or profile.remote != REMOTE or profile.label != LABEL:
        raise ContractError("repository/service identity mismatch")
    for value, name in (
        (profile.plist, "plist"),
        (profile.stdout, "stdout"),
        (profile.stderr, "stderr"),
    ):
        _absolute(value, name)
    if profile.endpoint != ENDPOINT:
        raise ContractError("endpoint mismatch")
    return profile


def validate_deployment_manifest(manifest: DeploymentManifest) -> DeploymentManifest:
    if not isinstance(manifest, DeploymentManifest):
        raise ContractError("deployment manifest must be typed")
    _id(manifest.deployment_id, "deployment id")
    if manifest.role not in {"desired", "predecessor"}:
        raise ContractError("deployment role mismatch")
    if manifest.repository != REPOSITORY:
        raise ContractError("deployment repository mismatch")
    _hash(manifest.source_set_sha256, "deployment source-set hash")
    _hash(manifest.commit, "deployment commit", 40)
    _hash(manifest.tree, "deployment tree", 40)
    if manifest.entrypoint != ENTRYPOINT:
        raise ContractError("deployment entrypoint mismatch")
    _hash(manifest.entrypoint_blob_oid, "deployment entrypoint blob", 40)
    _hash(manifest.entrypoint_sha256, "deployment entrypoint hash")
    if manifest.tracked_mode != "100644":
        raise ContractError("deployment tracked mode mismatch")
    _hash(manifest.content_sha256, "deployment content hash")
    if manifest.content_sha256 != manifest.entrypoint_sha256:
        raise ContractError("deployment content identity mismatch")
    _hash(manifest.manifest_sha256, "deployment manifest hash")
    expected_deployment_id = (
        "r1-"
        + canonical_hash({
            "schema": "nexus.gateway.deployment_manifest.v2",
            "role": manifest.role,
            "repository": manifest.repository,
            "source_set_sha256": manifest.source_set_sha256,
        })[:40]
    )
    if manifest.deployment_id != expected_deployment_id:
        raise ContractError("deployment id is not manager-derived")
    expected_manifest_hash = canonical_hash({
        key: value for key, value in manifest.model_dump().items() if key != "manifest_sha256"
    })
    if manifest.manifest_sha256 != expected_manifest_hash:
        raise ContractError("deployment manifest hash mismatch")
    fixed_interpreter = InterpreterIdentity()
    if (
        manifest.owner_uid != fixed_interpreter.uid
        or manifest.owner_gid != fixed_interpreter.gid
        or manifest.mode != 0o644
    ):
        raise ContractError("deployment ownership/mode mismatch")
    if manifest.interpreter != fixed_interpreter:
        raise ContractError("deployment interpreter mismatch")
    return manifest


def validate_recovery_source_set(source_set: RecoverySourceSet) -> RecoverySourceSet:
    if not isinstance(source_set, RecoverySourceSet):
        raise ContractError("recovery source set must be typed")
    if source_set.repository != REPOSITORY:
        raise ContractError("recovery source-set repository mismatch")
    for value, name in (
        (source_set.accepted_commit, "accepted commit"),
        (source_set.accepted_tree, "accepted tree"),
        (source_set.desired_commit, "desired commit"),
        (source_set.desired_tree, "desired tree"),
        (source_set.predecessor_commit, "predecessor commit"),
        (source_set.predecessor_tree, "predecessor tree"),
    ):
        _hash(value, name, 40)
    for role, entrypoint in (
        ("accepted", source_set.accepted_entrypoint),
        ("desired", source_set.desired_entrypoint),
        ("predecessor", source_set.predecessor_entrypoint),
    ):
        if entrypoint.path != ENTRYPOINT or entrypoint.tracked_mode != "100644":
            raise ContractError(f"{role} source-set entrypoint mismatch")
        _hash(entrypoint.blob_oid, f"{role} entrypoint blob", 40)
        _hash(entrypoint.sha256, f"{role} entrypoint hash")
    if source_set.interpreter != InterpreterIdentity():
        raise ContractError("recovery source-set interpreter mismatch")
    _hash(source_set.source_set_sha256, "recovery source-set hash")
    expected = canonical_hash({
        key: value for key, value in source_set.model_dump().items() if key != "source_set_sha256"
    })
    if source_set.source_set_sha256 != expected:
        raise ContractError("recovery source-set hash mismatch")
    return source_set


def derive_deployment_manifest(
    source_set: RecoverySourceSet,
    *,
    role: str,
) -> DeploymentManifest:
    """Derive the only valid manifest/ID from a validated semantic source set."""
    validate_recovery_source_set(source_set)
    if role == "desired":
        commit, tree, entrypoint = (
            source_set.desired_commit,
            source_set.desired_tree,
            source_set.desired_entrypoint,
        )
    elif role == "predecessor":
        commit, tree, entrypoint = (
            source_set.predecessor_commit,
            source_set.predecessor_tree,
            source_set.predecessor_entrypoint,
        )
    else:
        raise ContractError("deployment role mismatch")
    deployment_id = (
        "r1-"
        + canonical_hash({
            "schema": "nexus.gateway.deployment_manifest.v2",
            "role": role,
            "repository": source_set.repository,
            "source_set_sha256": source_set.source_set_sha256,
        })[:40]
    )
    values = {
        "deployment_id": deployment_id,
        "role": role,
        "repository": source_set.repository,
        "source_set_sha256": source_set.source_set_sha256,
        "commit": commit,
        "tree": tree,
        "entrypoint": entrypoint.path,
        "entrypoint_blob_oid": entrypoint.blob_oid,
        "entrypoint_sha256": entrypoint.sha256,
        "tracked_mode": entrypoint.tracked_mode,
        "interpreter": source_set.interpreter,
        "content_sha256": entrypoint.sha256,
        "owner_uid": source_set.interpreter.uid,
        "owner_gid": source_set.interpreter.gid,
        "mode": 0o644,
    }
    manifest = DeploymentManifest(
        **values,
        manifest_sha256=canonical_hash(values),
    )
    return validate_deployment_manifest(manifest)


def validate_source_bundle_evidence(
    evidence: SourceBundleEvidence,
    *,
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    source_set: RecoverySourceSet,
    expected_fresh_main_commit: str,
    expected_fresh_main_tree: str,
    expected_bare_store: BareStoreEvidence,
) -> SourceBundleEvidence:
    if not isinstance(evidence, SourceBundleEvidence):
        raise ContractError("source bundle evidence must be typed")
    validate_recovery_request(request)
    validate_recovery_authority(receipt, request=request)
    validate_recovery_source_set(source_set)
    if receipt.source_set != source_set:
        raise ContractError("source bundle trusted source-set mismatch")
    _hash(expected_fresh_main_commit, "trusted fresh main commit", 40)
    _hash(expected_fresh_main_tree, "trusted fresh main tree", 40)
    if (
        not isinstance(expected_bare_store, BareStoreEvidence)
        or not Path(expected_bare_store.path).is_absolute()
        or expected_bare_store.repository != REPOSITORY
        or not expected_bare_store.origin
        or expected_bare_store.is_bare is not True
        or expected_bare_store.alternates_absent is not True
        or expected_bare_store.owner_uid != InterpreterIdentity().uid
        or expected_bare_store.owner_gid != InterpreterIdentity().gid
        or expected_bare_store.mode != 0o700
    ):
        raise ContractError("trusted bare store identity mismatch")
    _id(evidence.request_id, "bundle request id")
    _id(evidence.idempotency_fence, "bundle fence")
    _id(evidence.receipt_id, "bundle receipt id")
    for value, name, length in (
        (evidence.request_hash, "bundle request hash", 64),
        (evidence.receipt_hash, "bundle receipt hash", 64),
        (evidence.source_set_sha256, "bundle source-set hash", 64),
        (evidence.observed_fresh_main_commit, "fresh main commit", 40),
        (evidence.observed_fresh_main_tree, "fresh main tree", 40),
        (evidence.bundle_sha256, "raw bundle hash", 64),
        (evidence.bare_store.object_set_sha256, "bare object-set hash", 64),
        (evidence.evidence_hash, "bundle evidence hash", 64),
    ):
        _hash(value, name, length)
    expected_roles = (
        ("fresh-main", "refs/nexus-r1/fresh-main"),
        ("desired", "refs/nexus-r1/desired"),
        ("predecessor", "refs/nexus-r1/predecessor"),
    )
    if not isinstance(evidence.role_heads, tuple) or len(evidence.role_heads) != 3:
        raise ContractError("source bundle must contain exactly three named roles")
    for head, (role, ref) in zip(evidence.role_heads, expected_roles, strict=True):
        if head.role != role or head.ref != ref:
            raise ContractError("source bundle named role mismatch")
        _hash(head.commit, f"{role} bundle head", 40)
    if tuple(head.commit for head in evidence.role_heads) != (
        expected_fresh_main_commit,
        source_set.desired_commit,
        source_set.predecessor_commit,
    ):
        raise ContractError("source bundle trusted role head mismatch")
    if (
        evidence.request_id != request.request_id
        or evidence.request_hash != request.request_hash
        or evidence.idempotency_fence != request.idempotency_fence
        or evidence.receipt_id != receipt.receipt_id
        or evidence.receipt_hash != receipt.receipt_hash
        or evidence.source_set_sha256 != source_set.source_set_sha256
    ):
        raise ContractError("source bundle trusted request/receipt/source-set mismatch")
    if (
        evidence.observed_fresh_main_commit != expected_fresh_main_commit
        or evidence.observed_fresh_main_tree != expected_fresh_main_tree
    ):
        raise ContractError("source bundle trusted fresh-main mismatch")
    if evidence.bundle_size <= 0 or evidence.bundle_verified is not True:
        raise ContractError("source bundle physical verification missing")
    if (
        not Path(evidence.bare_store.path).is_absolute()
        or evidence.bare_store.repository != REPOSITORY
        or not evidence.bare_store.origin
        or evidence.bare_store.is_bare is not True
        or evidence.bare_store.alternates_absent is not True
        or evidence.bare_store.owner_uid != InterpreterIdentity().uid
        or evidence.bare_store.owner_gid != InterpreterIdentity().gid
        or evidence.bare_store.mode != 0o700
    ):
        raise ContractError("bare store evidence mismatch")
    if evidence.bare_store != expected_bare_store:
        raise ContractError("source bundle trusted bare store mismatch")
    if not isinstance(evidence.observed_at, str) or not evidence.observed_at:
        raise ContractError("bundle observation time missing")
    expected_hash = canonical_hash({
        key: value for key, value in evidence.model_dump().items() if key != "evidence_hash"
    })
    if evidence.evidence_hash != expected_hash:
        raise ContractError("source bundle evidence hash mismatch")
    return evidence


def validate_reconcile_outcome(
    outcome: GatewayReconcileOutcome,
) -> GatewayReconcileOutcome:
    if not isinstance(outcome, GatewayReconcileOutcome):
        raise ContractError("reconcile outcome must be typed")
    _id(outcome.request_id, "reconcile request id")
    _id(outcome.idempotency_fence, "reconcile fence")
    _id(outcome.desired_manifest_id, "reconcile desired manifest")
    _id(outcome.predecessor_manifest_id, "reconcile predecessor manifest")
    _hash(outcome.request_hash, "reconcile request hash")
    _hash(outcome.evidence_hash, "reconcile evidence hash")
    if not isinstance(outcome.physical_observation, Mapping):
        raise ContractError("reconcile physical observation missing")
    if type(outcome.effect_started) is not bool or not isinstance(outcome.result, ResultClass):
        raise ContractError("reconcile result type mismatch")
    expected = canonical_hash({
        key: value for key, value in outcome.model_dump().items() if key != "evidence_hash"
    })
    if outcome.evidence_hash != expected:
        raise ContractError("reconcile evidence hash mismatch")
    return outcome


def derive_recovery_ledger_binding(
    *,
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    source_bundle_evidence: SourceBundleEvidence,
) -> str:
    validate_recovery_request(request)
    validate_recovery_authority(receipt, request=request)
    return canonical_hash({
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "authority_schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "card_sha256": receipt.card_sha256,
        "accepted_source_merge": receipt.accepted_source_merge,
        "accepted_source_tree": receipt.accepted_source_tree,
        "final_manager_sha256": receipt.final_manager_sha256,
        "independent_acceptance_receipt_hash": (receipt.independent_acceptance_receipt_hash),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "source_bundle_evidence_hash": source_bundle_evidence.evidence_hash,
        "operation": request.operation,
        "effect_class": request.effect_class,
        "idempotency_fence": request.idempotency_fence,
    })


def validate_recovery_ledger_record(
    record: RecoveryLedgerRecord,
    *,
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    source_bundle_evidence: SourceBundleEvidence | None,
    expected_sequence: int,
    expected_parent_hash: str,
) -> RecoveryLedgerRecord:
    if not isinstance(record, RecoveryLedgerRecord):
        raise ContractError("recovery ledger record must be typed")
    validate_recovery_request(request)
    validate_recovery_authority(receipt, request=request)
    if record.schema != "nexus.gateway.ledger.v2":
        raise ContractError("recovery ledger schema mismatch")
    if type(record.sequence) is not int or record.sequence != expected_sequence:
        raise ContractError("recovery ledger sequence mismatch")
    if record.parent_hash != expected_parent_hash:
        raise ContractError("recovery ledger parent mismatch")
    if record.sequence == 1:
        if record.parent_hash != "":
            raise ContractError("first recovery ledger parent must be empty")
    else:
        _hash(record.parent_hash, "recovery ledger parent")
    _hash(record.request_hash, "recovery ledger request")
    _hash(record.record_hash, "recovery ledger record")
    expected_hash = canonical_hash({
        key: value for key, value in record.model_dump().items() if key != "record_hash"
    })
    if record.record_hash != expected_hash:
        raise ContractError("recovery ledger record hash mismatch")
    evidence_hash = None if source_bundle_evidence is None else source_bundle_evidence.evidence_hash
    if record.state is DeploymentState.REQUESTED:
        if record.source_bundle_evidence_hash is not None:
            raise ContractError("REQUESTED recovery row cannot bind bundle evidence")
    elif evidence_hash is None or record.source_bundle_evidence_hash != evidence_hash:
        raise ContractError("recovery ledger bundle evidence mismatch")
    exact = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "authority_schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "card_sha256": receipt.card_sha256,
        "accepted_source_merge": receipt.accepted_source_merge,
        "accepted_source_tree": receipt.accepted_source_tree,
        "final_manager_sha256": receipt.final_manager_sha256,
        "independent_acceptance_receipt_hash": (receipt.independent_acceptance_receipt_hash),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "operation": request.operation,
        "effect_class": request.effect_class,
        "idempotency_fence": request.idempotency_fence,
    }
    for name, expected in exact.items():
        if getattr(record, name) != expected:
            raise ContractError(f"recovery ledger trusted {name} mismatch")
    if not isinstance(record.pre_effect_identity, Mapping) or not isinstance(
        record.observed_identity, Mapping
    ):
        raise ContractError("recovery ledger identity evidence invalid")
    return record


def validate_recovery_effect_plan(
    plan: RecoveryEffectPlan,
    *,
    request: GatewayRecoveryRequest,
    receipt: RecoveryAuthorityReceipt,
    deployment_root: str = (
        "/Users/jameschen/Library/Application Support/Nexus/gateway-direct/deployments"
    ),
) -> RecoveryEffectPlan:
    if not isinstance(plan, RecoveryEffectPlan):
        raise ContractError("recovery effect plan must be typed")
    validate_recovery_request(request)
    validate_recovery_authority(receipt, request=request)
    fixed = {
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "idempotency_fence": request.idempotency_fence,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "desired_root": str(Path(deployment_root) / receipt.desired_manifest_id),
        "predecessor_root": str(Path(deployment_root) / receipt.predecessor_manifest_id),
        "service_label": LABEL,
        "plist_path": PLIST,
        "endpoint": ENDPOINT,
    }
    for name, expected in fixed.items():
        if getattr(plan, name) != expected:
            raise ContractError(f"recovery effect plan {name} mismatch")
    _hash(plan.pre_effect_identity_hash, "pre-effect identity")
    _hash(plan.plan_hash, "recovery effect plan")
    expected_hash = canonical_hash({
        key: value for key, value in plan.model_dump().items() if key != "plan_hash"
    })
    if plan.plan_hash != expected_hash:
        raise ContractError("recovery effect plan hash mismatch")
    return plan


def validate_recovery_effect_ack(
    ack: RecoveryEffectAck,
    *,
    plan: RecoveryEffectPlan,
) -> RecoveryEffectAck:
    if not isinstance(ack, RecoveryEffectAck):
        raise ContractError("recovery effect acknowledgement must be typed")
    if ack.plan_hash != plan.plan_hash or ack.effect_kind != "GATEWAY_DURABLE_RECOVERY":
        raise ContractError("recovery effect acknowledgement binding mismatch")
    if (
        type(ack.acknowledged) is not bool
        or type(ack.applied) is not bool
        or type(ack.already_desired) is not bool
    ):
        raise ContractError("recovery effect acknowledgement type mismatch")
    if not ack.acknowledged or (ack.applied and ack.already_desired):
        raise ContractError("recovery effect acknowledgement state mismatch")
    _hash(ack.evidence_hash, "recovery effect acknowledgement")
    expected = canonical_hash({
        key: value for key, value in ack.model_dump().items() if key != "evidence_hash"
    })
    if ack.evidence_hash != expected:
        raise ContractError("recovery effect acknowledgement hash mismatch")
    return ack


def validate_recovery_physical_identity(
    identity: RecoveryPhysicalIdentity,
    *,
    expected_manifest: DeploymentManifest,
    expected_root: str,
    expected_plist_sha256: str | None = None,
) -> RecoveryPhysicalIdentity:
    if not isinstance(identity, RecoveryPhysicalIdentity):
        raise ContractError("recovery physical identity must be typed")
    validate_deployment_manifest(expected_manifest)
    if (
        identity.loaded is not True
        or identity.service_label != LABEL
        or type(identity.pid) is not int
        or identity.pid <= 0
        or not identity.start_identity
        or identity.listener != ENDPOINT
        or identity.deployment_id != expected_manifest.deployment_id
        or identity.root != expected_root
        or identity.head != expected_manifest.commit
        or identity.tree != expected_manifest.tree
        or not identity.server_instance
        or not identity.observed_at
        or (expected_plist_sha256 is not None and identity.plist_sha256 != expected_plist_sha256)
    ):
        raise ContractError("recovery physical identity mismatch")
    _hash(identity.plist_sha256, "recovery physical plist")
    _hash(identity.evidence_hash, "recovery physical identity")
    expected = canonical_hash({
        key: value for key, value in identity.model_dump().items() if key != "evidence_hash"
    })
    if identity.evidence_hash != expected:
        raise ContractError("recovery physical identity hash mismatch")
    return identity


def validate_recovery_request(request: GatewayRecoveryRequest) -> GatewayRecoveryRequest:
    if (
        not isinstance(request, GatewayRecoveryRequest)
        or request.schema != GatewayRecoveryRequest.__dataclass_fields__["schema"].default
    ):
        raise ContractError("R1 recovery request schema mismatch")
    if (
        request.operation != "gateway-recover"
        or request.effect_class is not EffectClass.GATEWAY_DURABLE_RECOVERY
    ):
        raise ContractError("R1 recovery operation/effect mismatch")
    for value, name, length in (
        (request.request_id, "request id", 128),
        (request.idempotency_fence, "fence", 128),
        (request.recovery_authority_id, "authority id", 128),
        (request.desired_manifest_id, "desired id", 128),
        (request.predecessor_manifest_id, "predecessor id", 128),
        (request.recovery_authority_hash, "authority hash", 64),
        (request.desired_manifest_hash, "desired manifest hash", 64),
        (request.predecessor_manifest_hash, "predecessor manifest hash", 64),
    ):
        (_hash(value, name) if length == 64 else _id(value, name))
    expected = canonical_hash({
        key: value
        for key, value in request.model_dump().items()
        if key not in {"request_hash", "schema"}
    })
    if request.request_hash != expected:
        raise ContractError("R1 recovery request hash mismatch")
    return request


def validate_profile(
    profile: DeploymentProfile, *, expected: DeploymentProfile | None = None
) -> DeploymentProfile:
    if not isinstance(profile, DeploymentProfile):
        raise ContractError("profile must be typed")
    validate_repository(profile.repository)
    g = profile.git
    if not isinstance(g, GitIdentity) or not isinstance(profile.interpreter, InterpreterIdentity):
        raise ContractError("profile nested identity must be typed")
    for value, name in ((g.root, "root"), (g.toplevel, "toplevel")):
        _absolute(value, name)
    if g.root != g.toplevel or g.remote != REMOTE:
        raise ContractError("profile trust mismatch")
    # A dirty profile is only ever the observed rollback-only current profile.
    # Any other dirty profile, including a dirty desired target, is rejected.
    if g.clean is False:
        frozen_current = globals().get("CURRENT_PROFILE")
        if frozen_current is None or _plain(profile) != _plain(frozen_current):
            raise ContractError("only the frozen rollback-only current profile may be dirty")
    elif g.clean is not True:
        raise ContractError("profile trust mismatch")
    _hash(g.head, "HEAD", 40)
    _hash(g.tree, "tree", 40)
    if profile.entrypoint not in (ENTRYPOINT, str(Path(g.root) / ENTRYPOINT)):
        raise ContractError("entrypoint mismatch")
    _hash(profile.entrypoint_sha256, "entrypoint hash")
    _hash(profile.interpreter.sha256, "interpreter hash")
    if (
        profile.interpreter.path != INTERPRETER
        or profile.interpreter.resolved_path != INTERPRETER_TARGET
    ):
        raise ContractError("interpreter mismatch")
    if (
        not isinstance(profile.interpreter.uid, int)
        or isinstance(profile.interpreter.uid, bool)
        or not isinstance(profile.interpreter.gid, int)
        or isinstance(profile.interpreter.gid, bool)
    ):
        raise ContractError("interpreter ownership mismatch")
    if (
        profile.interpreter.mode != "lrwxr-xr-x"
        or profile.interpreter.uid != 501
        or profile.interpreter.gid != 20
    ):
        raise ContractError("interpreter mode/ownership mismatch")
    if profile.trust_class == "" or not isinstance(profile.trust_class, str):
        raise ContractError("trust class missing")
    known_profiles = globals().get("CURRENT_PROFILE"), globals().get("DESIRED_PROFILE")
    if all(item is not None for item in known_profiles):
        if profile not in {item for item in known_profiles if item is not None}:
            raise ContractError("profile differs from complete frozen deployment identity")
    if expected is not None and profile != expected:
        raise ContractError("profile differs from explicit expected identity")
    return profile


def compare_profiles(current: DeploymentProfile, desired: DeploymentProfile) -> bool:
    """Return true only when the current server is exactly the desired canary."""
    validate_profile(current)
    validate_profile(desired)
    if current.git.clean is not desired.git.clean:
        return False
    if current.git.root != desired.git.root:
        return False
    return current.git.head == desired.git.head and current.git.tree == desired.git.tree


def validate_desired_profile(
    current: DeploymentProfile, desired: DeploymentProfile
) -> DeploymentProfile:
    validate_profile(current)
    validate_profile(desired)
    if current.git.head == desired.git.head and current.git.tree == desired.git.tree:
        raise ContractError("desired profile must be an explicit different target")
    return desired


_EDGES: dict[DeploymentState, set[DeploymentState]] = {
    DeploymentState.REQUESTED: {DeploymentState.PREFLIGHTED, DeploymentState.BLOCKED},
    DeploymentState.PREFLIGHTED: {
        DeploymentState.TARGET_READY,
        DeploymentState.STARTED,
        DeploymentState.BLOCKED,
    },
    DeploymentState.TARGET_READY: {
        DeploymentState.ROLLBACK_READY,
        DeploymentState.ROLLBACK_UNAVAILABLE,
        DeploymentState.BLOCKED,
    },
    DeploymentState.ROLLBACK_READY: {DeploymentState.EFFECT_STARTED, DeploymentState.BLOCKED},
    DeploymentState.ROLLBACK_UNAVAILABLE: {DeploymentState.BLOCKED},
    DeploymentState.STARTED: {
        DeploymentState.SERVICE_OBSERVED,
        DeploymentState.UNCERTAIN_EFFECT,
        DeploymentState.BLOCKED,
    },
    DeploymentState.EFFECT_STARTED: {
        DeploymentState.SERVICE_OBSERVED,
        DeploymentState.UNCERTAIN_EFFECT,
        DeploymentState.BLOCKED,
    },
    DeploymentState.SERVICE_OBSERVED: {
        DeploymentState.IDENTITY_VERIFIED,
        DeploymentState.UNCERTAIN_EFFECT,
    },
    DeploymentState.IDENTITY_VERIFIED: {
        DeploymentState.CLIENT_BOUND,
        DeploymentState.UNCERTAIN_EFFECT,
    },
    DeploymentState.CLIENT_BOUND: {DeploymentState.VERIFIED, DeploymentState.UNCERTAIN_EFFECT},
    DeploymentState.UNCERTAIN_EFFECT: {
        DeploymentState.SERVICE_OBSERVED,
        DeploymentState.ROLLED_BACK,
        DeploymentState.BLOCKED,
    },
    DeploymentState.ROLLBACK_STARTED: {
        DeploymentState.ROLLED_BACK,
        DeploymentState.UNCERTAIN_EFFECT,
        DeploymentState.BLOCKED,
    },
}


def transition(previous: DeploymentState | str, current: DeploymentState | str) -> DeploymentState:
    try:
        previous_state, current_state = DeploymentState(previous), DeploymentState(current)
    except ValueError as exc:
        raise ContractError("unknown deployment state") from exc
    if current_state not in _EDGES.get(previous_state, set()):
        raise ContractError(f"invalid transition {previous_state}->{current_state}")
    return current_state


def _validate_rollback(capture: RollbackCapture) -> None:
    for value, name in (
        (capture.plist_sha256, "rollback plist"),
        (capture.plist_bytes_sha256, "rollback bytes"),
        (capture.artifact_sha256, "rollback artifact"),
        (capture.source_sha256, "rollback source"),
    ):
        _hash(value, name)
    if (
        not isinstance(capture.plist_bytes_hex, str)
        or not capture.plist_bytes_hex
        or len(capture.plist_bytes_hex) % 2
    ):
        raise ContractError("rollback bytes missing")
    try:
        payload = bytes.fromhex(capture.plist_bytes_hex)
    except (TypeError, ValueError) as exc:
        raise ContractError("rollback bytes are not hex") from exc
    payload_hash = hashlib.sha256(payload).hexdigest()
    if payload_hash != capture.plist_bytes_sha256 or payload_hash != capture.plist_sha256:
        raise ContractError("rollback bytes hash mismatch")
    if capture.label != LABEL or capture.interpreter_sha256 != INTERPRETER_SHA256:
        raise ContractError("rollback fixed identity mismatch")
    if capture.root != CURRENT_PROFILE.git.root or capture.source_root != CURRENT_PROFILE.git.root:
        raise ContractError("rollback source root mismatch")
    if (
        capture.source_head != CURRENT_PROFILE.git.head
        or capture.source_tree != CURRENT_PROFILE.git.tree
    ):
        raise ContractError("rollback source revision mismatch")
    for value, name in (
        (capture.program_arguments_hash, "rollback program arguments"),
        (capture.environment_hash, "rollback environment"),
    ):
        _hash(value, name)
    try:
        parsed = plistlib.loads(payload)
    except Exception as exc:
        raise ContractError("rollback plist malformed") from exc
    if not isinstance(parsed, Mapping) or parsed.get("Label") != LABEL:
        raise ContractError("rollback plist label mismatch")
    args = parsed.get("ProgramArguments")
    env = parsed.get("EnvironmentVariables")
    if not isinstance(args, list) or not isinstance(env, (dict, type(None))):
        raise ContractError("rollback plist arguments malformed")
    if len(args) == 3 and args[0] == "/bin/zsh" and args[1] == "-c":
        # Exact legacy wrapper allowlist: the observed current `.direct`
        # plist.  This is the only accepted shell/wrapper form and it never
        # grants generic shell authority.
        if args[2] != CURRENT_WRAPPER_COMMAND:
            raise ContractError("rollback wrapper command mismatch")
        if env not in (None, {}):
            raise ContractError("rollback wrapper environment mismatch")
        allowed_keys = {
            "Label",
            "ProgramArguments",
            "RunAtLoad",
            "KeepAlive",
            "WorkingDirectory",
            "StandardOutPath",
            "StandardErrorPath",
        }
        expected_payload_hash = CURRENT_WRAPPER_PLIST_SHA256
    else:
        # Direct interpreter form retained for compatibility only.
        if args != [INTERPRETER, str(Path(CURRENT_ROOT) / ENTRYPOINT)]:
            raise ContractError("rollback program arguments mismatch")
        if env != {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}:
            raise ContractError("rollback environment mismatch")
        allowed_keys = {
            "Label",
            "EnvironmentVariables",
            "ProgramArguments",
            "RunAtLoad",
            "KeepAlive",
            "WorkingDirectory",
            "StandardOutPath",
            "StandardErrorPath",
        }
        expected_payload_hash = payload_hash
    if set(parsed) != allowed_keys:
        raise ContractError("rollback plist fields mismatch")
    if (
        parsed.get("RunAtLoad") is not True
        or parsed.get("KeepAlive") is not True
        or parsed.get("WorkingDirectory") != CURRENT_PROFILE.git.root
        or parsed.get("StandardOutPath") != STDOUT
        or parsed.get("StandardErrorPath") != STDERR
    ):
        raise ContractError("rollback fixed plist identity mismatch")
    if payload_hash != expected_payload_hash:
        raise ContractError("legacy rollback wrapper hash mismatch")
    if parsed.get("WorkingDirectory") != CURRENT_PROFILE.git.root:
        raise ContractError("rollback working directory mismatch")
    if parsed.get("StandardOutPath") != STDOUT or parsed.get("StandardErrorPath") != STDERR:
        raise ContractError("rollback log identity mismatch")
    if parsed.get("RunAtLoad") is not True or parsed.get("KeepAlive") is not True:
        raise ContractError("rollback launch flags mismatch")
    if (
        canonical_hash(args) != capture.program_arguments_hash
        or canonical_hash(env) != capture.environment_hash
    ):
        raise ContractError("rollback identity hash mismatch")


def validate_source_authority(
    receipt: AuthorityReceipt, *, request_id: str | None = None
) -> AuthorityReceipt:
    """Validate provenance only; this receipt has no host-effect authority."""
    if not isinstance(receipt, AuthorityReceipt):
        raise ContractError("source authority receipt must be typed")
    if not receipt.issuer or not receipt.receipt_id:
        raise ContractError("source authority identity missing")
    _id(receipt.receipt_id, "source receipt id")
    if receipt.repository != REPOSITORY or receipt.action != "gateway-rebind":
        raise ContractError("source authority identity mismatch")
    if receipt.scope != "NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY":
        raise ContractError("source authority scope mismatch")
    if request_id is not None and receipt.request_id != request_id:
        raise ContractError("source authority request mismatch")
    _hash(receipt.receipt_hash, "source receipt hash")
    expected = canonical_hash({
        key: value for key, value in _plain(receipt).items() if key != "receipt_hash"
    })
    if receipt.receipt_hash != expected:
        raise ContractError("source authority receipt hash mismatch")
    return receipt


def validate_host_effect_authority(
    receipt: HostEffectAuthorityReceipt,
    *,
    request: "GatewayDeploymentRequest | None" = None,
    now: str | None = None,
    allow_revoked: bool = False,
) -> HostEffectAuthorityReceipt:
    """Validate one host-effect receipt without reading the host store.

    ``allow_revoked`` is intentionally limited to evidence parsing by the
    bundle validator.  The effect selector never enables it.
    """
    if not isinstance(receipt, HostEffectAuthorityReceipt):
        raise ContractError("host authority receipt must be typed")
    if (
        receipt.schema != HOST_AUTHORITY_SCHEMA
        or type(receipt.receipt_version) is not int
        or receipt.receipt_version != 1
    ):
        raise ContractError("host authority schema/version mismatch")
    _id(receipt.receipt_id, "host receipt id")
    if receipt.scope != HOST_AUTHORITY_SCOPE:
        raise ContractError("host authority scope mismatch")
    _hash(receipt.receipt_hash, "host receipt hash")
    exact = {
        "issuer_id": "owner-james",
        "coordinator_id": "coordinator-codex",
        "authorized_actor_id": "coordinator-codex",
        "owner_activation_id": OWNER_ACTIVATION_ID,
        "owner_activation_sha256": OWNER_ACTIVATION_SHA256,
        "source_thread": OWNER_SOURCE_THREAD,
        "standing_grant_id": STANDING_GRANT_ID,
        "standing_grant_receipt_sha256": STANDING_GRANT_RECEIPT_SHA256,
        "source_base_merge": SOURCE_BASE_MERGE,
        "source_base_tree": SOURCE_BASE_TREE,
        "host_card_path": HOST_CARD_PATH,
        "host_card_id": HOST_CARD_ID,
        "host_card_sha256": HOST_CARD_SHA256,
        "repository": REPOSITORY,
        "service_label": LABEL,
        "plist_path": PLIST,
        "endpoint": ENDPOINT,
    }
    for name, expected in exact.items():
        if getattr(receipt, name) != expected:
            raise ContractError(f"host authority {name} mismatch")
    operation_effects = {
        "status": EffectClass.STATUS,
        "gateway-status": EffectClass.STATUS,
        "preflight": EffectClass.PREFLIGHT,
        "gateway-preflight": EffectClass.PREFLIGHT,
        "install": EffectClass.INSTALL_ARTIFACT,
        "install-artifact": EffectClass.INSTALL_ARTIFACT,
        "install_artifact": EffectClass.INSTALL_ARTIFACT,
        "reload": EffectClass.GATEWAY_RELOAD,
        "gateway-reload": EffectClass.GATEWAY_RELOAD,
        "rollback": EffectClass.GATEWAY_ROLLBACK,
        "gateway-rollback": EffectClass.GATEWAY_ROLLBACK,
    }
    if (
        receipt.operation not in operation_effects
        or receipt.effect_class is not operation_effects[receipt.operation]
    ):
        raise ContractError("host authority operation/effect mismatch")
    for value, name, length in (
        (receipt.correction_merge_sha, "correction merge", 40),
        (receipt.correction_tree_sha, "correction tree", 40),
        (receipt.current_main_sha, "current main", 40),
        (receipt.independent_acceptance_receipt_hash, "acceptance receipt", 64),
        (receipt.final_manager_sha256, "final manager", 64),
        (receipt.current_profile_hash, "current profile", 64),
        (receipt.desired_profile_hash, "desired profile", 64),
    ):
        _hash(value, name, length)
    if receipt.current_profile_hash != canonical_hash(CURRENT_PROFILE):
        raise ContractError("host authority current_profile_hash mismatch")
    if receipt.desired_profile_hash != canonical_hash(DESIRED_PROFILE):
        raise ContractError("host authority desired_profile_hash mismatch")
    _validate_revocation_fields(
        receipt.revocation_state,
        receipt.revoked_at,
        receipt.revocation_reason,
        label="host authority",
    )
    if receipt.revocation_state == "REVOKED" and not allow_revoked:
        raise ContractError("host authority is revoked")
    if request is not None:
        if (
            receipt.request_id != request.request_id
            or receipt.idempotency_fence != request.idempotency_fence
        ):
            raise ContractError("host authority request/fence mismatch")
        if (
            receipt.operation != request.operation
            or receipt.effect_class is not request.effect_class
        ):
            raise ContractError("host authority operation/effect mismatch")
        if receipt.current_profile_hash != canonical_hash(request.current):
            raise ContractError("host authority current profile mismatch")
        if receipt.desired_profile_hash != canonical_hash(request.desired):
            raise ContractError("host authority desired profile mismatch")
    if now is not None:
        validate_receipt_freshness(receipt, now=now)
    expected_hash = canonical_hash({
        key: value for key, value in _plain(receipt).items() if key != "receipt_hash"
    })
    if receipt.receipt_hash != expected_hash:
        raise ContractError("host authority receipt hash mismatch")
    return receipt


def _validate_revocation_fields(
    state: str,
    revoked_at: str | None,
    reason: str | None,
    *,
    label: str,
) -> None:
    if state == "NOT_REVOKED":
        if revoked_at is not None or reason is not None:
            raise ContractError(f"{label} revocation fields must be null")
        return
    if state != "REVOKED":
        raise ContractError(f"{label} revocation state invalid")
    if not isinstance(revoked_at, str) or not revoked_at:
        raise ContractError(f"{label} revoked_at missing")
    if not isinstance(reason, str) or not reason:
        raise ContractError(f"{label} revocation reason missing")


_BUNDLE_CHILDREN: tuple[tuple[str, EffectClass], ...] = (
    ("install-artifact", EffectClass.INSTALL_ARTIFACT),
    ("reload", EffectClass.GATEWAY_RELOAD),
    ("rollback", EffectClass.GATEWAY_ROLLBACK),
)


def validate_host_effect_authority_bundle(
    bundle: HostEffectAuthorityBundle | Mapping[str, Any],
    *,
    now: str | None = None,
    allow_revoked: bool = True,
) -> HostEffectAuthorityBundle:
    """Parse and validate the immutable three-child bundle as evidence.

    Parsing deliberately preserves a consistently revoked bundle/child so a
    reviewer can inspect the evidence.  It does not make that evidence
    selectable; callers must use the selector below before any effect.
    """
    if isinstance(bundle, Mapping):
        bundle = HostEffectAuthorityBundle.model_validate(bundle)
    if not isinstance(bundle, HostEffectAuthorityBundle):
        raise ContractError("host authority bundle must be typed")
    if (
        bundle.schema != HOST_AUTHORITY_BUNDLE_SCHEMA
        or type(bundle.bundle_version) is not int
        or bundle.bundle_version != 1
    ):
        raise ContractError("host authority bundle schema/version mismatch")
    if bundle.scope != HOST_AUTHORITY_BUNDLE_SCOPE:
        raise ContractError("host authority bundle scope mismatch")
    _id(bundle.bundle_id, "host authority bundle id")
    _hash(bundle.bundle_hash, "host authority bundle hash")
    exact = {
        "repository": REPOSITORY,
        "host_card_path": HOST_CARD_PATH,
        "host_card_id": HOST_CARD_ID,
        "host_card_sha256": HOST_CARD_SHA256,
        "source_base_merge": SOURCE_BASE_MERGE,
        "source_base_tree": SOURCE_BASE_TREE,
    }
    for name, expected in exact.items():
        if getattr(bundle, name) != expected:
            raise ContractError(f"host authority bundle {name} mismatch")
    for value, name, length in (
        (bundle.correction_merge_sha, "bundle correction merge", 40),
        (bundle.correction_tree_sha, "bundle correction tree", 40),
        (bundle.current_main_sha, "bundle current main", 40),
        (bundle.independent_acceptance_receipt_hash, "bundle acceptance receipt", 64),
        (bundle.final_manager_sha256, "bundle final manager", 64),
    ):
        _hash(value, name, length)
    _validate_revocation_fields(
        bundle.revocation_state,
        bundle.revoked_at,
        bundle.revocation_reason,
        label="host authority bundle",
    )
    if not isinstance(bundle.receipts, tuple) or len(bundle.receipts) != len(_BUNDLE_CHILDREN):
        raise ContractError("host authority bundle must contain exactly three receipts")
    seen_receipt_ids: set[str] = set()
    seen_request_ids: set[str] = set()
    seen_fences: set[str] = set()
    revoked_children = 0
    for index, (receipt, (operation, effect)) in enumerate(
        zip(bundle.receipts, _BUNDLE_CHILDREN, strict=True)
    ):
        if not isinstance(receipt, HostEffectAuthorityReceipt):
            raise ContractError("host authority bundle child must be typed")
        shared_provenance = {
            "repository": "repository",
            "host_card_path": "host_card_path",
            "host_card_id": "host_card_id",
            "host_card_sha256": "host_card_sha256",
            "source_base_merge": "source_base_merge",
            "source_base_tree": "source_base_tree",
            "correction_merge_sha": "correction_merge_sha",
            "correction_tree_sha": "correction_tree_sha",
            "independent_acceptance_receipt_hash": "independent_acceptance_receipt_hash",
            "final_manager_sha256": "final_manager_sha256",
            "current_main_sha": "current_main_sha",
        }
        for bundle_field, receipt_field in shared_provenance.items():
            if getattr(receipt, receipt_field) != getattr(bundle, bundle_field):
                raise ContractError(f"host authority bundle child {index} provenance mismatch")
        # Validate the full child after cross-binding every shared field, so a
        # rehashed child substitution is rejected at the bundle equality gate.
        validate_host_effect_authority(receipt, allow_revoked=allow_revoked)
        if receipt.operation != operation or receipt.effect_class is not effect:
            raise ContractError(f"host authority bundle child {index} operation mismatch")
        if receipt.receipt_id in seen_receipt_ids:
            raise ContractError("host authority bundle duplicate receipt id")
        if receipt.request_id in seen_request_ids:
            raise ContractError("host authority bundle duplicate request id")
        if receipt.idempotency_fence in seen_fences:
            raise ContractError("host authority bundle duplicate idempotency fence")
        seen_receipt_ids.add(receipt.receipt_id)
        seen_request_ids.add(receipt.request_id)
        seen_fences.add(receipt.idempotency_fence)
        if receipt.revocation_state == "REVOKED":
            if (
                receipt.revoked_at != bundle.revoked_at
                or receipt.revocation_reason != bundle.revocation_reason
            ):
                raise ContractError("host authority bundle revoked child fields mismatch")
            revoked_children += 1
        elif receipt.revoked_at is not None or receipt.revocation_reason is not None:
            raise ContractError("host authority bundle child revocation fields mismatch")
    if bundle.revocation_state == "NOT_REVOKED" and revoked_children:
        raise ContractError("active host authority bundle contains revoked child")
    if bundle.revocation_state == "REVOKED" and not revoked_children:
        raise ContractError("revoked host authority bundle has no revoked child")
    expected_hash = canonical_hash({
        key: value for key, value in _plain(bundle).items() if key != "bundle_hash"
    })
    if bundle.bundle_hash != expected_hash:
        raise ContractError("host authority bundle hash mismatch")
    if now is not None:
        _validate_bundle_freshness(bundle, now=now)
    return bundle


def _validate_bundle_freshness(bundle: HostEffectAuthorityBundle, *, now: str) -> None:
    def parse(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ContractError("host authority bundle timestamp malformed") from exc
        if parsed.tzinfo is None:
            raise ContractError("host authority bundle timestamp must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    issued, expires, observed = parse(bundle.issued_at), parse(bundle.expires_at), parse(now)
    if expires <= issued or issued > observed or expires <= observed:
        raise ContractError("host authority bundle stale")
    for receipt in bundle.receipts:
        validate_receipt_freshness(receipt, now=now)


def select_host_effect_authority_receipt(
    bundle: HostEffectAuthorityBundle | Mapping[str, Any],
    request: "GatewayDeploymentRequest | Mapping[str, Any]",
    *,
    now: str | None = None,
) -> HostEffectAuthorityReceipt:
    """Select exactly one active child equal to the request's receipt."""
    parsed = validate_host_effect_authority_bundle(bundle, now=None, allow_revoked=True)
    if (
        parsed.revocation_state != "NOT_REVOKED"
        or parsed.revoked_at is not None
        or parsed.revocation_reason is not None
    ):
        raise ContractError("host authority bundle is revoked")
    if isinstance(request, Mapping):
        request = GatewayDeploymentRequest.model_validate(request)
    if not isinstance(request, GatewayDeploymentRequest) or request.host_authority is None:
        raise ContractError("host authority request child required")
    if now is not None:
        _validate_bundle_freshness(parsed, now=now)
    selected = [
        child
        for child in parsed.receipts
        if child.receipt_id == request.host_authority.receipt_id
        and child.operation == request.host_authority.operation
        and child.effect_class is request.host_authority.effect_class
        and child.request_id == request.host_authority.request_id
        and child.idempotency_fence == request.host_authority.idempotency_fence
        and child == request.host_authority
    ]
    if len(selected) != 1:
        raise ContractError("host authority bundle child selection mismatch")
    selected_child = selected[0]
    if (
        selected_child.revocation_state != "NOT_REVOKED"
        or selected_child.revoked_at is not None
        or selected_child.revocation_reason is not None
    ):
        raise ContractError("selected host authority child is revoked")
    return selected_child


# Short names are kept for adapter/review tooling that uses the contract's
# parse/select vocabulary.
parse_host_effect_authority_bundle = validate_host_effect_authority_bundle
select_host_authority_receipt = select_host_effect_authority_receipt


def _validate_recovery_activation_lineage(receipt: RecoveryAuthorityReceipt) -> None:
    lineage = (
        receipt.owner_activation_id,
        receipt.owner_activation_sha256,
        receipt.source_thread,
    )
    target = (
        receipt.desired_commit,
        receipt.desired_tree,
        receipt.predecessor_commit,
        receipt.predecessor_tree,
    )
    historical_lineage = (
        OWNER_ACTIVATION_ID,
        OWNER_ACTIVATION_SHA256,
        OWNER_SOURCE_THREAD,
    )
    task002_lineage = (
        TASK002_RECOVERY_ACTIVATION_ID,
        TASK002_RECOVERY_ACTIVATION_SHA256,
        TASK002_RECOVERY_SOURCE_COMMENT,
    )
    task002_target = (
        TASK002_RECOVERY_DESIRED_COMMIT,
        TASK002_RECOVERY_DESIRED_TREE,
        TASK002_RECOVERY_PREDECESSOR_COMMIT,
        TASK002_RECOVERY_PREDECESSOR_TREE,
    )
    if lineage == historical_lineage:
        if target == task002_target:
            raise ContractError(
                "R1 historical activation cannot authorize TASK-002 recovery target"
            )
        return
    if lineage == task002_lineage:
        if target != task002_target:
            raise ContractError("R1 TASK-002 recovery activation target mismatch")
        return
    raise ContractError("R1 recovery authority activation lineage mismatch")


def validate_recovery_authority(
    receipt: RecoveryAuthorityReceipt,
    *,
    request: GatewayRecoveryRequest | None = None,
    now: str | None = None,
) -> RecoveryAuthorityReceipt:
    if (
        not isinstance(receipt, RecoveryAuthorityReceipt)
        or receipt.schema != RecoveryAuthorityReceipt.SCHEMA
    ):
        raise ContractError("R1 recovery authority schema mismatch")
    if (
        type(receipt.receipt_version) is not int
        or receipt.receipt_version != 1
        or receipt.operation != "gateway-recover"
    ):
        raise ContractError("R1 recovery operation mismatch")
    if receipt.effect_class is not EffectClass.GATEWAY_DURABLE_RECOVERY:
        raise ContractError("R1 recovery effect mismatch")
    if receipt.card_sha256 != RECOVERY_CARD_SHA256:
        raise ContractError("R1 recovery Card mismatch")
    if (
        receipt.source_base_merge != SOURCE_BASE_MERGE
        or receipt.source_base_tree != SOURCE_BASE_TREE
    ):
        raise ContractError("R1 recovery source binding mismatch")
    if (
        receipt.service_label != LABEL
        or receipt.plist_path != PLIST
        or receipt.endpoint != ENDPOINT
    ):
        raise ContractError("R1 recovery fixed service mismatch")
    exact = {
        "issuer_id": "owner-james",
        "coordinator_id": "coordinator-codex",
        "authorized_actor_id": "coordinator-codex",
        "standing_grant_id": STANDING_GRANT_ID,
        "standing_grant_receipt_sha256": STANDING_GRANT_RECEIPT_SHA256,
        "repository": REPOSITORY,
        "host_card_path": RECOVERY_CARD_PATH,
    }
    for name, expected in exact.items():
        if getattr(receipt, name) != expected:
            raise ContractError(f"R1 recovery authority {name} mismatch")
    _validate_recovery_activation_lineage(receipt)
    for value, name, length in (
        (receipt.receipt_hash, "recovery receipt", 64),
        (receipt.current_main_sha, "recovery issuance parent", 40),
        (receipt.accepted_source_merge, "accepted source merge", 40),
        (receipt.accepted_source_tree, "accepted source tree", 40),
        (receipt.authority_floor_commit, "authority floor commit", 40),
        (receipt.authority_floor_tree, "authority floor tree", 40),
        (receipt.desired_commit, "desired commit", 40),
        (receipt.desired_tree, "desired tree", 40),
        (receipt.predecessor_commit, "predecessor commit", 40),
        (receipt.predecessor_tree, "predecessor tree", 40),
        (receipt.desired_manifest_sha256, "desired manifest", 64),
        (receipt.predecessor_manifest_sha256, "predecessor manifest", 64),
        (receipt.final_manager_sha256, "final manager", 64),
        (receipt.independent_acceptance_receipt_hash, "acceptance receipt", 64),
    ):
        _hash(value, name, length)
    _id(receipt.receipt_id, "recovery receipt id")
    _id(receipt.request_id, "recovery request id")
    _id(receipt.idempotency_fence, "recovery fence")
    expected_hash = canonical_hash({
        key: value for key, value in receipt.model_dump().items() if key != "receipt_hash"
    })
    if receipt.receipt_hash != expected_hash:
        raise ContractError("R1 recovery receipt hash mismatch")
    _validate_revocation_fields(
        receipt.revocation_state,
        receipt.revoked_at,
        receipt.revocation_reason,
        label="R1 recovery authority",
    )
    if receipt.revocation_state != "NOT_REVOKED":
        raise ContractError("R1 recovery authority revoked")
    source_set = validate_recovery_source_set(receipt.source_set)
    if (
        receipt.current_main_sha != receipt.authority_floor_commit
        or receipt.authority_floor_commit != receipt.accepted_source_merge
        or receipt.authority_floor_tree != receipt.accepted_source_tree
        or source_set.accepted_commit != receipt.accepted_source_merge
        or source_set.accepted_tree != receipt.accepted_source_tree
        or source_set.desired_commit != receipt.desired_commit
        or source_set.desired_tree != receipt.desired_tree
        or source_set.predecessor_commit != receipt.predecessor_commit
        or source_set.predecessor_tree != receipt.predecessor_tree
    ):
        raise ContractError("R1 recovery semantic source binding mismatch")
    desired = derive_deployment_manifest(source_set, role="desired")
    predecessor = derive_deployment_manifest(source_set, role="predecessor")
    if (
        receipt.desired_manifest != desired
        or receipt.predecessor_manifest != predecessor
        or receipt.desired_manifest_id != desired.deployment_id
        or receipt.desired_manifest_sha256 != desired.manifest_sha256
        or receipt.predecessor_manifest_id != predecessor.deployment_id
        or receipt.predecessor_manifest_sha256 != predecessor.manifest_sha256
    ):
        raise ContractError("R1 recovery manager-derived manifest mismatch")
    if request is not None and (
        request.recovery_authority_id != receipt.receipt_id
        or request.recovery_authority_hash != receipt.receipt_hash
        or request.operation != receipt.operation
        or request.request_id != receipt.request_id
        or request.idempotency_fence != receipt.idempotency_fence
        or request.desired_manifest_id != receipt.desired_manifest_id
        or request.predecessor_manifest_id != receipt.predecessor_manifest_id
        or request.desired_manifest_hash != receipt.desired_manifest_sha256
        or request.predecessor_manifest_hash != receipt.predecessor_manifest_sha256
    ):
        raise ContractError("R1 recovery request binding mismatch")
    if now is not None:
        validate_receipt_freshness(receipt, now=now)
    return receipt


def validate_receipt_freshness(
    receipt: HostEffectAuthorityReceipt | RecoveryAuthorityReceipt, *, now: str
) -> HostEffectAuthorityReceipt | RecoveryAuthorityReceipt:
    if not isinstance(receipt, (HostEffectAuthorityReceipt, RecoveryAuthorityReceipt)):
        raise ContractError("authority freshness receipt must be typed")

    def parse(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ContractError("host authority timestamp malformed") from exc
        if parsed.tzinfo is None:
            raise ContractError("host authority timestamp must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    issued, expires, observed = parse(receipt.issued_at), parse(receipt.expires_at), parse(now)
    if expires <= issued or issued > observed or expires <= observed:
        raise ContractError("host authority receipt stale")
    return receipt


# Stable public names for adapters and review tooling.
HostAuthorityReceipt = HostEffectAuthorityReceipt
validate_host_authority = validate_host_effect_authority


def validate_request(
    request: GatewayDeploymentRequest | Mapping[str, Any],
) -> GatewayDeploymentRequest:
    if isinstance(request, Mapping):
        request = GatewayDeploymentRequest.model_validate(request)
    if not isinstance(request, GatewayDeploymentRequest):
        raise ContractError("request must be typed")
    if request.schema != SCHEMA:
        raise ContractError("schema mismatch")
    for value, name in (
        (request.request_id, "request id"),
        (request.idempotency_fence, "idempotency fence"),
        (request.operation, "operation"),
    ):
        _id(value, name)
    operations = {
        "preflight": EffectClass.PREFLIGHT,
        "gateway-preflight": EffectClass.PREFLIGHT,
        "status": EffectClass.STATUS,
        "gateway-status": EffectClass.STATUS,
        "install-artifact": EffectClass.INSTALL_ARTIFACT,
        "install_artifact": EffectClass.INSTALL_ARTIFACT,
        "install": EffectClass.INSTALL_ARTIFACT,
        "reload": EffectClass.GATEWAY_RELOAD,
        "gateway-reload": EffectClass.GATEWAY_RELOAD,
        "rollback": EffectClass.GATEWAY_ROLLBACK,
        "gateway-rollback": EffectClass.GATEWAY_ROLLBACK,
    }
    if (
        request.operation not in operations
        or request.effect_class is not operations[request.operation]
    ):
        raise ContractError("operation/effect substitution")
    validate_profile(request.current, expected=CURRENT_PROFILE)
    validate_profile(request.desired, expected=DESIRED_PROFILE)
    validate_desired_profile(request.current, request.desired)
    if request.operation == "gateway-recover":
        raise ContractError("R1 recovery requires GatewayRecoveryRequest")
    validate_current_identity(request.current_identity, request.current)
    validate_source_authority(request.authority, request_id=request.request_id)
    if request.host_authority is None:
        raise ContractError("host-effect authority receipt required")
    validate_host_effect_authority(request.host_authority, request=request)
    _validate_rollback(request.rollback)
    if (
        request.quiescence.disposition not in {"drained", "held", "reconciled"}
        or not request.quiescence.lifecycle_state
        or not request.quiescence.assist_state
    ):
        raise ContractError("quiescence required")
    if not request.quiescence.evidence_sha256 or not request.quiescence.reacquisition_receipt:
        raise ContractError("quiescence evidence missing")
    _hash(request.quiescence.evidence_sha256, "quiescence evidence")
    if request.quiescence.pending_actions and request.quiescence.disposition != "reconciled":
        raise ContractError("pending actions require reconciliation")
    validate_postflight_identity(request.postflight, request.desired)
    if request.stable_artifact is not None:
        artifact = request.stable_artifact
        if not isinstance(artifact, StableArtifactIdentity):
            raise ContractError("artifact identity must be typed")
        if request.host_authority is None:
            raise ContractError("artifact authority receipt required")
        if (
            request.host_authority.final_manager_sha256 != artifact.source_blob_sha256
            or request.host_authority.final_manager_sha256 != artifact.artifact_sha256
        ):
            raise ContractError("manager artifact triple mismatch")
        for value, name in (
            (artifact.source_root, "artifact source root"),
            (artifact.source_path, "artifact source path"),
        ):
            _absolute(value, name)
        for value, name in (
            (artifact.source_head, "artifact head"),
            (artifact.source_tree, "artifact tree"),
            (artifact.source_blob_sha256, "artifact blob"),
            (artifact.artifact_sha256, "artifact hash"),
        ):
            _hash(value, name, 40 if name.endswith(("head", "tree")) else 64)
        if (
            not isinstance(artifact.uid, int)
            or isinstance(artifact.uid, bool)
            or artifact.uid < 0
            or not isinstance(artifact.mode, int)
            or isinstance(artifact.mode, bool)
            or artifact.mode != 0o700
        ):
            raise ContractError("installed manager ownership/mode invalid")
        try:
            Path(artifact.source_path).relative_to(Path(artifact.source_root))
        except ValueError as exc:
            raise ContractError("artifact source path outside source root") from exc
        if (
            artifact.request_id != request.request_id
            or artifact.card_id != "TASK-526-A"
            or artifact.authority_receipt_id != request.host_authority.receipt_id
            or not artifact.install_fence
            or not artifact.predecessor_sha256
            or not artifact.rollback_receipt
        ):
            raise ContractError("artifact request substitution")
    payload = {
        key: _plain(value)
        for key, value in _plain(request).items()
        if key not in {"request_hash", "schema"}
    }
    # Preserve the historical request hash domain for pre-R1 operations; the
    # new manifest/readiness fields participate only when explicitly present.
    expected = canonical_hash(payload)
    legacy_payload = {
        key: _plain(value)
        for key, value in _plain(request).items()
        if key not in {"request_hash", "schema"}
    }
    if request.request_hash not in {expected, canonical_hash(legacy_payload)}:
        raise ContractError("request hash mismatch")
    return request


def validate_authority_freshness(receipt: AuthorityReceipt, *, now: str) -> AuthorityReceipt:
    """Validate an authority receipt against a caller-supplied timestamp."""
    if not isinstance(receipt, AuthorityReceipt) or not receipt.issued_at or not receipt.expires_at:
        raise ContractError("authority freshness evidence missing")

    def parse(value: str) -> datetime:
        if (
            not isinstance(value, str)
            or not value
            or value.endswith("Z") is False
            and "+" not in value
            and "-" not in value[10:]
        ):
            raise ContractError("authority timestamp malformed")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError("authority timestamp malformed") from exc
        if parsed.tzinfo is None:
            raise ContractError("authority timestamp must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    issued, expires, observed = parse(receipt.issued_at), parse(receipt.expires_at), parse(now)
    if expires <= issued or issued > observed or expires <= observed:
        raise ContractError("authority receipt stale")
    return receipt


def validate_current_identity(
    identity: IdentityEvidence, profile: DeploymentProfile
) -> IdentityEvidence:
    """Reject supplied identity fields that disagree with the bound profile."""
    validate_profile(profile)
    if not isinstance(identity, IdentityEvidence):
        raise ContractError("current identity must be typed")
    expected = {
        "label": LABEL,
        "plist_sha256": None,
        "plist_bytes_sha256": None,
        "server_instance": None,
        "root": profile.git.root,
        "head": profile.git.head,
        "tree": profile.git.tree,
        "source_sha256": None,
        "tool_manifest_sha256": None,
        "schema_sha256": None,
        "permission_sha256": None,
        "action": GATEWAY_ACTION,
        "task_id": GATEWAY_TASK_ID,
        "lifecycle": GATEWAY_LIFECYCLE_REVISION,
        "endpoint": ENDPOINT,
    }
    for key, value in expected.items():
        observed = getattr(identity, key)
        if value is None and (not isinstance(observed, str) or not observed):
            raise ContractError(f"current identity missing: {key}")
        if key.endswith("_sha256") and observed:
            _hash(observed, key)
        if value is not None and observed != value:
            raise ContractError(f"current identity mismatch: {key}")
    if not isinstance(identity.pid, int) or isinstance(identity.pid, bool) or identity.pid <= 0:
        raise ContractError("invalid current PID")
    if not identity.loaded or not identity.client_bound:
        raise ContractError("current service/client identity not verified")
    if identity.plist_sha256 != identity.plist_bytes_sha256:
        raise ContractError("current plist hashes disagree")
    return identity


def validate_postflight_identity(
    identity: PostflightIdentity, profile: DeploymentProfile
) -> PostflightIdentity:
    if not isinstance(identity, PostflightIdentity):
        raise ContractError("postflight identity must be typed")
    validate_profile(profile)
    if (
        not identity.server_instance
        or not identity.root
        or not identity.action
        or not identity.task_id
        or not identity.lifecycle
    ):
        raise ContractError("postflight identity incomplete")
    if (
        identity.root != profile.git.root
        or identity.head != profile.git.head
        or identity.tree != profile.git.tree
    ):
        raise ContractError("postflight deployment identity mismatch")
    for value, name in ((identity.head, "postflight HEAD"), (identity.tree, "postflight tree")):
        _hash(value, name, 40)
    for value, name in (
        (identity.tool_manifest_sha256, "postflight manifest"),
        (identity.schema_sha256, "postflight schema"),
        (identity.permission_sha256, "postflight permission"),
    ):
        _hash(value, name)
    if (
        identity.action != GATEWAY_ACTION
        or identity.task_id != GATEWAY_TASK_ID
        or identity.lifecycle != GATEWAY_LIFECYCLE_REVISION
    ):
        raise ContractError("postflight action/task/lifecycle mismatch")
    if not identity.client_bound or not identity.token_bound:
        raise ContractError("authenticated client binding missing")
    required = tuple(identity.required_actions)
    observed = tuple(identity.observed_actions)
    if (
        not required
        or not observed
        or any(not isinstance(item, str) or not item for item in required + observed)
    ):
        raise ContractError("postflight action manifest missing")
    if not set(required).issubset(set(observed)):
        raise ContractError("postflight required action missing")
    return identity


def validate_rollback_capture(capture: RollbackCapture) -> RollbackCapture:
    if not isinstance(capture, RollbackCapture):
        raise ContractError("rollback capture must be typed")
    _validate_rollback(capture)
    return capture


CURRENT_PROFILE = DeploymentProfile(
    GitIdentity(
        "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "67521fe91e990f4e140642984c743dd50a408e84",
        "f6d6c2bf0912ff4a63d3c10a089910f95eab3c12",
        clean=False,
    ),
    entrypoint_sha256="8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
    trust_class="ROLLBACK_ONLY_OBSERVED_CURRENT",
)
DESIRED_PROFILE = DeploymentProfile(
    GitIdentity(
        "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-935a9dd3",
        "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-935a9dd3",
        "7ad264e1c12a2b4d3896b4cdeec68688acf034f7",
        "b9057f8ef736fb6d3cd30da983f33f5f61fb86e9",
    ),
    entrypoint_sha256="8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
    trust_class="EXPLICIT_DESIRED_CANARY",
)
