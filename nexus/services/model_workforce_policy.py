from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import yaml

from nexus.contracts.workforce_admission import (
    AdmissionDecision,
    WorkforceAdmissionDecision,
    WorkforceAdmissionRequest,
    WorkforcePolicySnapshot,
    WorkforceWorker,
    parse_autonomy_rank,
)


class WorkforcePolicyError(Exception):
    """Base exception for workforce policy operations."""


class WorkforcePolicyValidationError(WorkforcePolicyError):
    """Raised when workforce policy fails schema or semantic validation."""


NON_ADMISSIBLE_STATES: set[str] = {
    "REGISTERED_BLOCKED",
    "QUARANTINED",
    "DISABLED_PROTOCOL_FAILURE",
    "DISABLED_RESOURCE_RISK",
    "INSTALLED_NOT_CONNECTED",
    "NOT_A_MODEL_WORKER",
}

MUTATION_FORBIDDEN_ACTIONS: set[str] = {
    "direct_workspace_mutation",
    "code_mutation",
    "direct_apply",
}


def compute_policy_hash(parsed_data: dict[str, Any]) -> str:
    """Compute deterministic semantic SHA-256 hash from canonical parsed policy JSON.
    
    Does not hash load time or path.
    """
    # Create clean copy without transient metadata
    clean_data = json.loads(json.dumps(parsed_data, default=str))
    canonical_json = json.dumps(clean_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def get_freshness_evidence(last_verified_str: str) -> dict[str, Any]:
    """Calculate verified age in days and check for future dates without blocking on age."""
    try:
        verified_date = datetime.date.fromisoformat(str(last_verified_str))
        today = datetime.date.today()
        age_days = (today - verified_date).days
        is_future = verified_date > today
        return {
            "last_verified": str(last_verified_str),
            "verified_age_days": age_days,
            "is_future": is_future,
        }
    except Exception:
        return {
            "last_verified": str(last_verified_str),
            "verified_age_days": None,
            "is_future": False,
        }


class WorkforcePolicyLoader:
    """Fail-closed loader and admission evaluator for the model workforce policy."""

    DEFAULT_POLICY_PATH = Path("nexus/config/model_workforce.yaml")

    def __init__(self, policy_path: str | Path | None = None) -> None:
        if policy_path is None:
            self.policy_path = Path(self.DEFAULT_POLICY_PATH)
        else:
            self.policy_path = Path(policy_path)
        self._cached_snapshot: WorkforcePolicySnapshot | None = None

    def load(self) -> WorkforcePolicySnapshot:
        """Load and validate the policy file.
        
        Raises WorkforcePolicyValidationError if file is missing or invalid.
        """
        if not self.policy_path.is_file():
            raise WorkforcePolicyValidationError(f"Policy file not found: {self.policy_path}")

        try:
            content = self.policy_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception as exc:
            raise WorkforcePolicyValidationError(f"Failed to parse YAML from {self.policy_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise WorkforcePolicyValidationError(f"Policy content in {self.policy_path} must be a YAML object/dict")

        # 1. Schema check
        if data.get("schema") != "nexus.model_workforce.v1":
            raise WorkforcePolicyValidationError(
                f"Invalid schema: expected 'nexus.model_workforce.v1', got '{data.get('schema')}'"
            )

        # 2. Status check
        if data.get("status") != "current":
            raise WorkforcePolicyValidationError(
                f"Invalid status: expected 'current', got '{data.get('status')}'"
            )

        # 3. Route authority check
        if data.get("route_authority") != "CapabilityPlanner":
            raise WorkforcePolicyValidationError(
                f"Invalid route_authority: expected 'CapabilityPlanner', got '{data.get('route_authority')}'"
            )

        # 4. ISO last_verified check (must not be in the future)
        last_verified_raw = data.get("last_verified")
        if not last_verified_raw:
            raise WorkforcePolicyValidationError("Missing last_verified date")
        try:
            verified_date = datetime.date.fromisoformat(str(last_verified_raw))
        except ValueError as exc:
            raise WorkforcePolicyValidationError(f"Invalid ISO last_verified date: {last_verified_raw}") from exc

        today = datetime.date.today()
        if verified_date > today:
            raise WorkforcePolicyValidationError(
                f"last_verified date '{last_verified_raw}' is in the future relative to '{today}'"
            )

        # 5. Declared states check
        declared_states_raw = data.get("states")
        if not isinstance(declared_states_raw, list) or not declared_states_raw:
            raise WorkforcePolicyValidationError("Policy must define a non-empty list of declared 'states'")
        declared_states = tuple(str(s) for s in declared_states_raw)

        # 6. Workers check
        workers_raw = data.get("workers")
        if not isinstance(workers_raw, dict) or not workers_raw:
            raise WorkforcePolicyValidationError("Policy must define a non-empty 'workers' dictionary")

        parsed_workers: dict[str, WorkforceWorker] = {}
        seen_identities: set[tuple[str, str]] = set()

        for w_id, w_data in workers_raw.items():
            if not isinstance(w_data, dict):
                raise WorkforcePolicyValidationError(f"Worker '{w_id}' definition must be a dictionary")

            # Check required worker fields
            provider = w_data.get("provider")
            model = w_data.get("model")
            w_state = w_data.get("state")
            availability = w_data.get("availability")
            roles_raw = w_data.get("roles")

            if not provider or not isinstance(provider, str):
                raise WorkforcePolicyValidationError(f"Worker '{w_id}' missing or invalid 'provider'")
            if not model or not isinstance(model, str):
                raise WorkforcePolicyValidationError(f"Worker '{w_id}' missing or invalid 'model'")
            if not w_state or not isinstance(w_state, str):
                raise WorkforcePolicyValidationError(f"Worker '{w_id}' missing or invalid 'state'")
            if not availability or not isinstance(availability, str):
                raise WorkforcePolicyValidationError(f"Worker '{w_id}' missing or invalid 'availability'")
            if not isinstance(roles_raw, list):
                raise WorkforcePolicyValidationError(f"Worker '{w_id}' missing or invalid 'roles' list")

            if w_state not in declared_states:
                raise WorkforcePolicyValidationError(
                    f"Worker '{w_id}' state '{w_state}' not in declared states"
                )

            # Check unique provider+model identity
            identity = (provider, model)
            if identity in seen_identities:
                raise WorkforcePolicyValidationError(
                    f"Duplicate provider+model identity: {provider} / {model} (worker: {w_id})"
                )
            seen_identities.add(identity)

            parsed_workers[w_id] = WorkforceWorker(
                worker_id=w_id,
                provider=provider,
                model=model,
                state=w_state,
                availability=availability,
                roles=tuple(str(r) for r in roles_raw),
                autonomy=w_data.get("autonomy"),
                preferred_context=w_data.get("preferred_context"),
                benchmark_ref=w_data.get("benchmark_ref"),
                requires=tuple(str(r) for r in w_data.get("requires", [])),
                forbidden_claims=tuple(str(c) for c in w_data.get("forbidden_claims", [])),
                forbidden_actions=tuple(str(a) for a in w_data.get("forbidden_actions", [])),
                reenable_requires=tuple(str(r) for r in w_data.get("reenable_requires", [])),
                current_assignment=w_data.get("current_assignment"),
                cost_characteristic=w_data.get("cost_characteristic"),
                blocker=w_data.get("blocker"),
                reason=w_data.get("reason"),
            )

        # 7. Routing validation
        routing = data.get("routing")
        if not isinstance(routing, dict):
            raise WorkforcePolicyValidationError("Policy must contain a 'routing' object")
        if routing.get("blocked_or_disabled_models_must_not_be_selected") is not True:
            raise WorkforcePolicyValidationError(
                "routing.blocked_or_disabled_models_must_not_be_selected must be true"
            )
        if routing.get("experiment_only_models_require_explicit_authorization") is not True:
            raise WorkforcePolicyValidationError(
                "routing.experiment_only_models_require_explicit_authorization must be true"
            )

        # 8. Context policy validation
        context_policy = data.get("context_policy")
        if not isinstance(context_policy, dict):
            raise WorkforcePolicyValidationError("Policy must contain a 'context_policy' object")

        policy_hash = compute_policy_hash(data)

        snapshot = WorkforcePolicySnapshot(
            schema=data["schema"],
            status=data["status"],
            owner=str(data.get("owner", "")),
            last_verified=str(last_verified_raw),
            authority_document=str(data.get("authority_document", "")),
            benchmark_matrix=str(data.get("benchmark_matrix", "")),
            benchmark_harness=str(data.get("benchmark_harness", "")),
            route_authority=data["route_authority"],
            declared_states=declared_states,
            workers=parsed_workers,
            non_workers=dict(data.get("non_workers", {})),
            routing=dict(routing),
            context_policy=dict(context_policy),
            evidence_layers=dict(data.get("evidence_layers", {})),
            claim_rules=dict(data.get("claim_rules", {})),
            benchmark_snapshot=dict(data.get("benchmark_snapshot", {})),
            policy_hash=policy_hash,
        )

        self._cached_snapshot = snapshot
        return snapshot

    def admit(
        self,
        request: WorkforceAdmissionRequest,
        snapshot: WorkforcePolicySnapshot | None = None,
    ) -> WorkforceAdmissionDecision:
        """Evaluate a workforce admission request against the policy snapshot."""
        if snapshot is None:
            if self._cached_snapshot is None:
                snapshot = self.load()
            else:
                snapshot = self._cached_snapshot

        freshness = get_freshness_evidence(snapshot.last_verified)

        block_reasons: list[str] = []
        escalate_reasons: list[str] = []

        # 1. Route authorization check
        if not request.route_authorized:
            block_reasons.append("Route authorization required (route_authorized is False)")

        # 2. Worker resolution & identity check
        worker: WorkforceWorker | None = None
        if request.requested_worker_id:
            worker = snapshot.workers.get(request.requested_worker_id)
            if not worker:
                block_reasons.append(f"Unknown worker ID: '{request.requested_worker_id}'")
            else:
                if request.provider and request.provider != worker.provider:
                    block_reasons.append(
                        f"Mismatched provider: requested '{request.provider}', worker has '{worker.provider}'"
                    )
                if request.model and request.model != worker.model:
                    block_reasons.append(
                        f"Mismatched model: requested '{request.model}', worker has '{worker.model}'"
                    )
        elif request.provider and request.model:
            matches = [
                w for w in snapshot.workers.values()
                if w.provider == request.provider and w.model == request.model
            ]
            if len(matches) == 0:
                block_reasons.append(
                    f"Unknown worker for provider '{request.provider}' and model '{request.model}'"
                )
            elif len(matches) > 1:
                block_reasons.append(
                    f"Ambiguous worker match for provider '{request.provider}' and model '{request.model}'"
                )
            else:
                worker = matches[0]
        elif request.model:
            matches = [w for w in snapshot.workers.values() if w.model == request.model]
            if len(matches) == 0:
                block_reasons.append(f"Unknown worker for model '{request.model}'")
            elif len(matches) > 1:
                block_reasons.append(f"Ambiguous worker match for model '{request.model}'")
            else:
                worker = matches[0]
        else:
            block_reasons.append("Missing worker identity (requested_worker_id, provider, model are all empty)")

        # 3. Request completeness checks
        if not request.role:
            block_reasons.append("Missing requested role")
        if not request.autonomy:
            block_reasons.append("Missing requested autonomy")
        elif not parse_autonomy_level_safe(request.autonomy):
            block_reasons.append(f"Invalid requested autonomy level: '{request.autonomy}'")
        if not request.context:
            block_reasons.append("Missing requested context")

        # 4. Worker status & availability checks (if worker resolved)
        missing_controls: list[str] = []
        if worker:
            if worker.state in NON_ADMISSIBLE_STATES:
                block_reasons.append(f"Worker '{worker.worker_id}' state is non-admissible: '{worker.state}'")
            elif worker.state == "EXPERIMENT_ONLY":
                if not request.explicit_experiment_authorization:
                    block_reasons.append(
                        f"Experiment-only worker '{worker.worker_id}' requires explicit experiment authorization"
                    )
                if worker.availability != "AVAILABLE":
                    block_reasons.append(
                        f"Worker '{worker.worker_id}' availability is '{worker.availability}', required 'AVAILABLE'"
                    )
            else:
                if worker.availability != "AVAILABLE":
                    block_reasons.append(
                        f"Worker '{worker.worker_id}' availability is '{worker.availability}', required 'AVAILABLE'"
                    )

            # Controls check
            for req_ctrl in worker.requires:
                if req_ctrl not in request.provided_controls:
                    missing_controls.append(req_ctrl)
            if missing_controls:
                block_reasons.append(f"Missing required controls: {', '.join(missing_controls)}")

        # If any BLOCK reason exists, return BLOCK decision immediately
        if block_reasons:
            return WorkforceAdmissionDecision(
                schema="nexus.workforce_admission_decision.v1",
                decision=AdmissionDecision.BLOCK,
                resolved_worker_id=worker.worker_id if worker else None,
                resolved_provider=worker.provider if worker else None,
                resolved_model=worker.model if worker else None,
                requested_role=request.role,
                admitted_role=None,
                requested_autonomy=request.autonomy,
                admitted_autonomy=None,
                requested_context=request.context,
                admitted_context=None,
                autonomy_ceiling=worker.autonomy if worker else None,
                decision_reasons=tuple(block_reasons),
                required_controls=worker.requires if worker else (),
                missing_controls=tuple(missing_controls),
                policy_schema=snapshot.schema,
                policy_status=snapshot.status,
                policy_last_verified=snapshot.last_verified,
                policy_hash=snapshot.policy_hash,
                route_authority=snapshot.route_authority,
                freshness_evidence=freshness,
            )

        # At this point, worker is guaranteed to be non-None and passes basic BLOCK checks.
        assert worker is not None

        # 5. ESCALATE checks (evaluated only when BLOCK does not trigger)
        # 5a. Role check
        if request.role not in worker.roles:
            escalate_reasons.append(
                f"Requested role '{request.role}' is outside admitted roles for worker '{worker.worker_id}': {list(worker.roles)}"
            )

        # 5b. Autonomy ceiling check
        try:
            req_rank = parse_autonomy_rank(request.autonomy)
            ceiling_rank = parse_autonomy_rank(worker.autonomy)
            if req_rank > ceiling_rank:
                escalate_reasons.append(
                    f"Requested autonomy '{request.autonomy}' exceeds worker autonomy ceiling '{worker.autonomy}'"
                )
        except ValueError as exc:
            escalate_reasons.append(str(exc))

        # 5c. Context policy checks (preferred context)
        if worker.preferred_context:
            if worker.preferred_context == "nexus_bounded" and request.context == "nexus_full":
                escalate_reasons.append(
                    f"Requested context '{request.context}' exceeds worker preferred context '{worker.preferred_context}'"
                )
            elif worker.preferred_context == "tightly_bounded" and request.context in ("nexus_bounded", "nexus_full"):
                escalate_reasons.append(
                    f"Requested context '{request.context}' exceeds worker preferred context '{worker.preferred_context}'"
                )

        # 5d. Local / Ollama nexus_full check
        if worker.provider in ("ollama", "local") and request.context == "nexus_full":
            escalate_reasons.append(
                f"Local/Ollama worker '{worker.worker_id}' requested with full context ('nexus_full')"
            )

        # 5e. Observed full-context regression check
        observed_regressions = set(snapshot.context_policy.get("observed_full_context_regressions", []))
        if request.context == "nexus_full" and (
            worker.worker_id in observed_regressions or worker.benchmark_ref in observed_regressions
        ):
            escalate_reasons.append(
                f"Worker '{worker.worker_id}' has observed full-context regression when requested with 'nexus_full'"
            )

        # 5f. Physical mutation conflicts with forbidden actions
        if request.mutation_requested:
            conflicts = [act for act in worker.forbidden_actions if act in MUTATION_FORBIDDEN_ACTIONS]
            if conflicts:
                escalate_reasons.append(
                    f"Physical mutation requested but worker '{worker.worker_id}' forbids physical mutation: {conflicts}"
                )

        if escalate_reasons:
            return WorkforceAdmissionDecision(
                schema="nexus.workforce_admission_decision.v1",
                decision=AdmissionDecision.ESCALATE,
                resolved_worker_id=worker.worker_id,
                resolved_provider=worker.provider,
                resolved_model=worker.model,
                requested_role=request.role,
                admitted_role=None,
                requested_autonomy=request.autonomy,
                admitted_autonomy=None,
                requested_context=request.context,
                admitted_context=None,
                autonomy_ceiling=worker.autonomy,
                decision_reasons=tuple(escalate_reasons),
                required_controls=worker.requires,
                missing_controls=(),
                policy_schema=snapshot.schema,
                policy_status=snapshot.status,
                policy_last_verified=snapshot.last_verified,
                policy_hash=snapshot.policy_hash,
                route_authority=snapshot.route_authority,
                freshness_evidence=freshness,
            )

        # 6. ALLOW - all checks passed!
        return WorkforceAdmissionDecision(
            schema="nexus.workforce_admission_decision.v1",
            decision=AdmissionDecision.ALLOW,
            resolved_worker_id=worker.worker_id,
            resolved_provider=worker.provider,
            resolved_model=worker.model,
            requested_role=request.role,
            admitted_role=request.role,
            requested_autonomy=request.autonomy,
            admitted_autonomy=request.autonomy,
            requested_context=request.context,
            admitted_context=request.context,
            autonomy_ceiling=worker.autonomy,
            decision_reasons=("All constraints and required controls passed",),
            required_controls=worker.requires,
            missing_controls=(),
            policy_schema=snapshot.schema,
            policy_status=snapshot.status,
            policy_last_verified=snapshot.last_verified,
            policy_hash=snapshot.policy_hash,
            route_authority=snapshot.route_authority,
            freshness_evidence=freshness,
        )


def parse_autonomy_level_safe(level: str | None) -> bool:
    if level is None:
        return False
    try:
        parse_autonomy_rank(level)
        return True
    except ValueError:
        return False
