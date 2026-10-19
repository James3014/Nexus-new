"""Worker candidate and model calibration of ``UnifiedMCPGateway``.

Big-file split G7b (Issue #2490). ``_WorkerCandidateMixin`` holds
``_resolve_assisted_worker``, ``_worker_candidate``, ``_model_calibration_evidence`` and
``_model_calibration_plan``, moved out of ``nexus/orchestrator/unified_mcp_gateway.py``.
Their source lines are verbatim, except that ``_git``, ``pre_action_guard``,
``CANONICAL_SOURCE_ROOT`` and ``build_canonical_planner_admission`` (patched on the gateway
module by tests) and ``GatewayInputError``, ``TOOL_MANIFEST_REVISION``, ``_text``,
``_safe_relative_path`` and ``_require_bound_controller`` (defined by the gateway), plus
``NON_ADMISSIBLE_STATES`` (read from the gateway's import), are resolved at call time
through ``_gateway()``.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

from nexus.contracts.lifecycle_action import (
    ContractKind,
    LifecycleActionType,
    MutationDomain,
    PermissionProfile,
    build_action_envelope,
)
from nexus.engine.canonical_task_seam import (
    VerifiedTaskCardIdentity,
    build_canonical_dispatch_envelope,
)
from nexus.orchestrator.measure_external_target import (
    ExternalTarget,
    ExternalTargetError,
    external_target_enabled,
    external_target_head,
    validate_external_target,
)
from nexus.orchestrator.self_hosted_task_service import (
    resolve_lifecycle_identity,
    validate_task_card_binding,
)
from nexus.orchestrator.task_contract import parse_task_card_expected_evidence
from nexus.services.model_capability_lineage import CHANGE_KIND_VALUES, LineageResolutionError
from nexus.services.unified_runtime import ONLINE_CLI_SPEC_REGISTRY

if TYPE_CHECKING:
    # Typing only: the model-probe (and, through it, assist) helpers called through ``self``.
    from nexus.orchestrator.unified_mcp_gateway_parts.model_probe import (
        _ModelProbeMixin as _WorkerCandidateBase,
    )
    from nexus.services.model_capability_lineage import CalibrationPlanner
else:
    _WorkerCandidateBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


_RIE_IDENTITY_KEYS = frozenset({"repository", "pr_number", "base_sha", "current_main_sha"})


def _rie_knowledge_identity(raw: Any, head: str) -> dict[str, Any]:
    """Validate the optional RIE knowledge identity hint (#1579) against the bound HEAD.

    The hint is context for the Planner-selected codeintel hook only; it selects,
    routes and gates nothing.  It is normalized here, then signed into the bound
    request.  ``head_sha`` is never caller-supplied: the hook uses the leased
    target revision.  ``base_sha`` must be an ancestor of the bound controller
    HEAD, so the changed-path set RIE sees (``base_sha..HEAD``) is a real slice of
    this repository's history.  ``current_main_sha`` is snapshot metadata only: it
    may be on a sibling history (main moved on) and keeps the hook's default
    (``base_sha``) when omitted, so a retry after HEAD moves keeps the same hint.
    """
    from nexus.services.rie_knowledge_codeintel_hook import validate_identity_hint

    if not isinstance(raw, Mapping) or not set(raw) <= _RIE_IDENTITY_KEYS:
        raise _gateway().GatewayInputError("RIE_KNOWLEDGE_IDENTITY_INVALID")
    normalized = validate_identity_hint(raw)
    if normalized is None:
        raise _gateway().GatewayInputError("RIE_KNOWLEDGE_IDENTITY_INVALID")
    try:
        _gateway()._git("merge-base", "--is-ancestor", normalized["base_sha"], head)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        raise _gateway().GatewayInputError("RIE_KNOWLEDGE_IDENTITY_NOT_ANCESTOR:base_sha") from exc
    return normalized


_CODEINTEL_LOOKUP_KEYS = frozenset({"target_symbol", "search_paths"})
_CODEINTEL_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _codeintel_lookup(raw: Any, *, root: Optional[Path] = None) -> dict[str, Any]:
    """Validate the optional codeintel lookup target (#1579).

    Lets the Planner-selected codeintel executor perform its real, read-only
    implementation lookup (it refuses without a symbol); it selects, routes and
    gates nothing.  A dotted Python identifier (max 128) and 1-4 safe
    repository-relative ``.py`` files to search, so a lookup always inspects
    named files and never scans a directory.
    """
    invalid = _gateway().GatewayInputError("CODEINTEL_LOOKUP_INVALID")
    if not isinstance(raw, Mapping) or not set(raw) <= _CODEINTEL_LOOKUP_KEYS:
        raise invalid
    symbol = raw.get("target_symbol")
    if not isinstance(symbol, str) or len(symbol) > 128 or not _CODEINTEL_SYMBOL.fullmatch(symbol):
        raise invalid
    paths = raw.get("search_paths")
    if not isinstance(paths, list) or not 1 <= len(paths) <= 4:
        raise invalid
    for path in paths:
        if not isinstance(path, str) or not path.endswith(".py"):
            raise invalid
        try:
            if root is None:
                _gateway()._safe_relative_path(path, "codeintel_lookup.search_paths")
            else:
                _gateway()._safe_relative_path(path, "codeintel_lookup.search_paths", root=root)
        except Exception as exc:  # noqa: BLE001 - one stable refusal code
            raise invalid from exc
    # Containment, existence and symlinks are re-checked against the leased target
    # worktree by the task service right before the lookup.
    return {"target_symbol": symbol, "search_paths": list(paths)}


class _WorkerCandidateMixin(_WorkerCandidateBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by UnifiedMCPGateway
        _workforce_loader: Any  # WorkforcePolicyLoader; pyright cannot resolve that import symbol
        _calibration_planner: CalibrationPlanner

        @staticmethod
        def _canonical_request(
            task_id: str,
            what: str,
            why: str,
            allowed: list[str],
            verifiers: list[str],
            base: str,
            *,
            action: Optional[Mapping[str, Any]] = ...,
            contract_binding: Optional[Mapping[str, Any]] = ...,
            controller_dirty_baseline_authorization: Optional[Mapping[str, Any]] = ...,
            bound_action_request: Optional[Mapping[str, Any]] = ...,
            controller_repo_root: Optional[Path] = ...,
        ) -> dict[str, Any]: ...

        @staticmethod
        def _exact_hash(value: Any, field: str, length: int) -> str: ...

    # fmt: off
    def _resolve_assisted_worker(self, requested: str, requested_model: str) -> tuple[str, str, str | None]:
        """Resolve provider, exact model, and policy worker ID from one request."""
        key = str(requested or "auto").strip().lower() or "auto"
        model = str(requested_model or "").strip()
        if key == "auto":
            provider = os.environ.get("NEXUS_ASSIST_PROVIDER", "agy").strip().lower() or "agy"
            return provider, model, None
        snapshot = self._workforce_loader.load()
        worker = snapshot.workers.get(key)
        if worker is None:
            matches = [item for item in snapshot.workers.values() if item.model == key]
            if len(matches) == 1:
                worker = matches[0]
            elif key not in ONLINE_CLI_SPEC_REGISTRY and key not in {"mimo", "ollama"}:
                raise _gateway().GatewayInputError("ASSIST_PROVIDER_NOT_REGISTERED")
        if worker is not None:
            if worker.state in _gateway().NON_ADMISSIBLE_STATES:
                raise _gateway().GatewayInputError(f"ASSIST_MODEL_NOT_ADMISSIBLE:{worker.worker_id}")
            if model and model != worker.model:
                raise _gateway().GatewayInputError("ASSIST_MODEL_IDENTITY_MISMATCH")
            return worker.provider, worker.model, worker.worker_id
        return key, model, None

    def _worker_candidate(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = {
            "task_id", "what", "why", "worker", "provider", "model", "allowed_files", "verifier_commands",
            "owner_confirmation", "authority_change_candidate_confirmation",
            "workforce_demands", "workforce_admission", "planner_output",
            "task_card_path", "task_card_hash", "fail_to_pass_required",
            "rie_knowledge_identity", "codeintel_lookup",
        }
        # #2721: ``external_target`` exists only on a measurement Gateway
        # (NEXUS_MEASURE_EXTERNAL_TARGET_ROOT set).  Elsewhere it stays an
        # unknown field and is refused exactly like any other.
        if external_target_enabled():
            allowed_keys.add("external_target")
        unknown = sorted(set(arguments) - allowed_keys)
        if unknown:
            raise _gateway().GatewayInputError(f"WORKER_CANDIDATE_UNKNOWN_FIELDS:{','.join(unknown)}")
        if arguments.get("owner_confirmation") is not True:
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        _gateway()._require_bound_controller()
        external: Optional[ExternalTarget] = None
        if "external_target" in arguments:
            try:
                external = validate_external_target(
                    arguments["external_target"],
                    nexus_root=Path(_gateway().CANONICAL_SOURCE_ROOT),
                    forbidden_roots=(Path(_gateway().LOADED_SOURCE_ROOT),),
                )
            except ExternalTargetError as exc:
                raise _gateway().GatewayInputError(str(exc)) from exc
            if "rie_knowledge_identity" in arguments:
                # Its ancestry check reads the Nexus-new history, not the external one.
                raise _gateway().GatewayInputError("EXTERNAL_TARGET_RIE_KNOWLEDGE_UNSUPPORTED")
        external_root = external.repo_root if external is not None else None
        authority_confirmation = arguments.get("authority_change_candidate_confirmation", False)
        if not isinstance(authority_confirmation, bool):
            raise _gateway().GatewayInputError("AUTHORITY_CHANGE_CONFIRMATION_INVALID")
        fail_to_pass_required = arguments.get("fail_to_pass_required", False)
        if not isinstance(fail_to_pass_required, bool):
            raise _gateway().GatewayInputError("FAIL_TO_PASS_REQUIRED_INVALID")
        what = _gateway()._text(arguments.get("what"), "what", max_length=4000)
        why = _gateway()._text(arguments.get("why"), "why", max_length=4000)
        task_id = self._task_id(arguments, what, why, [str(p).strip() for p in arguments.get("allowed_files") or []])
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not 1 <= len(allowed) <= 4:
            raise _gateway().GatewayInputError("allowed_files must contain 1-4 bounded paths")
        for path in allowed:
            if external_root is None:
                _gateway()._safe_relative_path(path, "allowed_files")
            else:
                _gateway()._safe_relative_path(path, "allowed_files", root=external_root)
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or [] if str(command).strip()]
        if not verifiers or len(verifiers) > 4:
            raise _gateway().GatewayInputError("verifier_commands must contain 1-4 bounded commands")
        if any(any(token in command for token in (";", "&&", "||", "`", "$(", "|")) for command in verifiers):
            raise _gateway().GatewayInputError("verifier_commands must be bounded")
        raw_task_card_path = arguments.get("task_card_path")
        raw_task_card_hash = arguments.get("task_card_hash")
        task_card_path = raw_task_card_path if isinstance(raw_task_card_path, str) else ""
        task_card_hash = raw_task_card_hash if isinstance(raw_task_card_hash, str) else ""
        if bool(task_card_path) != bool(task_card_hash):
            raise _gateway().GatewayInputError("TASK_CARD_PATH_HASH_PAIR_REQUIRED")
        if not task_card_path:
            raise _gateway().GatewayInputError("TRACKED_TASK_CARD_REQUIRED")
        _gateway()._safe_relative_path(task_card_path, "task_card_path")
        if not task_card_path.startswith("tasks/"):
            raise _gateway().GatewayInputError("TASK_CARD_PATH_INVALID")
        if len(task_card_hash) != 64 or any(char not in "0123456789abcdef" for char in task_card_hash):
            raise _gateway().GatewayInputError("TASK_CARD_HASH_INVALID")
        head = self._exact_hash(_gateway()._git("rev-parse", "HEAD").strip(), "expected_head", 40)
        _gateway()._require_bound_controller(head)
        # ``head`` stays the Nexus-new Controller HEAD (it holds the Task Card);
        # ``target_head`` is the revision the Target is cut from and the one the
        # action envelope binds.  They differ only for an external target (#2721).
        target_head = external.base_revision if external is not None else head
        rie_identity = (
            _rie_knowledge_identity(arguments["rie_knowledge_identity"], head)
            if "rie_knowledge_identity" in arguments
            else None
        )
        codeintel_lookup = (
            _codeintel_lookup(arguments["codeintel_lookup"], root=external_root)
            if "codeintel_lookup" in arguments
            else None
        )
        external_request: dict[str, Any] = (
            {"controller_repo_root": external_root} if external_root is not None else {}
        )
        contract_binding = {
            "contract_kind": ContractKind.TRACKED_TASK_CARD.value,
            "contract_hash": None,
            "owner_inline_contract": None,
            "task_card_path": task_card_path,
            "task_card_hash": task_card_hash,
        }
        protected_contracts = ["repository-authority-change.v1"] if authority_confirmation else []
        card_request = self._canonical_request(
            task_id,
            what,
            why,
            allowed,
            verifiers,
            target_head,
            contract_binding=contract_binding,
            **external_request,
        )
        card_request.update({
            "worker": "auto",
            "execution_lane": "ISOLATED_TARGET",
            "primary_agent": False,
            "worker_candidate_ingress": True,
            "task_card_required": True,
            "lifecycle_identity_required": True,
            "protected_contracts": protected_contracts,
        })
        if authority_confirmation:
            card_request["authority_change_candidate_confirmation"] = True
        if fail_to_pass_required:
            card_request["fail_to_pass_required"] = True
        try:
            contract = self.service.build_contract(card_request)
            validate_task_card_binding(
                contract,
                card_request,
                is_ephemeral=bool(getattr(self.service, "ephemeral", False)),
            )
            lifecycle_identity = resolve_lifecycle_identity(
                contract,
                card_request,
                is_ephemeral=bool(getattr(self.service, "ephemeral", False)),
            )
            canonical_card_path = Path(str(lifecycle_identity.get("task_card_path") or "")).resolve()
            canonical_relative_path = canonical_card_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT.resolve()).as_posix()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise _gateway().GatewayInputError(f"TASK_CARD_BINDING_INVALID:{exc}") from exc
        if (
            lifecycle_identity.get("contract_kind") != ContractKind.TRACKED_TASK_CARD.value
            or canonical_relative_path != task_card_path
            or lifecycle_identity.get("task_card_hash") != task_card_hash
        ):
            raise _gateway().GatewayInputError("TASK_CARD_BINDING_MISMATCH")
        verified_task_card = VerifiedTaskCardIdentity(
            task_id=task_id,
            task_card_path=task_card_path,
            canonical_task_card_path=str(canonical_card_path),
            task_card_hash=task_card_hash,
        )
        # The expected-evidence universe comes only from the hashed card,
        # never from a tool argument (#2181).
        try:
            card_bytes = canonical_card_path.read_bytes()
        except OSError as exc:
            raise _gateway().GatewayInputError(f"TASK_CARD_BINDING_INVALID:{exc}") from exc
        if hashlib.sha256(card_bytes).hexdigest() != task_card_hash:
            raise _gateway().GatewayInputError("TASK_CARD_BINDING_MISMATCH")
        try:
            card_universe = parse_task_card_expected_evidence(card_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _gateway().GatewayInputError(f"TASK_CARD_BINDING_INVALID:{exc}") from exc
        evidence_binding: dict[str, Any] = (
            {"expected_evidence": card_universe, "core_envelope_required": True}
            if card_universe is not None
            else {}
        )
        try:
            internal = _gateway().build_canonical_planner_admission(
                task_id=task_id,
                task_text=what,
                allowed_files=tuple(allowed),
                verifier_command=tuple(verifiers),
                task_card_identity=verified_task_card,
                # Route facts and codeintel describe the repository the Target is cut from.
                **({"route_facts_repo_root": external_root} if external_root is not None else {}),
            )
        except (TypeError, ValueError, RuntimeError) as exc:
            raise _gateway().GatewayInputError(f"WORKFORCE_INTERNAL_BINDING_INVALID:{exc}") from exc
        planner_output = internal["planner_output"]
        demands = internal["workforce_demands"]
        admission = internal["workforce_admission"]
        dispatch_binding = dict(internal["binding"])
        for field, expected in (
            ("planner_output", planner_output),
            ("workforce_demands", demands),
            ("workforce_admission", admission),
        ):
            supplied = arguments.get(field)
            if supplied is not None and supplied != expected:
                raise _gateway().GatewayInputError(f"WORKFORCE_CALLER_EVIDENCE_MISMATCH:{field}")
        requested_worker = str(arguments.get("worker") or "").strip().lower()
        if requested_worker and requested_worker != "auto" and requested_worker not in {
            dispatch_binding["worker_id"].lower(), dispatch_binding["provider"].lower(),
        }:
            raise _gateway().GatewayInputError("WORKFORCE_ADMISSION_WORKER_MISMATCH")
        for field in ("provider", "model"):
            supplied = str(arguments.get(field) or "").strip()
            if supplied and supplied != dispatch_binding[field]:
                raise _gateway().GatewayInputError(f"WORKFORCE_ADMISSION_{field.upper()}_MISMATCH")
        provider = dispatch_binding["provider"]
        model = dispatch_binding["model"]
        worker_id = dispatch_binding["worker_id"]
        try:
            validate_task_card_binding(
                contract,
                card_request,
                is_ephemeral=bool(getattr(self.service, "ephemeral", False)),
            )
            current_identity = resolve_lifecycle_identity(
                contract,
                card_request,
                is_ephemeral=bool(getattr(self.service, "ephemeral", False)),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise _gateway().GatewayInputError(f"TASK_CARD_DRIFT:{exc}") from exc
        if (
            current_identity.get("task_card_path") != str(canonical_card_path)
            or current_identity.get("task_card_hash") != task_card_hash
        ):
            raise _gateway().GatewayInputError("TASK_CARD_DRIFT")
        preflight = self._provider_preflight({"provider": provider, "model": model})
        ready, blocker = self._provider_execution_ready(
            preflight,
            provider=provider,
            model=model if dispatch_binding is not None else None,
        )
        if not ready:
            detail = blocker or "WORKER_PREFLIGHT_FAILED"
            if preflight.get("next_action"):
                detail = f"{detail}:{preflight['next_action']}"
            raise _gateway().GatewayInputError(detail)
        readiness_binding = {
            "provider_probe_evidence_hash": self._exact_hash(
                preflight.get("probe_evidence_hash"),
                "provider_probe_evidence_hash",
                64,
            ),
            "provider_binary_path": _gateway()._text(
                preflight.get("binary_path"),
                "provider_binary_path",
                max_length=1024,
            ),
            "provider_binary_sha256": self._exact_hash(
                preflight.get("binary_sha256"),
                "provider_binary_sha256",
                64,
            ),
            "provider_cli_version_sha256": self._exact_hash(
                preflight.get("cli_version_sha256"),
                "provider_cli_version_sha256",
                64,
            ),
            "provider_probe_expires_at": _gateway()._text(
                preflight.get("probe_expires_at"),
                "provider_probe_expires_at",
                max_length=128,
            ),
            "provider_authentication_evidence": str(
                preflight.get("authentication_evidence") or "local_provider_no_auth_required"
            ),
        }
        bound = self._canonical_request(
            task_id, what, why, allowed, verifiers, target_head,
            contract_binding=contract_binding,
            **external_request,
        )
        protected_contracts = ["repository-authority-change.v1"] if authority_confirmation else []
        bound.update({"provider": provider, "model": model, "worker": provider, "worker_id": worker_id,
                      "execution_lane": "ISOLATED_TARGET", "primary_agent": False,
                      "worker_candidate_ingress": True,
                      "protected_contracts": protected_contracts})
        bound["workforce_demands"] = demands
        bound["workforce_admission"] = admission
        bound["planner_output"] = planner_output
        bound["task_card_required"] = True
        bound["lifecycle_identity_required"] = True
        bound.update(readiness_binding)
        bound.update(evidence_binding)
        if rie_identity is not None:
            bound["rie_knowledge_identity"] = rie_identity
        if codeintel_lookup is not None:
            bound["codeintel_lookup"] = codeintel_lookup
        if authority_confirmation:
            bound["authority_change_candidate_confirmation"] = True
        if fail_to_pass_required:
            bound["fail_to_pass_required"] = True
        action = build_action_envelope(
            task_id=task_id, action_type=LifecycleActionType.TASK_RUN,
            request=bound, tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=target_head, allowed_paths=allowed, mutation=True,
            task_card_path=task_card_path, task_card_hash=task_card_hash,
            contract_kind=ContractKind.TRACKED_TASK_CARD,
            contract_hash=None,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.TARGET,
        ).model_dump(mode="json")
        bound.update({
            "attempt_id": action["attempt_id"], "action_id": action["action_id"],
            "idempotency_key": action["idempotency_key"],
            "action_type": action["action_type"],
        })
        canonical_dispatch_envelope = build_canonical_dispatch_envelope(
            planner_output,
            dispatch_binding,
            task_id=task_id,
            attempt_id=str(bound["attempt_id"]),
            task_card_path=task_card_path,
            task_card_hash=task_card_hash,
        ).to_dict()
        bound["canonical_dispatch_envelope"] = canonical_dispatch_envelope
        action = build_action_envelope(
            task_id=task_id, action_type=LifecycleActionType.TASK_RUN,
            request=bound, tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION,
            expected_head=target_head, allowed_paths=allowed, mutation=True,
            task_card_path=task_card_path, task_card_hash=task_card_hash,
            contract_kind=ContractKind.TRACKED_TASK_CARD,
            contract_hash=None,
            permission_profile=PermissionProfile.CANDIDATE,
            mutation_domain=MutationDomain.TARGET,
            attempt_id=bound["attempt_id"], action_id=bound["action_id"],
            idempotency_key=bound["idempotency_key"],
        ).model_dump(mode="json")
        request = self._canonical_request(
            task_id, what, why, allowed, verifiers, target_head,
            action=action, contract_binding=contract_binding,
            bound_action_request=bound,
            **external_request,
        )
        request["request_hash"] = action["request_hash"]
        request.update({"provider": provider, "model": model, "worker": provider, "worker_id": worker_id,
                        "execution_lane": "ISOLATED_TARGET", "primary_agent": False,
                        "worker_candidate_ingress": True,
                        "task_card_required": True,
                        "lifecycle_identity_required": True})
        request["workforce_demands"] = demands
        request["workforce_admission"] = admission
        request["planner_output"] = planner_output
        request["canonical_dispatch_envelope"] = canonical_dispatch_envelope
        request.update(readiness_binding)
        request.update(evidence_binding)
        if rie_identity is not None:
            request["rie_knowledge_identity"] = dict(rie_identity)
        if codeintel_lookup is not None:
            request["codeintel_lookup"] = dict(codeintel_lookup)
        if authority_confirmation:
            request["authority_change_candidate_confirmation"] = True
        if fail_to_pass_required:
            request["fail_to_pass_required"] = True
        request["protected_contracts"] = protected_contracts
        current_head = self._exact_hash(_gateway()._git("rev-parse", "HEAD").strip(), "current_head", 40)
        if current_head != head:
            raise _gateway().GatewayInputError("HEAD_DRIFT")
        current_target_head = current_head
        if external is not None:
            try:
                current_target_head = external_target_head(external.repo_root)
            except ExternalTargetError as exc:
                raise _gateway().GatewayInputError(str(exc)) from exc
            if current_target_head != target_head:
                raise _gateway().GatewayInputError("EXTERNAL_TARGET_HEAD_DRIFT")
        _gateway().pre_action_guard(action, request=request, current_head=current_target_head, tool_manifest_hash=_gateway().TOOL_MANIFEST_REVISION)
        result = self.service.submit_task(request)
        payload = dict(result or {})
        payload.update({"schema": "nexus.worker_candidate.v1", "worker_id": worker_id,
                        "provider": provider, "model": model, "preflight": preflight,
                        "candidate_only": True})
        return payload

    def _model_calibration_evidence(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Read-only calibration-evidence query.  Never Workforce Admission.

        Resolves one lineage by lineage_id OR by exact provider+model execution
        identity.  Unknown or ambiguous lineage fails closed.  The action does
        not modify any file, grant admission, select a route, or call a
        provider.
        """
        lineage_id = str(arguments.get("lineage_id") or "").strip()
        provider = str(arguments.get("provider") or "").strip()
        model = str(arguments.get("model") or "").strip()
        if lineage_id and (provider or model):
            raise _gateway().GatewayInputError(
                "nexus_model_calibration_evidence accepts lineage_id OR exact provider+model, not both"
            )
        if bool(provider) != bool(model):
            raise _gateway().GatewayInputError(
                "nexus_model_calibration_evidence requires provider and model together"
            )
        if lineage_id:
            try:
                return self._calibration_planner.evidence_bundle(lineage_id=lineage_id)
            except LineageResolutionError as exc:
                raise _gateway().GatewayInputError(str(exc)) from exc
        if provider and model:
            try:
                return self._calibration_planner.evidence_bundle(provider=provider, model=model)
            except LineageResolutionError as exc:
                raise _gateway().GatewayInputError(str(exc)) from exc
        raise _gateway().GatewayInputError(
            "nexus_model_calibration_evidence requires lineage_id OR exact provider+model"
        )

    def _model_calibration_plan(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Read-only minimum-requalification plan.  Never Workforce Admission.

        Plans reuse still-valid lower-tier semantic evidence instead of
        restarting from L1.  The action does not modify any file, grant
        admission, select a route, start a model call, promote a model, or
        change runtime state.
        """
        provider = str(arguments.get("provider") or "").strip()
        model = str(arguments.get("model") or "").strip()
        target_role = _gateway()._text(arguments.get("target_role"), "target_role", max_length=256)
        if not provider or not model:
            raise _gateway().GatewayInputError("nexus_model_calibration_plan requires provider and model")
        change_kind = str(arguments.get("change_kind") or "").strip().lower() or None
        if change_kind is not None and change_kind not in CHANGE_KIND_VALUES:
            raise _gateway().GatewayInputError(
                f"change_kind must be one of {', '.join(CHANGE_KIND_VALUES)}"
            )
        description = str(arguments.get("description") or "").strip()[:512]
        try:
            return self._calibration_planner.build_calibration_plan(
                provider=provider,
                model=model,
                target_role=target_role,
                change_kind=change_kind,
                description=description,
            ).to_dict()
        except LineageResolutionError as exc:
            raise _gateway().GatewayInputError(str(exc)) from exc
    # fmt: on
