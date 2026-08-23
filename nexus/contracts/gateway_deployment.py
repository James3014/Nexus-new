"""Pure, fail-closed bindings for the Gateway deployment owner.

The module deliberately has no filesystem, process, network, or clock access.
It describes the only identities that the durable adapter may act on and keeps
the state machine/hash rules deterministic.  The adapter in
``scripts/ops/mcp_gateway_durable.py`` is the sole effect owner.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
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
INTERPRETER_TARGET = "/Users/jameschen/.local/share/uv/python/cpython-3.14.0-macos-aarch64-none/bin/python3.14"
INTERPRETER_SHA256 = "c89af0b037c601180919ca5fd8a936bd2568cbb4976f91a208c10f54c17a1b78"
ENTRYPOINT = "scripts/ops/nexus_mcp_gateway_http.py"
SCHEMA = "nexus.gateway.deployment.v1"


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
            item.name for item in fields(cls)
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
        return cls(**converted)  # type: ignore[arg-type]

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


@dataclass(frozen=True)
class QuiescenceEvidence(StrictRecord):
    disposition: str
    lifecycle_state: str = ""
    assist_state: str = ""
    evidence_sha256: str = ""
    pending_actions: tuple[str, ...] = ()
    reacquisition_receipt: str = ""


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
    required_actions: tuple[str, ...] = ()
    observed_actions: tuple[str, ...] = ()
    token_bound: bool = False


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
    postflight: Mapping[str, str]
    effect_class: EffectClass
    request_hash: str = ""
    schema: str = SCHEMA
    stable_artifact: StableArtifactIdentity | None = None

    _converters: ClassVar[Mapping[str, Any]] = {
        "authority": AuthorityReceipt.model_validate,
        "current": DeploymentProfile.model_validate,
        "desired": DeploymentProfile.model_validate,
        "current_identity": IdentityEvidence.model_validate,
        "rollback": RollbackCapture.model_validate,
        "quiescence": QuiescenceEvidence.model_validate,
        "effect_class": EffectClass,
        "stable_artifact": lambda value: None if value is None else StableArtifactIdentity.model_validate(value),
    }


def validate_repository(profile: RepositoryProfile) -> RepositoryProfile:
    if not isinstance(profile, RepositoryProfile):
        raise ContractError("repository profile must be typed")
    if profile.repository != REPOSITORY or profile.remote != REMOTE or profile.label != LABEL:
        raise ContractError("repository/service identity mismatch")
    for value, name in ((profile.plist, "plist"), (profile.stdout, "stdout"), (profile.stderr, "stderr")):
        _absolute(value, name)
    if profile.endpoint != ENDPOINT:
        raise ContractError("endpoint mismatch")
    return profile


def validate_profile(profile: DeploymentProfile, *, expected: DeploymentProfile | None = None) -> DeploymentProfile:
    if not isinstance(profile, DeploymentProfile):
        raise ContractError("profile must be typed")
    validate_repository(profile.repository)
    g = profile.git
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
    if profile.interpreter.path != INTERPRETER or profile.interpreter.resolved_path != INTERPRETER_TARGET:
        raise ContractError("interpreter mismatch")
    if not isinstance(profile.interpreter.uid, int) or not isinstance(profile.interpreter.gid, int):
        raise ContractError("interpreter ownership mismatch")
    if profile.trust_class == "" or not isinstance(profile.trust_class, str):
        raise ContractError("trust class missing")
    known_profiles = globals().get("CURRENT_PROFILE"), globals().get("DESIRED_PROFILE")
    if all(item is not None for item in known_profiles):
        identity = (g.root, g.head, g.tree)
        if identity not in {(item.git.root, item.git.head, item.git.tree) for item in known_profiles if item is not None}:
            raise ContractError("profile is not one of the frozen deployment identities")
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


def validate_desired_profile(current: DeploymentProfile, desired: DeploymentProfile) -> DeploymentProfile:
    validate_profile(current)
    validate_profile(desired)
    if current.git.head == desired.git.head and current.git.tree == desired.git.tree:
        raise ContractError("desired profile must be an explicit different target")
    return desired


_EDGES: dict[DeploymentState, set[DeploymentState]] = {
    DeploymentState.REQUESTED: {DeploymentState.PREFLIGHTED, DeploymentState.BLOCKED},
    DeploymentState.PREFLIGHTED: {DeploymentState.STARTED, DeploymentState.BLOCKED},
    DeploymentState.STARTED: {DeploymentState.SERVICE_OBSERVED, DeploymentState.UNCERTAIN_EFFECT, DeploymentState.BLOCKED},
    DeploymentState.SERVICE_OBSERVED: {DeploymentState.IDENTITY_VERIFIED, DeploymentState.UNCERTAIN_EFFECT},
    DeploymentState.IDENTITY_VERIFIED: {DeploymentState.CLIENT_BOUND, DeploymentState.UNCERTAIN_EFFECT},
    DeploymentState.CLIENT_BOUND: {DeploymentState.VERIFIED, DeploymentState.UNCERTAIN_EFFECT},
    DeploymentState.UNCERTAIN_EFFECT: {DeploymentState.ROLLBACK_STARTED, DeploymentState.PREFLIGHTED, DeploymentState.BLOCKED},
    DeploymentState.ROLLBACK_STARTED: {DeploymentState.ROLLED_BACK, DeploymentState.UNCERTAIN_EFFECT, DeploymentState.BLOCKED},
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
    for value, name in ((capture.plist_sha256, "rollback plist"), (capture.plist_bytes_sha256, "rollback bytes"), (capture.artifact_sha256, "rollback artifact"), (capture.source_sha256, "rollback source")):
        _hash(value, name)
    try:
        payload = bytes.fromhex(capture.plist_bytes_hex)
    except (TypeError, ValueError) as exc:
        raise ContractError("rollback bytes are not hex") from exc
    payload_hash = hashlib.sha256(payload).hexdigest()
    if payload_hash != capture.plist_bytes_sha256 or payload_hash != capture.plist_sha256:
        raise ContractError("rollback bytes hash mismatch")
    if capture.label != LABEL or capture.interpreter_sha256 != INTERPRETER_SHA256:
        raise ContractError("rollback fixed identity mismatch")
    if capture.root:
        _absolute(capture.root, "rollback root")


def validate_request(request: GatewayDeploymentRequest | Mapping[str, Any]) -> GatewayDeploymentRequest:
    if isinstance(request, Mapping):
        request = GatewayDeploymentRequest.model_validate(request)
    if not isinstance(request, GatewayDeploymentRequest):
        raise ContractError("request must be typed")
    if request.schema != SCHEMA:
        raise ContractError("schema mismatch")
    for value, name in ((request.request_id, "request id"), (request.idempotency_fence, "idempotency fence"), (request.operation, "operation")):
        _id(value, name)
    operations = {
        "preflight": EffectClass.PREFLIGHT,
        "gateway-preflight": EffectClass.PREFLIGHT,
        "status": EffectClass.STATUS,
        "gateway-status": EffectClass.STATUS,
        "install-artifact": EffectClass.INSTALL_ARTIFACT,
        "install_artifact": EffectClass.INSTALL_ARTIFACT,
        "reload": EffectClass.GATEWAY_RELOAD,
        "gateway-reload": EffectClass.GATEWAY_RELOAD,
        "rollback": EffectClass.GATEWAY_ROLLBACK,
        "gateway-rollback": EffectClass.GATEWAY_ROLLBACK,
    }
    if request.operation not in operations or request.effect_class is not operations[request.operation]:
        raise ContractError("operation/effect substitution")
    validate_profile(request.current)
    validate_profile(request.desired)
    validate_desired_profile(request.current, request.desired)
    validate_current_identity(request.current_identity, request.current)
    if request.authority.repository != REPOSITORY or request.authority.request_id not in ("", request.request_id):
        raise ContractError("authority mismatch")
    if request.authority.action != "gateway-rebind" or not request.authority.scope.endswith("SOURCE_CANDIDATE_ONLY"):
        raise ContractError("authority scope mismatch")
    _validate_rollback(request.rollback)
    if request.quiescence.disposition not in {"drained", "held", "reconciled"}:
        raise ContractError("quiescence required")
    if request.quiescence.pending_actions and request.quiescence.disposition != "reconciled":
        raise ContractError("pending actions require reconciliation")
    allowed_postflight = {
        "server_instance", "root", "head", "tree", "tool_manifest_sha256",
        "schema_sha256", "permission_sha256", "action", "task_id", "lifecycle",
        "required_actions", "client_bound", "token_bound",
    }
    if not isinstance(request.postflight, Mapping) or not request.postflight or set(request.postflight) - allowed_postflight or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in request.postflight.items()):
        raise ContractError("postflight identities missing")
    if request.stable_artifact is not None:
        artifact = request.stable_artifact
        for value, name in ((artifact.source_root, "artifact source root"), (artifact.source_path, "artifact source path")):
            _absolute(value, name)
        for value, name in ((artifact.source_head, "artifact head"), (artifact.source_tree, "artifact tree"), (artifact.source_blob_sha256, "artifact blob"), (artifact.artifact_sha256, "artifact hash")):
            _hash(value, name, 40 if name.endswith(("head", "tree")) else 64)
        if artifact.uid < 0 or artifact.mode & ~0o777:
            raise ContractError("artifact ownership/mode invalid")
        if artifact.request_id not in ("", request.request_id):
            raise ContractError("artifact request substitution")
    payload = {key: _plain(value) for key, value in _plain(request).items() if key not in {"request_hash", "schema"}}
    expected = canonical_hash(payload)
    # The first admitted worker predates the optional stable-artifact field and
    # calculated its fence from the six required request fields.  Accept that
    # exact legacy encoding only when the optional field is absent (never when
    # a real artifact is supplied).
    legacy_expected = canonical_hash({key: value for key, value in payload.items() if key != "stable_artifact"})
    if request.request_hash not in {expected, legacy_expected}:
        raise ContractError("request hash mismatch")
    return request


def validate_authority_freshness(receipt: AuthorityReceipt, *, now: str) -> AuthorityReceipt:
    """Validate an authority receipt against a caller-supplied timestamp."""
    if not isinstance(receipt, AuthorityReceipt) or not receipt.issued_at or not receipt.expires_at:
        raise ContractError("authority freshness evidence missing")
    if receipt.issued_at > now or receipt.expires_at <= now:
        raise ContractError("authority receipt stale")
    return receipt


def validate_current_identity(identity: IdentityEvidence, profile: DeploymentProfile) -> IdentityEvidence:
    """Reject supplied identity fields that disagree with the bound profile."""
    validate_profile(profile)
    expected = {
        "label": LABEL,
        "root": profile.git.root,
        "head": profile.git.head,
        "tree": profile.git.tree,
        "endpoint": ENDPOINT,
    }
    for key, value in expected.items():
        observed = getattr(identity, key)
        if observed not in ("", None) and observed != value:
            raise ContractError(f"current identity mismatch: {key}")
    if identity.pid is not None and identity.pid <= 0:
        raise ContractError("invalid current PID")
    return identity


def validate_rollback_capture(capture: RollbackCapture) -> RollbackCapture:
    if not isinstance(capture, RollbackCapture):
        raise ContractError("rollback capture must be typed")
    _validate_rollback(capture)
    return capture


CURRENT_PROFILE = DeploymentProfile(
    GitIdentity("/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe", "67521fe91e990f4e140642984c743dd50a408e84", "f6d6c2bf0912ff4a63d3c10a089910f95eab3c12"),
    entrypoint_sha256="8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
    trust_class="ROLLBACK_ONLY_OBSERVED_CURRENT",
)
DESIRED_PROFILE = DeploymentProfile(
    GitIdentity("/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-935a9dd3", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-935a9dd3", "7ad264e1c12a2b4d3896b4cdeec68688acf034f7", "b9057f8ef736fb6d3cd30da983f33f5f61fb86e9"),
    entrypoint_sha256="8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
    trust_class="EXPLICIT_DESIRED_CANARY",
)
