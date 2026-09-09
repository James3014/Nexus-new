import hashlib
import importlib
import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

_FEATURE_INTENT_TOKENS = frozenset({"build", "create", "add", "implement", "feature"})
_FEATURE_INTENT_TOKEN_RE = re.compile(r"(?<!\w)([A-Za-z]+)(?!\w)")
_DAYSHIFT_CONTEXT_TOKEN = object()


def infer_task_kind(task_text: str) -> str:
    """Classify explicit feature intent without matching identifier fragments.

    Task text commonly names repair symbols such as ``add_one`` or
    ``rebuild_index``.  Those names must remain repair work; only standalone
    English intent words may enter the feature branch.  The planner remains
    the authority for the resulting execution decision.
    """
    text = str(task_text or "").strip().lower()
    if any(match.group(1) in _FEATURE_INTENT_TOKENS for match in _FEATURE_INTENT_TOKEN_RE.finditer(text)):
        return "feature"
    if any(keyword in text for keyword in ("新增", "建立", "實作", "開發")):
        return "feature"
    return "bug"


def build_engine(project_root: Path, **config_overrides):
    from nexus.engine.config import EngineConfig
    from nexus.engine.coordinator import NexusEngine

    return NexusEngine(EngineConfig(project_root=project_root, **config_overrides))


def build_command_service(project_root: Path):
    NexusCommandService = importlib.import_module("nexus." + "app.command_service").NexusCommandService
    return NexusCommandService(build_engine(project_root))


class LegacyTaskServiceAdapter:
    def __init__(self, command_service):
        self._command_service = command_service

    def execute_bug(self, task: str, delivery_mode: str = "standard", bug_id: str | None = None, **kwargs):
        TaskRequest = importlib.import_module("nexus." + "app.command_service").TaskRequest

        request = TaskRequest(
            task=task,
            task_id=bug_id,
            plan_only=bool(kwargs.get("plan_only", False)),
            delivery_mode=delivery_mode,
            verify_commands=kwargs.get("verify_commands"),
            artifact_paths=kwargs.get("artifact_paths"),
        )
        return self._command_service.execute_bug(request)

    def execute_feature(self, task: str, domain: str | None = None, delivery_mode: str = "standard", **kwargs):
        TaskRequest = importlib.import_module("nexus." + "app.command_service").TaskRequest

        request = TaskRequest(
            task=task,
            domain=domain,
            plan_only=bool(kwargs.get("plan_only", False)),
            delivery_mode=delivery_mode,
            verify_commands=kwargs.get("verify_commands"),
            artifact_paths=kwargs.get("artifact_paths"),
        )
        return self._command_service.execute_feature(request)


def build_legacy_cli_service(project_root: Path):
    """Build the compatibility-only legacy command surface.

    The daily ``nexus run`` product entry must not call this adapter.
    """
    return LegacyTaskServiceAdapter(build_command_service(project_root))


def execute_single_task_via_service(
    task_text: str,
    project_root: Path,
    execution_context: dict | None = None,
) -> bool:
    """Run one CLI task through CommandService with optional task-level context.

    ``execution_context`` is the sole task-scoped carrier for Local Assist mode
    and identity fields. Environment variables must not replace this context.
    """
    TaskRequest = importlib.import_module("nexus." + "app.command_service").TaskRequest

    service = build_command_service(project_root)
    context = dict(execution_context or {})
    request = TaskRequest(
        task=task_text,
        delivery_mode="standard",
        execution_context=context or None,
        task_id=str(context.get("task_id") or "") or None,
    )
    if infer_task_kind(task_text) == "feature":
        return bool(service.execute_feature(request))
    return bool(service.execute_bug(request))


@dataclass(frozen=True)
class CanonicalProductExecutionResult:
    """Result consumed directly by the daily CLI after one main-chain entry."""

    receipt: Mapping[str, Any]
    receipt_path: str
    root_receipt: Mapping[str, Any]
    root_receipt_valid: bool
    root_receipt_blockers: tuple[str, ...]
    production_ingress_count: int = 1
    production_runtime_entry_count: int = 1
    execution_decision_authority: str = "CapabilityPlanner"

    def __bool__(self) -> bool:
        return bool(
            self.root_receipt_valid
            and self.receipt.get("terminal_status") == "SUCCEEDED"
            and self.receipt.get("receipt_complete") is True
        )


@dataclass(frozen=True)
class VerifiedTaskCardIdentity:
    """Tracked-card identity returned by lifecycle readback, not caller authority."""

    task_id: str
    task_card_path: str
    canonical_task_card_path: str
    task_card_hash: str
    contract_kind: str = "TRACKED_TASK_CARD"

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("verified_task_card_task_id_missing")
        path = PurePosixPath(self.task_card_path)
        if path.is_absolute() or ".." in path.parts or not str(path).startswith("tasks/"):
            raise ValueError("verified_task_card_path_invalid")
        canonical_path = Path(self.canonical_task_card_path)
        if not canonical_path.is_absolute():
            raise ValueError("verified_task_card_canonical_path_invalid")
        if len(self.task_card_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.task_card_hash
        ):
            raise ValueError("verified_task_card_hash_invalid")
        if self.contract_kind != "TRACKED_TASK_CARD":
            raise ValueError("verified_task_card_contract_kind_invalid")


@dataclass(frozen=True)
class VerifiedCampaignIdentity:
    """Authenticated campaign source bound to one verified Task Card."""

    campaign_id: str
    task_id: str
    task_card_hash: str
    contract_kind: str = "TRACKED_TASK_CARD"

    def __post_init__(self) -> None:
        if not self.campaign_id or self.campaign_id != self.campaign_id.strip():
            raise ValueError("verified_campaign_id_invalid")
        if not self.task_id.strip() or len(self.task_card_hash) != 64:
            raise ValueError("verified_campaign_binding_invalid")
        if self.contract_kind != "TRACKED_TASK_CARD":
            raise ValueError("verified_campaign_contract_kind_invalid")


@dataclass(frozen=True)
class DayShiftAdmissionContext:
    """Planner admission bound to one tracked card and one workspace."""

    task_card_identity: VerifiedTaskCardIdentity
    repository_root: Path
    workspace_revision: str
    allowed_files: tuple[str, ...]
    verifier_command: tuple[str, ...]
    admission: Mapping[str, Any]
    campaign_identity: VerifiedCampaignIdentity | None = None
    task_text: str = ""
    source_token: object | None = None

    def __post_init__(self) -> None:
        if self.source_token is not _DAYSHIFT_CONTEXT_TOKEN:
            raise ValueError("dayshift_context_not_source_owned")
        if not isinstance(self.task_card_identity, VerifiedTaskCardIdentity):
            raise ValueError("dayshift_task_card_identity_unverified")
        if self.campaign_identity is not None and not isinstance(
            self.campaign_identity, VerifiedCampaignIdentity
        ):
            raise ValueError("dayshift_campaign_identity_unverified")
        if not self.workspace_revision.strip():
            raise ValueError("dayshift_workspace_revision_missing")
        if not self.allowed_files or any(
            not item or Path(item).is_absolute() or ".." in PurePosixPath(item).parts
            for item in self.allowed_files
        ):
            raise ValueError("dayshift_allowed_files_missing_or_invalid")
        if not self.verifier_command or any(not str(item).strip() for item in self.verifier_command):
            raise ValueError("dayshift_verifier_command_missing")
        object.__setattr__(self, "allowed_files", tuple(self.allowed_files))
        object.__setattr__(self, "verifier_command", tuple(self.verifier_command))
        if not isinstance(self.admission, Mapping):
            raise ValueError("dayshift_admission_missing")
        object.__setattr__(self, "admission", _freeze_dayshift_mapping(self.admission))
        admission = self.admission
        workforce_admission = admission.get("workforce_admission", admission)
        if not isinstance(workforce_admission, Mapping) or workforce_admission.get("overall_decision") != "ALLOW":
            raise ValueError("dayshift_admission_not_allowed")
        binding = admission.get("binding")
        if not isinstance(binding, Mapping) or any(
            not str(binding.get(key) or "").strip() for key in ("worker_id", "provider", "model", "binding_hash")
        ):
            raise ValueError("dayshift_admission_binding_missing")
        records = workforce_admission.get("records", ())
        record = next(
            (item for item in records if isinstance(item, Mapping) and item.get("demand", {}).get("execution_channel") == "online"),
            records[0] if isinstance(records, (list, tuple)) and records else {},
        )
        decision = record.get("decision", {}) if isinstance(record, Mapping) else {}
        if isinstance(decision, Mapping) and any(
            binding.get(key) != decision.get(source_key)
            for key, source_key in (
                ("worker_id", "resolved_worker_id"),
                ("provider", "resolved_provider"),
                ("model", "resolved_model"),
            )
        ):
            raise ValueError("dayshift_admission_binding_conflict")

    @property
    def task_id(self) -> str:
        return self.task_card_identity.task_id


_DAYSHIFT_ISSUED_CONTEXTS: dict[int, DayShiftAdmissionContext] = {}


def _is_issued_day_shift_context(context: object) -> bool:
    return _DAYSHIFT_ISSUED_CONTEXTS.get(id(context)) is context


def _freeze_dayshift_mapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_dayshift_mapping(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_dayshift_mapping(item) for item in value)
    return value


def build_day_shift_admission_context(
    *,
    task_text: str,
    task_card_identity: VerifiedTaskCardIdentity,
    repository_root: Path,
    workspace_revision: str,
    allowed_files: tuple[str, ...],
    verifier_command: tuple[str, ...],
    campaign_identity: VerifiedCampaignIdentity | None = None,
    execution_channels: tuple[str, ...] = ("online",),
) -> DayShiftAdmissionContext:
    """Create the only supported Stage2 context from canonical admission."""
    if not isinstance(task_card_identity, VerifiedTaskCardIdentity):
        raise ValueError("dayshift_task_card_identity_unverified")
    if not str(task_text).strip():
        raise ValueError("dayshift_task_text_missing")
    admission = build_canonical_planner_admission(
        task_id=task_card_identity.task_id,
        task_text=task_text,
        allowed_files=tuple(allowed_files),
        verifier_command=tuple(verifier_command),
        task_card_identity=task_card_identity,
        campaign_identity=campaign_identity,
        execution_channels=tuple(execution_channels),
    )
    context = DayShiftAdmissionContext(
        task_card_identity=task_card_identity,
        repository_root=Path(repository_root).resolve(),
        workspace_revision=str(workspace_revision).strip(),
        allowed_files=tuple(allowed_files),
        verifier_command=tuple(verifier_command),
        admission=admission,
        campaign_identity=campaign_identity,
        task_text=str(task_text),
        source_token=_DAYSHIFT_CONTEXT_TOKEN,
    )
    _DAYSHIFT_ISSUED_CONTEXTS[id(context)] = context
    return context


@dataclass(frozen=True)
class CanonicalDispatchEnvelope:
    """The immutable identity passed from planning through registry dispatch."""

    schema: str
    task_id: str
    attempt_id: str
    task_card_path: str
    task_card_hash: str
    demand_id: str
    planner_decision_hash: str
    planner_plan_hash: str
    worker_id: str
    provider: str
    model: str
    policy_hash: str
    binding_hash: str
    aggregate_binding_hash: str

    def __post_init__(self) -> None:
        if self.schema != "nexus.canonical_dispatch_envelope.v1":
            raise ValueError("canonical_dispatch_schema_invalid")
        for name in (
            "task_id", "attempt_id", "task_card_path", "demand_id", "worker_id", "provider", "model",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"canonical_dispatch_{name}_missing")
        for name in (
            "task_card_hash", "planner_decision_hash", "planner_plan_hash", "policy_hash",
            "binding_hash", "aggregate_binding_hash",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"canonical_dispatch_{name}_invalid")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "task_card_path": self.task_card_path,
            "task_card_hash": self.task_card_hash,
            "demand_id": self.demand_id,
            "planner_decision_hash": self.planner_decision_hash,
            "planner_plan_hash": self.planner_plan_hash,
            "worker_id": self.worker_id,
            "provider": self.provider,
            "model": self.model,
            "policy_hash": self.policy_hash,
            "binding_hash": self.binding_hash,
            "aggregate_binding_hash": self.aggregate_binding_hash,
        }


def build_canonical_dispatch_envelope(
    planner_output: Mapping[str, Any],
    dispatch_binding: Mapping[str, Any],
    *,
    task_id: str,
    attempt_id: str,
    task_card_path: str,
    task_card_hash: str,
) -> CanonicalDispatchEnvelope:
    """Bind the actual Planner decision to the already admitted worker identity."""
    if not isinstance(planner_output, Mapping):
        raise ValueError("canonical_dispatch_planner_decision_missing")
    decision = planner_output.get("execution_decision")
    if not isinstance(decision, Mapping):
        raise ValueError("canonical_dispatch_planner_decision_missing")
    if decision.get("authority") != "CapabilityPlanner":
        raise ValueError("canonical_dispatch_planner_authority_invalid")
    if str(decision.get("task_id") or "") != str(task_id):
        raise ValueError("canonical_dispatch_planner_task_mismatch")
    decision_hash = str(planner_output.get("decision_hash") or "")
    plan_hash = str(planner_output.get("plan_hash") or decision.get("plan_hash") or "")
    if decision_hash == "":
        raise ValueError("canonical_dispatch_decision_hash_missing")
    if len(decision_hash) != 64 or any(char not in "0123456789abcdef" for char in decision_hash):
        raise ValueError("canonical_dispatch_decision_hash_invalid")
    if len(plan_hash) != 64 or any(char not in "0123456789abcdef" for char in plan_hash):
        raise ValueError("canonical_dispatch_plan_hash_invalid")
    required = (
        "worker_id", "provider", "model", "policy_hash", "binding_hash",
        "aggregate_binding_hash",
    )
    if any(not isinstance(dispatch_binding.get(key), str) or not dispatch_binding[key].strip() for key in required):
        raise ValueError("canonical_dispatch_admission_identity_missing")
    return CanonicalDispatchEnvelope(
        schema="nexus.canonical_dispatch_envelope.v1",
        task_id=str(task_id),
        attempt_id=str(attempt_id),
        task_card_path=str(task_card_path),
        task_card_hash=str(task_card_hash),
        demand_id=str(dispatch_binding.get("demand_id") or ""),
        planner_decision_hash=decision_hash,
        planner_plan_hash=plan_hash,
        worker_id=str(dispatch_binding["worker_id"]),
        provider=str(dispatch_binding["provider"]),
        model=str(dispatch_binding["model"]),
        policy_hash=str(dispatch_binding["policy_hash"]),
        binding_hash=str(dispatch_binding["binding_hash"]),
        aggregate_binding_hash=str(dispatch_binding["aggregate_binding_hash"]),
    )


def _product_task_id(task_text: str, requested: str = "") -> str:
    raw = str(requested or "").strip()
    if raw and not any(char in raw for char in "/\\\x00") and len(raw) <= 120:
        return raw
    digest = hashlib.sha256(str(task_text or "").encode("utf-8")).hexdigest()[:16]
    return f"cli-{digest}"


def _safe_receipt_name(task_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", task_id)[:120] or "task"


def _bounded_product_file(
    root: Path,
    raw_path: str,
    *,
    require_regular_file: bool,
) -> str:
    value = str(raw_path or "").strip()
    try:
        relative = PurePosixPath(value)
    except (TypeError, ValueError):
        relative = PurePosixPath("/")
    if (
        not value
        or relative.is_absolute()
        or not relative.parts
        or ".." in relative.parts
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError(f"canonical_product_target_path_invalid:{value}")
    normalized = relative.as_posix()
    resolved = (root / normalized).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"canonical_product_target_path_invalid:{value}"
        ) from exc
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"canonical_product_target_path_invalid:{value}")
    if require_regular_file and not resolved.is_file():
        raise ValueError(f"canonical_product_target_path_invalid:{value}")
    return normalized


def _receipt_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _readback_runtime_receipt(
    receipt_path: Path,
    in_memory_receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Require the durable runtime receipt to match the returned payload exactly."""
    if not receipt_path.is_file():
        return dict(in_memory_receipt), ("runtime_receipt_disk_missing",)
    try:
        loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return dict(in_memory_receipt), ("runtime_receipt_disk_unreadable",)
    if not isinstance(loaded, Mapping):
        return dict(in_memory_receipt), ("runtime_receipt_disk_malformed",)
    disk_receipt = dict(loaded)
    if _receipt_payload_hash(disk_receipt) != _receipt_payload_hash(in_memory_receipt):
        return dict(in_memory_receipt), ("runtime_receipt_disk_mismatch",)
    return disk_receipt, ()


def _actual_runtime_controls(
    *,
    allowed_files: tuple[str, ...],
    verifier_command: tuple[str, ...],
) -> set[str]:
    """Describe controls physically supplied by the canonical product adapter."""
    controls = {
        "bounded_context",
        "compact_context",
        "deterministic_consumer",
        "fixed_schema",
        "governed_adapter",
        "isolated_directory",
        "json_event_receipt",
        "parser",
        "receipt",
        "reversible_application",
        "schema_validation",
    }
    if allowed_files:
        controls.update({"allowed_files", "bounded_scope", "small_scope"})
    if verifier_command:
        controls.update(
            {
                "external_verifier",
                "focused_tests",
                "independent_verification",
                "mandatory_commands",
                "verifier",
            }
        )
        joined = " ".join(verifier_command).lower()
        if "compile" in joined or "py_compile" in joined:
            controls.add("compile")
    return controls


def _derive_campaign_id_from_task_card(task_card_identity: 'VerifiedTaskCardIdentity') -> str:
    """Derive campaign identity from verified Task Card path or content.

    Campaign identity is exact-match only; blank, missing, or unrelated
    paths use the global route. Task-ID prose/prefix alone cannot mint
    campaign identity.
    """
    known_campaigns = {
        "CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01",
        "CAMPAIGN-PLANNER-WORKFORCE-SELECTION-REPAIR-01",
        "open-swe-resident-five-repo-canary-20260908",
    }
    canonical_path = Path(task_card_identity.canonical_task_card_path)
    try:
        card_bytes = canonical_path.read_bytes()
    except OSError as exc:
        raise ValueError("verified_task_card_canonical_bytes_missing") from exc
    actual_hash = hashlib.sha256(card_bytes).hexdigest()
    if actual_hash != task_card_identity.task_card_hash:
        raise ValueError("verified_task_card_hash_mismatch")
    content = card_bytes.decode("utf-8")
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("Campaign:"):
            value = stripped.split(":", 1)[1].strip().strip("`")
            return value if value in known_campaigns else ""
    return ""


def _resolve_policy_workforce_bindings(
    plan_payload: Mapping[str, Any],
    *,
    allowed_files: tuple[str, ...],
    verifier_command: tuple[str, ...],
    campaign_id: str = "",
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve Planner demands through the tracked Workforce policy.

    Callers cannot supply worker, provider, or model identities.  This function
    projects each Planner demand through the policy's canonical routing map;
    only Workforce Admission evaluates that mapped identity's eligibility.

    Campaign resolution is exact-match only; blank, missing, prefixed,
    or unrelated campaign IDs use the global route.
    """
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader

    policy = WorkforcePolicyLoader()
    snapshot = policy.load()
    signal_snapshot = plan_payload.get("signal_snapshot")
    demands_payload = (
        signal_snapshot.get("workforce_demands")
        if isinstance(signal_snapshot, Mapping)
        else None
    )
    demands = demands_payload.get("demands") if isinstance(demands_payload, Mapping) else None
    if not isinstance(demands, (list, tuple)):
        raise ValueError("canonical_workforce_demands_missing")

    controls = _actual_runtime_controls(
        allowed_files=allowed_files,
        verifier_command=verifier_command,
    )
    bindings: dict[str, Any] = {}
    providers: dict[str, str] = {}
    seen_channels: set[str] = set()
    for demand in demands:
        if not isinstance(demand, Mapping):
            raise ValueError("canonical_workforce_demand_malformed")
        channel = str(demand.get("execution_channel") or "")
        role = str(demand.get("requested_role") or "")
        if channel in seen_channels:
            raise ValueError(f"canonical_workforce_demand_conflict:{channel}")
        seen_channels.add(channel)
        if channel == "online":
            # Use campaign-aware resolution for online channel
            worker_id = policy.resolve_route(role, campaign_id=campaign_id)
        else:
            route_group_name = "local_first" if channel == "local" else channel
            route_group = snapshot.routing.get(route_group_name)
            worker_id = route_group.get(role) if isinstance(route_group, Mapping) else None
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError(f"canonical_workforce_route_missing:{channel}:{role}")
        worker = snapshot.workers.get(worker_id)
        if worker is None:
            raise ValueError(
                f"canonical_workforce_route_worker_missing:{channel}:{role}:{worker_id}"
            )
        bindings[channel] = {
            "worker_id": worker.worker_id,
            "controls": sorted(controls),
        }
        providers[channel] = worker.provider
    return bindings, providers


def build_canonical_planner_admission(
    *,
    task_id: str,
    task_text: str,
    allowed_files: tuple[str, ...],
    verifier_command: tuple[str, ...],
    task_card_identity: VerifiedTaskCardIdentity,
    campaign_identity: VerifiedCampaignIdentity | None = None,
    execution_channels: tuple[str, ...] = ("online",),
) -> dict[str, Any]:
    """Run the sole planner and current Workforce Admission for one gateway task."""
    from nexus.contracts.canonical_execution import CanonicalTaskContext
    from nexus.services.model_workforce_policy import WorkforcePolicyLoader
    from nexus.services.runtime_workforce_admission import evaluate_runtime_workforce_admission

    if not isinstance(task_card_identity, VerifiedTaskCardIdentity):
        raise ValueError("canonical_task_card_identity_unverified")
    if task_card_identity.task_id != task_id:
        raise ValueError("canonical_task_card_task_mismatch")

    task_card_campaign_id = _derive_campaign_id_from_task_card(task_card_identity)
    candidate_generation_only = (
        task_card_campaign_id == "open-swe-resident-five-repo-canary-20260908"
    )
    context = CanonicalTaskContext(
        task_id=str(task_id),
        task_type="feature" if infer_task_kind(task_text) == "feature" else "repair",
        task_desc=str(task_text),
        execution_world="product_runtime",
        transport_ingress="mcp",
        execution_channels=tuple(execution_channels),
        task_facts={
            "mutation_requested": bool(allowed_files) and not candidate_generation_only,
            "candidate_required": True,
            **({"candidate_generation_only": True} if candidate_generation_only else {}),
        },
        authority_inputs={
            "direct_canonical_eligible": False,
            "isolation_required": True,
            "owner_authorized": False,
            "assisted_execution_required": False,
        },
        route_features={
            "bounded_allowed_file_count": len(allowed_files),
            "deterministic_verifier_available": bool(verifier_command),
        },
        codeintel={
            "allowed_files": list(allowed_files),
            "verify_commands": list(verifier_command),
        },
    )
    from nexus.engine.canonical_execution import plan_canonical_task_bundle

    bundle = plan_canonical_task_bundle(context)
    planner_output = bundle.to_dict()
    plan_payload = planner_output["plan_payload"]
    demands = (plan_payload.get("signal_snapshot") or {}).get("workforce_demands")
    if not isinstance(demands, Mapping):
        raise ValueError("canonical_workforce_demands_missing")
    policy = WorkforcePolicyLoader()
    snapshot = policy.load()
    campaign_id = task_card_campaign_id
    if campaign_identity is not None:
        if not isinstance(campaign_identity, VerifiedCampaignIdentity):
            raise ValueError("canonical_campaign_identity_unverified")
        if (
            campaign_identity.task_id != task_card_identity.task_id
            or campaign_identity.task_card_hash != task_card_identity.task_card_hash
            or campaign_identity.contract_kind != task_card_identity.contract_kind
        ):
            raise ValueError("canonical_campaign_identity_binding_mismatch")
        if campaign_id and campaign_identity.campaign_id != campaign_id:
            raise ValueError("canonical_campaign_identity_conflict")
        campaign_id = campaign_identity.campaign_id
    policy_bindings, _ = _resolve_policy_workforce_bindings(
        plan_payload,
        allowed_files=allowed_files,
        verifier_command=verifier_command,
        campaign_id=campaign_id,
    )
    runtime_bindings: dict[str, Any] = {}
    for channel, policy_binding in policy_bindings.items():
        worker = snapshot.workers.get(str(policy_binding["worker_id"]))
        if worker is None:
            raise ValueError(f"canonical_workforce_worker_missing:{channel}")
        controls = set(policy_binding.get("controls") or [])
        controls.add("task_card")
        runtime_bindings[channel] = {
            "worker_id": worker.worker_id,
            "provider": worker.provider,
            "model": worker.model,
            "controls": sorted(controls),
        }
    admission = evaluate_runtime_workforce_admission(
        demands,
        runtime_bindings,
        policy,
    ).to_dict()
    records = admission.get("records")
    if admission.get("overall_decision") != "ALLOW" or not isinstance(records, list) or not records:
        raise ValueError("canonical_workforce_admission_not_single_allow")
    if any(
        not isinstance(item, Mapping)
        or not isinstance(item.get("decision"), Mapping)
        or item["decision"].get("decision") != "ALLOW"
        for item in records
    ):
        raise ValueError("canonical_workforce_admission_not_single_allow")
    record = next(
        item for item in records
        if item.get("demand", {}).get("execution_channel") == "online"
    ) if any(
        isinstance(item, Mapping)
        and item.get("demand", {}).get("execution_channel") == "online"
        for item in records
    ) else records[0]
    decision = record.get("decision") if isinstance(record, Mapping) else None
    if not isinstance(decision, Mapping) or decision.get("decision") != "ALLOW":
        raise ValueError("canonical_workforce_admission_not_single_allow")
    demand = next(
        item for item in demands["demands"] if item.get("execution_channel") == "online"
    )
    binding_identity = runtime_bindings.get("online") or runtime_bindings["local"]
    policy_identity = admission.get("policy_identity")
    if not isinstance(policy_identity, Mapping):
        policy_identity = {}
    return {
        "planner_output": planner_output,
        "workforce_demands": demands,
        "workforce_admission": admission,
        "workforce_bindings": runtime_bindings,
        "binding": {
            "demand_id": str(demand.get("demand_id") or ""),
            "worker_id": str(binding_identity.get("worker_id") or ""),
            "provider": str(binding_identity.get("provider") or ""),
            "model": str(binding_identity.get("model") or ""),
            "policy_hash": str(policy_identity.get("policy_hash") or ""),
            "binding_hash": str(record.get("binding_hash") or ""),
            "aggregate_binding_hash": str(admission.get("aggregate_binding_hash") or ""),
        },
    }


def _execution_learning_observer(context: Mapping[str, Any]) -> dict[str, Any]:
    """Bind observed runtime evidence without promoting a reusable lesson."""
    task_id = str(context.get("task_id") or "")
    local_raw = context.get("local")
    online_raw = context.get("online")
    local = local_raw if isinstance(local_raw, Mapping) else {}
    online = online_raw if isinstance(online_raw, Mapping) else {}
    evidence = bool(local.get("evidence_present") or online.get("evidence_present"))
    gate = bool(local.get("gate_passed") or online.get("gate_passed"))
    passed = bool(task_id and evidence and gate)
    return {
        "task_id": task_id,
        "status": "pass" if passed else "failed",
        "invoked": True,
        "gate_passed": passed,
        "evidence_refs": [f"learning:{task_id}:runtime_observation"] if evidence else [],
        "promotion_allowed": False,
        "source": "canonical_product_runtime_observation",
    }


def execute_canonical_product_task(
    task_text: str,
    project_root: Path,
    execution_context: Mapping[str, Any] | None = None,
) -> CanonicalProductExecutionResult:
    """Execute daily product work through one Planner and one Mainchain entry.

    This path has no CommandService/NexusEngine/NexusPipeline fallback.  Route,
    provider, model, topology, and legacy/new runtime selectors are rejected as
    caller inputs.
    """
    from nexus.contracts.canonical_execution import CanonicalTaskContext
    from nexus.contracts.root_receipt import (
        build_world_c_verifier_projection,
        validate_root_receipt,
    )
    from nexus.engine.canonical_execution import plan_canonical_task_bundle
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.local_assist_service import LocalAssistRequest, LocalAssistService
    from nexus.services.online_execution_policy import (
        normalize_online_policy,
        resolve_online_execution_decision,
    )
    from nexus.services.unified_runtime import UnifiedRuntimeRequest

    root = Path(project_root).resolve()
    context = dict(execution_context or {})
    forbidden = {
        "execution_topology",
        "lane",
        "model",
        "oauth_provider",
        "online_model",
        "online_provider",
        "provider",
        "recommended_flow",
        "route",
        "runtime_selector",
        "worker",
        "worker_id",
    }
    supplied_forbidden = sorted(forbidden.intersection(context))
    if supplied_forbidden:
        raise ValueError(f"canonical_product_caller_override_forbidden:{supplied_forbidden[0]}")

    task_id = _product_task_id(task_text, str(context.get("task_id") or ""))
    revision = str(context.get("workspace_revision") or "").strip()
    if not revision:
        raise ValueError("canonical_product_workspace_revision_missing")

    mode = str(context.get("local_assist_mode") or "disabled").strip().lower()
    if mode not in {"disabled", "shadow", "advisor"}:
        raise ValueError("canonical_product_local_policy_invalid")
    online_policy = normalize_online_policy(context.get("online_policy"))

    raw_allowed = context.get("target_files") or ()
    if isinstance(raw_allowed, str):
        raw_allowed = (raw_allowed,)
    allowed_files = tuple(dict.fromkeys(
        _bounded_product_file(root, str(item), require_regular_file=False)
        for item in raw_allowed
        if str(item).strip()
    ))
    raw_target_file = str(
        context.get("target_file") or (allowed_files[0] if allowed_files else "")
    )
    target_file = (
        _bounded_product_file(root, raw_target_file, require_regular_file=True)
        if raw_target_file
        else ""
    )
    if target_file and target_file not in allowed_files:
        raise ValueError("canonical_product_target_outside_allowed_files")

    raw_verifier = context.get("verifier_command") or ()
    if isinstance(raw_verifier, str):
        verifier_command = tuple(shlex.split(raw_verifier))
    elif isinstance(raw_verifier, (list, tuple)):
        verifier_command = tuple(str(item) for item in raw_verifier if str(item))
    else:
        raise ValueError("canonical_product_verifier_command_invalid")

    local_enabled = mode == "advisor"
    if online_policy == "deny" and not local_enabled:
        raise ValueError("canonical_product_no_execution_channel_enabled")
    verified_world_c = bool(local_enabled and allowed_files and target_file and verifier_command)
    if local_enabled and not allowed_files:
        raise ValueError("canonical_product_local_allowed_files_missing")

    task_type = "review" if local_enabled and not verified_world_c else (
        "feature" if infer_task_kind(task_text) == "feature" else "repair"
    )
    task_evidence_id = "canonical-" + hashlib.sha256(
        json.dumps(
            {
                "task_id": task_id,
                "workspace_revision": revision,
                "task_statement": str(task_text),
                "allowed_files": list(allowed_files),
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:24]
    codeintel = {
        "workspace_root": str(root),
        "target_file": target_file,
        "verify_commands": [shlex.join(verifier_command)] if verifier_command else [],
        "verify_timeout_sec": 120,
        "mempalace_tenant_id": "canonical-product",
        "mempalace_artifact_type": "canonical_task_context",
        "mempalace_artifact": {
            "artifact_id": task_evidence_id,
            "task_id": task_id,
            "workspace_revision": revision,
            "task_statement_hash": hashlib.sha256(
                str(task_text).encode("utf-8")
            ).hexdigest(),
            "allowed_files": list(allowed_files),
        },
        "mempalace_query": task_evidence_id,
    }
    route_features = {
        "bounded_allowed_file_count": len(allowed_files),
        "deterministic_verifier_available": bool(verifier_command),
    }
    execution_channels = ("online",)
    if local_enabled:
        execution_channels = (
            ("local",) if online_policy == "deny" else ("online", "local")
        )
    from nexus.engine.learning_policy_loader import merge_runtime_learning_policy

    runtime_budget = merge_runtime_learning_policy(
        root,
        context.get("budget") or {},
        task_desc=str(task_text),
        target_model=os.environ.get("NEXUS_LOCAL_MODEL_EXECUTOR_MODEL", "qwen2.5-coder:7b"),
        runtime_identity="local_model_executor",
        source_revision=revision,
    )

    canonical_context = CanonicalTaskContext(
        task_id=task_id,
        task_type=task_type,
        task_desc=str(task_text),
        execution_world=str(context.get("execution_world") or "product_runtime"),
        transport_ingress=str(context.get("transport_ingress") or "direct"),
        execution_channels=execution_channels,
        task_facts={
            "mutation_requested": bool(allowed_files),
            "candidate_required": verified_world_c,
        },
        authority_inputs={
            "direct_canonical_eligible": False,
            "isolation_required": verified_world_c,
            "owner_authorized": False,
            "assisted_execution_required": not verified_world_c,
        },
        route_features=route_features,
        codeintel=codeintel,
        budget=runtime_budget,
    )
    bundle = plan_canonical_task_bundle(canonical_context)
    plan_payload = bundle.to_dict()["plan_payload"]
    bindings, policy_providers = _resolve_policy_workforce_bindings(
        plan_payload,
        allowed_files=allowed_files,
        verifier_command=verifier_command,
    )

    selected_online_provider = policy_providers.get("online", "")
    online_decision = resolve_online_execution_decision(
        task_online_policy=online_policy,
        project_root=root,
        planner_online_needed=online_policy != "deny",
        requested_provider=selected_online_provider,
    )
    route = {
        "workspace_root": str(root),
        "route_features": route_features,
        "online_policy": online_decision.online_policy,
        "online_execution_decision": online_decision.to_dict(),
        "workforce_bindings": bindings,
    }

    local_request = None
    local_service = None
    verifier = None
    if local_enabled:
        snapshot = dict(plan_payload.get("signal_snapshot") or {})
        action = "verified-subtask" if verified_world_c else "advisor"
        local_request = LocalAssistRequest(
            schema="nexus.local_assist.request.v1",
            task_id=task_id,
            parent_task_id=task_id,
            workspace_root=str(root),
            workspace_revision=revision,
            task_statement=str(task_text),
            action=action,
            allowed_files=allowed_files,
            target_file=target_file,
            target_symbol=str(context.get("target_symbol") or ""),
            evidence_refs=(f"canonical-product:{task_id}:bounded-request",),
            verifier_command=verifier_command,
            requested_role="candidate" if verified_world_c else "advisor",
            mutation_policy="isolated_only",
            planner_snapshot=snapshot,
        )
        local_service = LocalAssistService()
        if verified_world_c:
            verifier = build_world_c_verifier_projection

    receipt_path = (
        root
        / ".nexus"
        / "reports"
        / "run"
        / f"{_safe_receipt_name(task_id)}.canonical_runtime.json"
    )
    # Runtime writer selection is source-owned.  The canonical product API
    # remains unchanged; it may only consume the already-loaded binding for
    # this exact project root.  Legacy/unactivated roots intentionally return
    # no factory and retain their existing behavior, while activated roots
    # fail closed inside the adapter when the binding is absent or stale.
    from nexus.orchestrator.writer_quiescence import (
        WriterAdmissionDenied,
        lookup_runtime_writer_factory,
    )

    runtime_writer_factory = lookup_runtime_writer_factory(root)
    from nexus.services.unified_runtime import _validate_runtime_writer_entry

    # Gateway construction can create report directories. Fence the selected
    # destination before constructing it, as well as at the Runtime boundary.
    _validate_runtime_writer_entry(
        runtime_writer_factory, owner_context=None,
        receipt_path=receipt_path, effect_journal=None,
    )
    effect_ports = {}
    if runtime_writer_factory is not None:
        effect_binding = runtime_writer_factory.effect_binding()
        if effect_binding is None:
            raise WriterAdmissionDenied("canonical_runtime_effect_binding_required")
        _validate_runtime_writer_entry(
            runtime_writer_factory, owner_context=None,
            receipt_path=receipt_path, effect_journal=effect_binding.journal,
        )
        effect_ports = {
            "effect_journal": effect_binding.journal,
            "effect_dispatch": effect_binding.dispatch,
            "effect_reconcile": effect_binding.reconcile,
            "effect_fenced": True,
        }
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision=revision,
        task_statement=str(task_text),
        task_type=task_type,
        route=route,
        budget=runtime_budget,
        online_enabled=online_decision.online_execution_requested,
        local_enabled=local_enabled,
        online_prompt=str(task_text),
        online_payload=json.dumps(
            {
                "task_id": task_id,
                "allowed_files": list(allowed_files),
                "verification_required": bool(verifier_command),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        online_output_schema={
            "status": "APPROVED | REJECTED | FAIL",
            "summary": "bounded result",
            "patch": "optional unified diff",
        },
        codeintel=codeintel,
        local_request=local_request,
        evidence_refs=(f"canonical-product:{task_id}:request",),
        canonical_context={
            "execution_world": canonical_context.execution_world,
            "transport_ingress": canonical_context.transport_ingress,
            "task_facts": dict(canonical_context.task_facts),
            "authority_inputs": dict(canonical_context.authority_inputs),
        },
        canonical_planning_bundle=bundle,
    )

    gateway = BattlesuitGateway(project_root=root)
    receipt = gateway.ask_unified(
        request,
        local_service=local_service,
        verifier=verifier,
        learning=_execution_learning_observer,
        receipt_path=receipt_path,
        runtime_writer_factory=runtime_writer_factory,
        **effect_ports,
    )
    receipt, readback_blockers = _readback_runtime_receipt(receipt_path, receipt)
    root_receipt = receipt.get("root_receipt")
    root_receipt = dict(root_receipt) if isinstance(root_receipt, Mapping) else {}
    root_valid, blockers = validate_root_receipt(root_receipt)
    if readback_blockers:
        root_valid = False
        blockers = sorted(set([*blockers, *readback_blockers]))
    authority = str(
        (receipt.get("canonical_execution") or {}).get("execution_decision_authority")
        if isinstance(receipt.get("canonical_execution"), Mapping)
        else ""
    )
    if authority != "CapabilityPlanner":
        root_valid = False
        blockers = sorted(set([*blockers, "execution_decision_authority_invalid"]))
    return CanonicalProductExecutionResult(
        receipt=receipt,
        receipt_path=str(receipt_path),
        root_receipt=root_receipt,
        root_receipt_valid=root_valid,
        root_receipt_blockers=tuple(blockers),
        execution_decision_authority=authority or "INVALID",
    )
