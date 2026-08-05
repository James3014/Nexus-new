"""Immutable contracts for the single canonical planning seam.

These contracts carry planner facts and planner output only.  They do not
select a provider, model, execution lane, Target, lifecycle, or world.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from nexus.engine.capability_contracts import CapabilityPlan


_CONTEXT_SCHEMA = "nexus.canonical_task_context.v1"
_DECISION_SCHEMA = "nexus.execution_decision.v1"
_PROJECTION_SCHEMA = "nexus.canonical_execution_projection.v1"
_ROUTE_AUTHORITY = "CapabilityPlanner"
_VALID_EXECUTION_DEPTHS = frozenset({"LIGHT", "STANDARD", "FULL"})
_ALLOWED_BUDGET_KEYS = frozenset({"max_cost", "scoring"})
_ALLOWED_SCORING_KEYS = frozenset({"benefit_weight", "risk_weight", "cost_weight"})


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _forbidden_context_key(key: str) -> bool:
    normalized = key.strip().lower()
    exact = {
        "capability_stack",
        "execution_topology",
        "fallback_provider",
        "preferred_provider",
        "selected_capabilities",
        "selected_route",
    }
    forbidden_fragments = ("lane", "lifecycle", "model", "provider", "route", "target", "worker", "world")
    return normalized in exact or any(fragment in normalized for fragment in forbidden_fragments)


def _freeze_json(value: Any, *, path: str) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        raw_keys = tuple(value.keys())
        if any(not isinstance(raw_key, str) for raw_key in raw_keys):
            raise ValueError(f"canonical_context_key_must_be_string:{path}")
        for raw_key in sorted(raw_keys):
            if _forbidden_context_key(raw_key):
                raise ValueError(f"canonical_context_route_override_forbidden:{path}.{raw_key}")
            frozen[raw_key] = _freeze_json(value[raw_key], path=f"{path}.{raw_key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, path=f"{path}[]") for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float):
            json.dumps(value, allow_nan=False)
        return value
    raise ValueError(f"canonical_context_value_not_json:{path}:{type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}_required")


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"invalid_{name}")


@dataclass(frozen=True)
class CanonicalTaskContext:
    schema: str = _CONTEXT_SCHEMA
    task_id: str = ""
    task_type: str = ""
    task_desc: str = ""
    route_features: Mapping[str, Any] = field(default_factory=dict)
    pillars: Mapping[str, Any] = field(default_factory=dict)
    codeintel: Mapping[str, Any] = field(default_factory=dict)
    phase_trace: Mapping[str, Any] = field(default_factory=dict)
    budget: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != _CONTEXT_SCHEMA:
            raise ValueError(f"invalid_canonical_task_context_schema:{self.schema}")
        _require_text(self.task_id, "task_id")
        _require_text(self.task_type, "task_type")
        _require_text(self.task_desc, "task_desc")
        for name in ("route_features", "pillars", "codeintel", "phase_trace", "budget"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ValueError(f"{name}_must_be_mapping")
            object.__setattr__(self, name, _freeze_json(value, path=name))
        for key in self.budget:
            if key not in _ALLOWED_BUDGET_KEYS:
                raise ValueError(f"canonical_context_budget_key_forbidden:{key}")
        scoring = self.budget.get("scoring", {})
        if not isinstance(scoring, Mapping):
            raise ValueError("canonical_context_scoring_must_be_mapping")
        for key in scoring:
            if key not in _ALLOWED_SCORING_KEYS:
                raise ValueError(f"canonical_context_scoring_key_forbidden:{key}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_desc": self.task_desc,
            "route_features": _thaw_json(self.route_features),
            "pillars": _thaw_json(self.pillars),
            "codeintel": _thaw_json(self.codeintel),
            "phase_trace": _thaw_json(self.phase_trace),
            "budget": _thaw_json(self.budget),
        }

    @property
    def context_hash(self) -> str:
        return _canonical_hash(self.to_dict())

    def planner_inputs(self) -> dict[str, Any]:
        return {
            "task_desc": self.task_desc,
            "task_type": self.task_type,
            "route": {"route_features": _thaw_json(self.route_features)},
            "pillars": _thaw_json(self.pillars),
            "codeintel": _thaw_json(self.codeintel),
            "phase_trace": _thaw_json(self.phase_trace),
            "budget": _thaw_json(self.budget),
        }


@dataclass(frozen=True)
class ExecutionDecision:
    schema: str
    task_id: str
    context_hash: str
    plan_hash: str
    authority: str
    plan_schema_version: str
    planner_mode: str
    score: float
    selected_capabilities: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    conditional_capabilities: tuple[str, ...]
    pending_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    constraints: tuple[str, ...]
    execution_depth: str
    fallback_policy: str = "fail_closed"

    def __post_init__(self) -> None:
        if self.schema != _DECISION_SCHEMA:
            raise ValueError(f"invalid_execution_decision_schema:{self.schema}")
        _require_text(self.task_id, "task_id")
        _require_sha256(self.context_hash, "context_hash")
        _require_sha256(self.plan_hash, "plan_hash")
        if self.authority != _ROUTE_AUTHORITY:
            raise ValueError("execution_decision_authority_must_be_CapabilityPlanner")
        _require_text(self.plan_schema_version, "plan_schema_version")
        _require_text(self.planner_mode, "planner_mode")
        if self.execution_depth not in _VALID_EXECUTION_DEPTHS:
            raise ValueError(f"invalid_execution_depth:{self.execution_depth}")
        if self.fallback_policy != "fail_closed":
            raise ValueError("execution_decision_fallback_must_fail_closed")
        for name in (
            "selected_capabilities",
            "required_capabilities",
            "conditional_capabilities",
            "pending_capabilities",
            "forbidden_capabilities",
            "constraints",
        ):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))

    @classmethod
    def from_plan(cls, context: CanonicalTaskContext, plan: CapabilityPlan) -> "ExecutionDecision":
        return cls(
            schema=_DECISION_SCHEMA,
            task_id=context.task_id,
            context_hash=context.context_hash,
            plan_hash=_canonical_hash(plan.to_dict()),
            authority=_ROUTE_AUTHORITY,
            plan_schema_version=plan.schema_version,
            planner_mode=plan.planner_mode,
            score=float(plan.score),
            selected_capabilities=tuple(plan.selected_capabilities),
            required_capabilities=tuple(plan.required_capabilities),
            conditional_capabilities=tuple(plan.conditional_capabilities),
            pending_capabilities=tuple(plan.pending_capabilities),
            forbidden_capabilities=tuple(plan.forbidden_capabilities),
            constraints=tuple(plan.constraints),
            execution_depth=plan.execution_depth,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "context_hash": self.context_hash,
            "plan_hash": self.plan_hash,
            "authority": self.authority,
            "plan_schema_version": self.plan_schema_version,
            "planner_mode": self.planner_mode,
            "score": self.score,
            "selected_capabilities": list(self.selected_capabilities),
            "required_capabilities": list(self.required_capabilities),
            "conditional_capabilities": list(self.conditional_capabilities),
            "pending_capabilities": list(self.pending_capabilities),
            "forbidden_capabilities": list(self.forbidden_capabilities),
            "constraints": list(self.constraints),
            "execution_depth": self.execution_depth,
            "fallback_policy": self.fallback_policy,
        }

    @property
    def decision_hash(self) -> str:
        return _canonical_hash(self.to_dict())


@dataclass(frozen=True)
class CanonicalExecutionProjection:
    schema: str
    task_id: str
    context_hash: str
    decision_hash: str
    plan_hash: str
    execution_decision_authority: str
    selected_capabilities: tuple[str, ...]
    constraints: tuple[str, ...]
    execution_depth: str
    fallback_policy: str = "fail_closed"

    def __post_init__(self) -> None:
        if self.schema != _PROJECTION_SCHEMA:
            raise ValueError(f"invalid_canonical_execution_projection_schema:{self.schema}")
        _require_text(self.task_id, "task_id")
        _require_sha256(self.context_hash, "context_hash")
        _require_sha256(self.decision_hash, "decision_hash")
        _require_sha256(self.plan_hash, "plan_hash")
        if self.execution_decision_authority != _ROUTE_AUTHORITY:
            raise ValueError("projection_authority_must_be_CapabilityPlanner")
        if self.execution_depth not in _VALID_EXECUTION_DEPTHS:
            raise ValueError(f"invalid_execution_depth:{self.execution_depth}")
        if self.fallback_policy != "fail_closed":
            raise ValueError("projection_fallback_must_fail_closed")
        object.__setattr__(self, "selected_capabilities", tuple(str(item) for item in self.selected_capabilities))
        object.__setattr__(self, "constraints", tuple(str(item) for item in self.constraints))

    @classmethod
    def from_decision(cls, decision: ExecutionDecision) -> "CanonicalExecutionProjection":
        return cls(
            schema=_PROJECTION_SCHEMA,
            task_id=decision.task_id,
            context_hash=decision.context_hash,
            decision_hash=decision.decision_hash,
            plan_hash=decision.plan_hash,
            execution_decision_authority=decision.authority,
            selected_capabilities=decision.selected_capabilities,
            constraints=decision.constraints,
            execution_depth=decision.execution_depth,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "context_hash": self.context_hash,
            "decision_hash": self.decision_hash,
            "plan_hash": self.plan_hash,
            "execution_decision_authority": self.execution_decision_authority,
            "selected_capabilities": list(self.selected_capabilities),
            "constraints": list(self.constraints),
            "execution_depth": self.execution_depth,
            "fallback_policy": self.fallback_policy,
        }

    @property
    def projection_hash(self) -> str:
        return _canonical_hash(self.to_dict())


def validate_canonical_execution_binding(
    context: CanonicalTaskContext,
    decision: ExecutionDecision,
    projection: CanonicalExecutionProjection,
) -> None:
    if decision.task_id != context.task_id or decision.context_hash != context.context_hash:
        raise ValueError("execution_decision_context_binding_mismatch")
    if projection.task_id != decision.task_id:
        raise ValueError("projection_task_binding_mismatch")
    if projection.context_hash != context.context_hash:
        raise ValueError("projection_context_binding_mismatch")
    if projection.decision_hash != decision.decision_hash:
        raise ValueError("projection_decision_binding_mismatch")
    if projection.plan_hash != decision.plan_hash:
        raise ValueError("projection_plan_binding_mismatch")
    if projection.execution_decision_authority != decision.authority:
        raise ValueError("projection_authority_binding_mismatch")
    if projection.selected_capabilities != decision.selected_capabilities:
        raise ValueError("projection_capabilities_binding_mismatch")
    if projection.constraints != decision.constraints:
        raise ValueError("projection_constraints_binding_mismatch")
    if projection.execution_depth != decision.execution_depth:
        raise ValueError("projection_execution_depth_binding_mismatch")
