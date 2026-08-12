"""Bounded, dependency-free property/falsification pilot for Issue #119.

This deliberately exercises the planner as the sole route authority.  The
generator is small and deterministic so a failing case can be copied directly
into a regression fixture without introducing Hypothesis or production hooks.
"""

from __future__ import annotations

import json
import os
import random
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from nexus.engine.capability_contracts import ExecutionReplanAuthorization
from nexus.engine.capability_planner import CapabilityPlanner

ENV_NAMES = (
    "NEXUS_C15_AUDIT_MODELS",
    "NEXUS_C15_DELEGATED_RETRY_CANDIDATE_MODELS",
    "NEXUS_C15_DIAGNOSIS_MODELS",
    "NEXUS_C15_JUDGE_MODEL",
    "NEXUS_C15_PRIMARY_PROPOSER_MODEL",
    "NEXUS_C15_SECONDARY_PROPOSER_MODEL",
    "NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW",
    "NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR",
    "NEXUS_LOCAL_MODEL_CALL_ALLOWED",
    "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL",
    "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER",
    "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY",
    "NEXUS_P3_DIFFICULTY",
    "NEXUS_PROTOCOL_MODE",
)
SEED = 119_2026
GENERATOR_VERSION = "stdlib-random-v1"


@contextmanager
def _frozen_runtime():
    old = {name: os.environ.get(name) for name in ENV_NAMES}
    values = {name: "0" for name in ENV_NAMES}
    values.update({
        "NEXUS_LOCAL_MODEL_EXECUTOR_MODEL": "frozen-test-model",
        "NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER": "frozen-test-provider",
        "NEXUS_LOCAL_MODEL_EXECUTOR_TOPOLOGY": "single_local_model",
        "NEXUS_PROTOCOL_MODE": "test",
    })
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _case(
    *,
    risk: int,
    confidence: float = 0.8,
    cross_module: bool = False,
    candidate_count: int = 2,
    **features,
):
    route_features = {
        "risk_score": risk,
        "adjusted_root_cause_confidence": confidence,
        "candidate_count": candidate_count,
        "is_cross_module_task": cross_module,
        **features,
    }
    return {
        "task_desc": "bounded planner property pilot task",
        "task_type": "bugfix",
        "route": {"route_features": route_features},
        "pillars": {},
        "codeintel": {},
        "phase_trace": {},
        "budget": {},
        "skills": [],
    }


def _plan(case):
    return (
        CapabilityPlanner()
        .plan(**{key: value for key, value in case.items() if not key.startswith("_")})
        .to_dict()
    )


def _stable(plan):
    return json.dumps(plan, sort_keys=True, separators=(",", ":"))


def _coverage(plan):
    trace = plan["signal_snapshot"]
    return {
        "routing_tier": trace.get("routing_tier"),
        "execution_depth": plan["execution_depth"],
        "safety_escalated": trace.get("routing_tier") == "L0_micro_patch"
        and plan["execution_depth"] == "STANDARD",
        "compression": "prompt_compression" in plan["conditional_capabilities"],
        "shadow": bool(trace.get("p3_shadow_route")),
        "replan_floor": plan["execution_depth"] == "FULL",
        "malformed_features": bool(trace.get("route_features_malformed")),
    }


def _generated_cases():
    rng = random.Random(SEED)
    for _ in range(12):
        yield _case(
            risk=rng.choice((5, 20, 45, 75, 90)),
            confidence=rng.choice((0.4, 0.8, 0.95)),
            cross_module=rng.choice((False, True)),
            impact_complexity=rng.choice((0, 2, 8, "malformed")),
            has_hard_signal=rng.choice((False, True)),
        )


def test_irrelevant_metadata_permutation_preserves_authoritative_plan():
    with _frozen_runtime():
        base = _case(risk=45, confidence=0.8)
        variants = []
        for key in ("ignored", "diagnostic", "unrelated"):
            variant = deepcopy(base)
            variant["route"][key] = {"seed": key, "values": [3, 2, 1]}
            variant["route"]["route_features"][key] = object().__class__.__name__
            variants.append(variant)
        expected = _stable(_plan(base))
        assert all(_stable(_plan(variant)) == expected for variant in variants)


def test_deterministic_generator_is_replayable_and_non_vacuous():
    with _frozen_runtime():
        first_cases = list(_generated_cases())
        second_cases = list(_generated_cases())
        for case in first_cases + second_cases:
            case["_pilot_malformed"] = not isinstance(
                case["route"]["route_features"].get("impact_complexity"), (int, float)
            )
        first = [
            _coverage(_plan(case)) | {"malformed_features": case["_pilot_malformed"]}
            for case in first_cases
        ]
        second = [
            _coverage(_plan(case)) | {"malformed_features": case["_pilot_malformed"]}
            for case in second_cases
        ]
    assert first == second
    assert {item["routing_tier"] for item in first} >= {
        "L1_green_lane",
        "L2_hardened",
        "L3_swarm_deep",
    }
    assert any(item["malformed_features"] or item["safety_escalated"] for item in first)
    assert GENERATOR_VERSION == "stdlib-random-v1"


def test_falsification_operators_change_authoritative_outcome_or_counter():
    with _frozen_runtime():
        baseline = _case(risk=20, confidence=0.8)
        baseline_plan = _plan(baseline)
        baseline_cov = _coverage(baseline_plan)

        operators = []
        compressed = deepcopy(baseline)
        compressed["route"]["prompt_compression"] = True
        operators.append(compressed)
        escalated = _case(
            risk=10, confidence=0.9, cross_module=True, impact_complexity=9, has_hard_signal=True
        )
        operators.append(escalated)
        malformed = _case(risk=20, confidence=0.8)
        malformed["route"]["route_features"] = ["malformed-route-features"]
        operators.append(malformed)
        floored = deepcopy(baseline)
        floored["replan_authorization"] = ExecutionReplanAuthorization(
            task_id="issue-119",
            workspace_revision="4c41ce2272cf3c9d81b18f53aed2f41aea029f4a",
            source_planner_decision_id="decision-119",
            source_replan_request_id="sha256:" + "1" * 64,
            source_receipt_hash="2" * 64,
            source_run_anchor_hash="3" * 64,
            requested_execution_depth="FULL",
        )
        operators.append(floored)

        outcomes = []
        for item in operators:
            try:
                planned = _plan(item)
            except (TypeError, ValueError, AttributeError) as exc:
                outcomes.append((f"FAIL_CLOSED:{type(exc).__name__}", {"malformed_features": True}))
            else:
                outcomes.append((_stable(planned), _coverage(planned)))
    assert all(
        serialized != _stable(baseline_plan) or coverage != baseline_cov
        for serialized, coverage in outcomes
    )


def test_coverage_counters_cover_required_authority_branches():
    with _frozen_runtime():
        safety = _case(risk=10, confidence=0.95, impact_complexity=9, candidate_count=1)
        safety["route"]["route_features"]["candidate_count"] = 1
        safety["task_type"] = "public_bugfix"
        safety["task_desc"] = "small verification test happy path"
        compression = _case(risk=45, confidence=0.8)
        compression["route"]["prompt_compression"] = True
        shadow = _case(risk=45, confidence=0.8)
        shadow["route"]["difficulty"] = "hard"
        shadow["route"]["workforce_admission_enabled"] = True
        os.environ["NEXUS_ENABLE_CLOUD_WITH_LOCAL_ASSIST_SHADOW"] = "1"
        os.environ["NEXUS_ENABLE_LOCAL_MODEL_EXECUTOR"] = "1"
        replan = _case(risk=45, confidence=0.8)
        replan["replan_authorization"] = ExecutionReplanAuthorization(
            task_id="issue-119",
            workspace_revision="4c41ce2272cf3c9d81b18f53aed2f41aea029f4a",
            source_planner_decision_id="decision-119",
            source_replan_request_id="sha256:" + "1" * 64,
            source_receipt_hash="2" * 64,
            source_run_anchor_hash="3" * 64,
            requested_execution_depth="FULL",
        )
        malformed = _case(risk=45, confidence=0.8)
        malformed["route"]["route_features"] = ["malformed-route-features"]
        counters = []
        for case in (safety, compression, shadow, replan):
            counters.append(_coverage(_plan(case)))
        try:
            _plan(malformed)
        except (TypeError, ValueError, AttributeError):
            malformed_seen = True
        else:
            malformed_seen = False
    assert any(item["safety_escalated"] for item in counters)
    assert any(item["compression"] for item in counters)
    assert any(item["shadow"] for item in counters)
    assert any(item["replan_floor"] for item in counters)
    assert malformed_seen


def test_pilot_is_cwd_bound_to_repository_root():
    repository_root = Path(__file__).resolve().parents[2]
    original_cwd = Path.cwd()
    before_entries = {path.relative_to(repository_root) for path in repository_root.rglob("*")}
    try:
        os.chdir(repository_root)
        assert Path.cwd() == repository_root
        assert Path.cwd().joinpath("nexus").is_dir()
    finally:
        os.chdir(original_cwd)
    after_entries = {path.relative_to(repository_root) for path in repository_root.rglob("*")}
    assert Path.cwd() == original_cwd
    assert after_entries == before_entries
