"""StrategyEnvelope trace-only contract for Nexus repair loop."""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class StrategyEnvelope:
    strategy_id: str
    strategy_family: str
    repair_strategy: str
    search_policy: str
    model_roles: dict
    target_symbols: list
    forbidden_paths: list
    invariants: list
    abort_conditions: list
    context_budget: int
    created_at: str
    trace_only: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class StrategyEnvelopeError(Exception):
    pass


def _validate_forbidden_paths(paths: list) -> None:
    for p in paths:
        if not isinstance(p, str):
            raise StrategyEnvelopeError(f"forbidden_path must be str: {p}")
        if p.startswith("/"):
            raise StrategyEnvelopeError(f"forbidden_path must not be absolute: {p}")
        if ".." in p:
            raise StrategyEnvelopeError(f"forbidden_path must not contain '..': {p}")


def _compute_strategy_id(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def create_strategy_envelope(
    strategy_family: str,
    repair_strategy: str,
    search_policy: str,
    model_roles: dict,
    target_symbols: list,
    forbidden_paths: list,
    invariants: list,
    abort_conditions: list,
    context_budget: int,
    trace_only: bool = True,
) -> StrategyEnvelope:
    if not strategy_family:
        raise StrategyEnvelopeError("strategy_family is required")
    if not repair_strategy:
        raise StrategyEnvelopeError("repair_strategy is required")
    if not search_policy:
        raise StrategyEnvelopeError("search_policy is required")
    if not isinstance(model_roles, dict):
        raise StrategyEnvelopeError("model_roles must be dict")
    if not isinstance(target_symbols, list):
        raise StrategyEnvelopeError("target_symbols must be list")
    if not isinstance(forbidden_paths, list):
        raise StrategyEnvelopeError("forbidden_paths must be list")
    if not isinstance(invariants, list):
        raise StrategyEnvelopeError("invariants must be list")
    if not isinstance(abort_conditions, list):
        raise StrategyEnvelopeError("abort_conditions must be list")
    if not isinstance(context_budget, int) or context_budget < 0:
        raise StrategyEnvelopeError("context_budget must be non-negative int")

    _validate_forbidden_paths(forbidden_paths)

    payload = {
        "strategy_family": strategy_family,
        "repair_strategy": repair_strategy,
        "search_policy": search_policy,
        "model_roles": model_roles,
        "target_symbols": target_symbols,
        "forbidden_paths": forbidden_paths,
        "invariants": invariants,
        "abort_conditions": abort_conditions,
        "context_budget": context_budget,
    }

    strategy_id = _compute_strategy_id(payload)
    created_at = datetime.utcnow().isoformat() + "Z"

    return StrategyEnvelope(
        strategy_id=strategy_id,
        strategy_family=strategy_family,
        repair_strategy=repair_strategy,
        search_policy=search_policy,
        model_roles=model_roles,
        target_symbols=target_symbols,
        forbidden_paths=forbidden_paths,
        invariants=invariants,
        abort_conditions=abort_conditions,
        context_budget=context_budget,
        created_at=created_at,
        trace_only=trace_only,
    )
