import hashlib
import importlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


def infer_task_kind(task_text: str) -> str:
    text = str(task_text or "").strip().lower()
    feature_keywords = (
        "build",
        "create",
        "add",
        "implement",
        "feature",
        "新增",
        "建立",
        "實作",
        "開發",
    )
    if any(keyword in text for keyword in feature_keywords):
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


def _resolve_policy_workforce_bindings(
    plan_payload: Mapping[str, Any],
    *,
    allowed_files: tuple[str, ...],
    verifier_command: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolve Planner demands through the tracked Workforce policy.

    Callers cannot supply worker, provider, or model identities.  This function
    only maps the Planner's demand role to an admissible policy worker; the
    runtime Workforce Admission gate remains the final authority.
    """
    from nexus.services.model_workforce_policy import (
        NON_ADMISSIBLE_STATES,
        WorkforcePolicyLoader,
    )

    snapshot = WorkforcePolicyLoader().load()
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
    for demand in demands:
        if not isinstance(demand, Mapping):
            raise ValueError("canonical_workforce_demand_malformed")
        channel = str(demand.get("execution_channel") or "")
        role = str(demand.get("requested_role") or "")
        context_class = str(demand.get("context_class") or "")
        candidates = [
            worker
            for worker in snapshot.workers.values()
            if worker.state not in NON_ADMISSIBLE_STATES
            and worker.availability == "AVAILABLE"
            and role in worker.roles
        ]
        if context_class:
            context_matches = [
                worker
                for worker in candidates
                if not worker.preferred_context or worker.preferred_context == context_class
            ]
            if context_matches:
                candidates = context_matches
        if not candidates:
            raise ValueError(f"canonical_workforce_worker_missing:{channel}:{role}")
        worker = candidates[0]
        bindings[channel] = {
            "worker_id": worker.worker_id,
            "controls": sorted(controls),
        }
        providers[channel] = worker.provider
    return bindings, providers


def _execution_learning_observer(context: Mapping[str, Any]) -> dict[str, Any]:
    """Bind observed runtime evidence without promoting a reusable lesson."""
    task_id = str(context.get("task_id") or "")
    local = context.get("local") if isinstance(context.get("local"), Mapping) else {}
    online = context.get("online") if isinstance(context.get("online"), Mapping) else {}
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
    raw_online_policy = context.get("online_policy")
    online_policy = (
        normalize_online_policy(str(raw_online_policy))
        if raw_online_policy is not None
        else ""
    )

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
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision=revision,
        task_statement=str(task_text),
        task_type=task_type,
        route=route,
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
