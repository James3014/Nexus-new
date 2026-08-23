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
INTERPRETER = "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python"
INTERPRETER_TARGET = (
    "/Users/jameschen/.local/share/uv/python/cpython-3.14.0-macos-aarch64-none/bin/python3.14"
)
INTERPRETER_SHA256 = "c89af0b037c601180919ca5fd8a936bd2568cbb4976f91a208c10f54c17a1b78"
ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
SCHEMA = "nexus.gateway.deployment.v1"
HOST_AUTHORITY_SCHEMA = "nexus.gateway.host_effect_authority.v1"
HOST_AUTHORITY_SCOPE = "NEXUS_GATEWAY_REBIND_HOST_EFFECT_ONLY"
HOST_CARD_ID = "TASK-526-HOST-1"
HOST_CARD_PATH = (
    "tasks/github-issue-526-host-authority-and-canary-20260823/01-gateway-host-local-canary.md"
)
HOST_CARD_SHA256 = "fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f"
OWNER_ACTIVATION_ID = "OWNER_ISSUE526_CONTINUE_20260823"
OWNER_ACTIVATION_SHA256 = "f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322"
OWNER_SOURCE_THREAD = "01a02a17-691c-7a20-ad0f-9166456416dc"
STANDING_GRANT_ID = "OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW"
STANDING_GRANT_RECEIPT_SHA256 = "3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5"
SOURCE_BASE_MERGE = "ac4a9ab1e0180170ca062cdc81f2142bca8bd80f"
SOURCE_BASE_TREE = "db329f4931b55b74f1e1f9fe61f7edf4ca8422bc"


class ContractError(ValueError):
    """Invalid, stale, substituted, or otherwise untrusted contract data."""


class DeploymentState(StrEnum):
    REQUESTED = "REQUESTED"
    PREFLIGHTED = "PREFLIGHTED"
    STARTED = "STARTED"
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


class ResultClass(StrEnum):
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"
    UNCERTAIN_EFFECT = "UNCERTAIN_EFFECT"
    ROLLED_BACK = "ROLLED_BACK"


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
        numeric_fields = {"uid", "gid", "pid", "sequence"} | (
            {"mode"} if type(value).__name__ == "StableArtifactIdentity" else set()
        )
        if (
            item.name in numeric_fields
            and raw is not None
            and (not isinstance(raw, int) or isinstance(raw, bool))
        ):
            raise ContractError(f"{type(value).__name__}.{item.name} type mismatch")
        if item.name in {"clean", "loaded", "client_bound", "token_bound"} and not isinstance(
            raw, bool
        ):
            raise ContractError(f"{type(value).__name__}.{item.name} type mismatch")
        if item.name in {
            "required_actions",
            "observed_actions",
            "pending_actions",
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
    if g.root != g.toplevel or g.remote != REMOTE or g.clean is not True:
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
    if desired.git.root == current.git.root and desired.git.head != current.git.head:
        return False
    return current == desired


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
    DeploymentState.PREFLIGHTED: {DeploymentState.STARTED, DeploymentState.BLOCKED},
    DeploymentState.STARTED: {
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
        DeploymentState.ROLLBACK_STARTED,
        DeploymentState.PREFLIGHTED,
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
    if (
        not isinstance(args, list)
        or len(args) != 2
        or args[0] != INTERPRETER
        or not str(args[1]).endswith("/" + ENTRYPOINT)
    ):
        raise ContractError("rollback program arguments mismatch")
    if parsed.get("WorkingDirectory") != CURRENT_PROFILE.git.root:
        raise ContractError("rollback working directory mismatch")
    if parsed.get("StandardOutPath") != STDOUT or parsed.get("StandardErrorPath") != STDERR:
        raise ContractError("rollback log identity mismatch")
    env = parsed.get("EnvironmentVariables")
    if env != {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}:
        raise ContractError("rollback environment mismatch")
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
) -> HostEffectAuthorityReceipt:
    """Validate the complete host-effect receipt without reading the host store."""
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
        "revocation_state": "NOT_REVOKED",
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
    if receipt.revoked_at is not None or receipt.revocation_reason is not None:
        raise ContractError("host authority revocation fields must be null")
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


def validate_receipt_freshness(
    receipt: HostEffectAuthorityReceipt, *, now: str
) -> HostEffectAuthorityReceipt:
    if not isinstance(receipt, HostEffectAuthorityReceipt):
        raise ContractError("host authority freshness receipt must be typed")

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
    expected = canonical_hash(payload)
    if request.request_hash != expected:
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
        "action": "gateway-rebind",
        "task_id": "TASK-526-A",
        "lifecycle": None,
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
        identity.action != "gateway-rebind"
        or identity.task_id != "TASK-526-A"
        or identity.lifecycle not in {"QUIESCENT", "READY", "ACTIVE"}
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
