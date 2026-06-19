"""Strategy-conditioned SurgicalPacker v0 dry-run adapter."""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class StrategyConditionedPackResult:
    strategy_id: str
    task_id: str
    target_symbols: list
    selected_context_refs: list
    forbidden_paths_checked: list
    invariants_checked: list
    abort_conditions_checked: list
    context_budget: int
    estimated_context_size: int
    packer_mode: str
    routing_changed: bool
    execution_changed: bool
    patch_apply_allowed: bool
    blocker_flags: list
    next_protocol_hint: str


class StrategyConditionedPackerError(Exception):
    pass


def dry_run_strategy_pack(
    strategy_envelope_dict: dict,
    task_id: str,
    available_context_size: int = 8000,
) -> StrategyConditionedPackResult | StrategyConditionedPackerError:
    blocker_flags = []

    if not strategy_envelope_dict:
        return StrategyConditionedPackerError("strategy_envelope is required")

    strategy_id = strategy_envelope_dict.get("strategy_id")
    if not strategy_id:
        blocker_flags.append("STRATEGY_MISSING")

    strategy_family = strategy_envelope_dict.get("strategy_family", "")
    target_symbols = strategy_envelope_dict.get("target_symbols", [])
    forbidden_paths = strategy_envelope_dict.get("forbidden_paths", [])
    invariants = strategy_envelope_dict.get("invariants", [])
    abort_conditions = strategy_envelope_dict.get("abort_conditions", [])
    model_roles = strategy_envelope_dict.get("model_roles", {})
    context_budget = strategy_envelope_dict.get("context_budget", 0)

    forbidden_violations = []
    for p in forbidden_paths:
        if isinstance(p, str) and p.startswith("/"):
            forbidden_violations.append(p)
        if isinstance(p, str) and ".." in p:
            forbidden_violations.append(p)
    if forbidden_violations:
        blocker_flags.append("FORBIDDEN_PATH_VIOLATION")

    estimated_context_size = len(json.dumps(strategy_envelope_dict))
    if estimated_context_size > context_budget:
        blocker_flags.append("CONTEXT_BUDGET_EXCEEDED")

    if not target_symbols:
        blocker_flags.append("TARGET_SYMBOL_MISSING")
    if not invariants:
        blocker_flags.append("INVARIANT_MISSING")
    if not abort_conditions:
        blocker_flags.append("ABORT_CONDITION_TRIGGERED")

    supported_roles = {"patcher", "locator", "arbiter", "selector"}
    unknown_roles = set(model_roles.keys()) - supported_roles
    if unknown_roles:
        blocker_flags.append("UNSUPPORTED_MODEL_ROLE")

    hint = "ready_for_packer_v1" if not blocker_flags else "blocked_fix_required"

    return StrategyConditionedPackResult(
        strategy_id=strategy_id or "missing",
        task_id=task_id,
        target_symbols=target_symbols,
        selected_context_refs=[],
        forbidden_paths_checked=forbidden_paths,
        invariants_checked=invariants,
        abort_conditions_checked=abort_conditions,
        context_budget=context_budget,
        estimated_context_size=estimated_context_size,
        packer_mode="dry_run",
        routing_changed=False,
        execution_changed=False,
        patch_apply_allowed=False,
        blocker_flags=blocker_flags,
        next_protocol_hint=hint,
    )
