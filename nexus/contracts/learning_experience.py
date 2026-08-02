from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


LEARNING_EXPERIENCE_SCHEMA_VERSION = "nexus_learning_experience.v1"
RUNTIME_LEARNING_CLOSURE_SCHEMA = "nexus.runtime_learning_closure.v1"
RUNTIME_LEARNING_PHASE_CHAIN = ("S", "P", "D", "X", "R", "A", "C")
PHASE_CHAIN = ("S", "P", "X", "D", "R", "A", "C")
HIGH_COST_CAPABILITIES = {
    "research",
    "external_doc_scout",
    "ultra_review",
    "sandbox",
    "swarm",
    "nightshift",
    "research_control_plane",
}


CAPABILITY_TAXONOMY: dict[str, dict[str, Any]] = {
    "direct_mode": {"category": "primary_execution", "phases": ("S", "P", "X", "D", "R", "A", "C")},
    "repair_loop": {"category": "primary_execution", "phases": ("R", "A")},
    "hyper": {"category": "primary_execution", "phases": ("P", "R", "A")},
    "nightshift": {"category": "primary_execution", "phases": ("D", "R", "C")},
    "codeintel": {"category": "recon_context", "phases": ("S", "P", "X", "A")},
    "research": {"category": "recon_context", "phases": ("X", "C")},
    "research_route": {"category": "recon_context", "phases": ("S", "P", "X")},
    "research_control_plane": {"category": "recon_context", "phases": ("X", "R", "A", "C")},
    "xray": {"category": "recon_context", "phases": ("X", "D")},
    "lancedb": {"category": "recon_context", "phases": ("X",)},
    "memory": {"category": "memory_learning", "phases": ("P", "X", "C")},
    "learn_mode": {"category": "memory_learning", "phases": ("X", "A", "C")},
    "learn_scheduler": {"category": "memory_learning", "phases": ("X", "C")},
    "learn_phase_slo": {"category": "memory_learning", "phases": ("P", "X", "D", "R", "A", "C")},
    "autoreason": {"category": "reasoning_acceleration", "phases": ("D", "R", "A")},
    "judge_panel": {"category": "reasoning_acceleration", "phases": ("D", "R", "A")},
    "llm_judge_panel": {"category": "reasoning_acceleration", "phases": ("D", "R", "A")},
    "ddtree": {"category": "reasoning_acceleration", "phases": ("X", "R", "A")},
    "belief": {"category": "reasoning_acceleration", "phases": ("D", "R")},
    "autonomic_router": {"category": "reasoning_acceleration", "phases": ("P", "D")},
    "forecast_gate": {"category": "reasoning_acceleration", "phases": ("P", "D")},
    "swarm": {"category": "collaboration", "phases": ("D", "R", "A")},
    "swarm_quiet_moment": {"category": "collaboration", "phases": ("D", "R", "A")},
    "drone": {"category": "collaboration", "phases": ("R", "A")},
    "multi_agent": {"category": "collaboration", "phases": ("P", "D", "R", "A", "C")},
    "file_lock": {"category": "collaboration", "phases": ("S", "P", "D")},
    "integration_manager": {"category": "collaboration", "phases": ("C",)},
    "mempalace_gate": {"category": "governance_risk", "phases": ("S", "D", "A")},
    "policy_gate": {"category": "governance_risk", "phases": ("S", "P", "D")},
    "capability_gate": {"category": "governance_risk", "phases": ("S", "P", "D")},
    "pregate": {"category": "governance_risk", "phases": ("S", "P")},
    "plan_quality_gate": {"category": "governance_risk", "phases": ("P", "D")},
    "ultra_review": {"category": "governance_risk", "phases": ("D", "A")},
    "artifact_gate": {"category": "validation_delivery", "phases": ("A", "C")},
    "claim_gate": {"category": "validation_delivery", "phases": ("A", "C")},
    "delivery_gate": {"category": "validation_delivery", "phases": ("A", "C")},
    "acceptance_check": {"category": "validation_delivery", "phases": ("A", "C")},
    "sandbox": {"category": "validation_delivery", "phases": ("R", "A")},
    "benchmark": {"category": "self_evolution", "phases": ("C",)},
    "meta_opt": {"category": "self_evolution", "phases": ("C",)},
    "regression_guard": {"category": "self_evolution", "phases": ("A", "C")},
    "registry_sync": {"category": "productization", "phases": ("S", "C")},
    "metabolism": {"category": "productization", "phases": ("C", "S")},
    "oracle_shadow": {"category": "productization", "phases": ("P", "R", "A", "C")},
    "federation": {"category": "productization", "phases": ("X", "R", "C")},
    "ui_validator": {"category": "productization", "phases": ("A",)},
    "stress_test": {"category": "productization", "phases": ("A", "C")},
}


@dataclass(frozen=True)
class CapabilityLifecycle:
    capability: str
    category: str
    phase: str
    selected: bool
    invoked: bool
    evidence: bool
    outcome: bool
    gate_passed: bool = False
    evidence_refs: tuple[str, ...] = ()
    failure_reason: str = ""

    @property
    def funnel_complete(self) -> bool:
        return bool(self.selected and self.invoked and self.evidence and self.outcome and self.gate_passed)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"evidence_refs": list(self.evidence_refs), "funnel_complete": self.funnel_complete}


@dataclass(frozen=True)
class LearningExperience:
    experience_id: str
    task_id: str
    task_type: str
    phase_continuity: dict[str, Any]
    capability_lifecycle: tuple[CapabilityLifecycle, ...]
    gate_chain: dict[str, str]
    outcome: str
    route_decision_ref: str = ""
    s2t_trace_refs: tuple[str, ...] = ()
    learning_steward_decision: str = "shadow"
    nexus_policy_targets: tuple[str, ...] = ("route_weight", "capability_weight", "s2t_prior")
    model_training_targets: tuple[str, ...] = ("preference_pair", "reward_row")
    promotion_status: str = "shadow"
    schema_version: str = LEARNING_EXPERIENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "capability_lifecycle": [item.to_dict() for item in self.capability_lifecycle],
            "s2t_trace_refs": list(self.s2t_trace_refs),
            "nexus_policy_targets": list(self.nexus_policy_targets),
            "model_training_targets": list(self.model_training_targets),
        }


def build_runtime_learning_closure(
    *,
    task_id: str,
    attempt_id: str,
    action_id: str,
    phase_receipts: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    candidate_ref: str = "",
    outcome: str,
    terminal_evidence: dict[str, Any],
    uncertain_mutation: bool = False,
    retrieved_lesson_ids: list[str] | tuple[str, ...] = (),
    applied_lesson_ids: list[str] | tuple[str, ...] = (),
    lesson_disposition: str = "shadow",
    qualification: dict[str, Any] | None = None,
    primary_task_success: bool = False,
    learning_write_succeeded: bool = True,
) -> dict[str, Any]:
    """Build one outcome-linked learning episode without creating new storage."""

    disposition = str(lesson_disposition or "shadow")
    write_ok = bool(learning_write_succeeded)
    episode = {
        "schema": RUNTIME_LEARNING_CLOSURE_SCHEMA,
        "task_id": str(task_id),
        "attempt_id": str(attempt_id),
        "action_id": str(action_id),
        "phase_chain": list(RUNTIME_LEARNING_PHASE_CHAIN),
        "phase_receipts": list(phase_receipts),
        "candidate_ref": str(candidate_ref),
        "outcome": str(outcome),
        "terminal_evidence": dict(terminal_evidence or {}),
        "uncertain_mutation": bool(uncertain_mutation),
        "auto_replay_allowed": False,
        "retrieved_lesson_ids": [str(item) for item in retrieved_lesson_ids],
        "applied_lesson_ids": [str(item) for item in applied_lesson_ids],
        "lesson_disposition": disposition,
        "qualification": dict(qualification or {}),
        "learning_write_succeeded": write_ok,
        "primary_task_success": bool(primary_task_success and write_ok),
        "learning_blocker": "" if write_ok else "LEARNING_WRITE_FAILED",
    }
    validate_runtime_learning_closure(episode)
    return episode


def validate_runtime_learning_closure(episode: dict[str, Any]) -> None:
    required = (
        "schema", "task_id", "attempt_id", "action_id", "phase_receipts",
        "outcome", "terminal_evidence", "auto_replay_allowed", "lesson_disposition",
        "learning_write_succeeded", "primary_task_success",
    )
    missing = [field for field in required if field not in episode]
    if missing:
        raise ValueError(f"RUNTIME_LEARNING_CLOSURE_INCOMPLETE:{','.join(missing)}")
    if episode.get("schema") != RUNTIME_LEARNING_CLOSURE_SCHEMA:
        raise ValueError("RUNTIME_LEARNING_CLOSURE_SCHEMA_INVALID")
    if episode.get("auto_replay_allowed") is not False:
        raise ValueError("RUNTIME_LEARNING_AUTO_REPLAY_FORBIDDEN")
    if episode.get("uncertain_mutation") and episode.get("auto_replay_allowed"):
        raise ValueError("RUNTIME_LEARNING_UNCERTAIN_REPLAY_FORBIDDEN")
    if str(episode.get("outcome") or "").upper() in {"FAILED", "BLOCKED", "REJECTED"} and episode.get("lesson_disposition") == "graduated":
        raise ValueError("RUNTIME_LEARNING_FAILED_ATTEMPT_CANNOT_GRADUATE")
    if episode.get("lesson_disposition") == "graduated":
        qualification = episode.get("qualification") or {}
        required_qualification = ("terminal_evidence", "repeatability", "prevention_rule", "authority_qualification")
        if not episode.get("terminal_evidence") or any(not qualification.get(field) for field in required_qualification[1:]):
            raise ValueError("RUNTIME_LEARNING_QUALIFICATION_INCOMPLETE")
    if episode.get("primary_task_success") and not episode.get("learning_write_succeeded"):
        raise ValueError("RUNTIME_LEARNING_WRITE_FAILURE_CANNOT_REPORT_SUCCESS")


def learning_experience_from_dict(payload: dict[str, Any]) -> LearningExperience:
    lifecycle = tuple(
        CapabilityLifecycle(
            capability=str(item.get("capability", "unknown")),
            category=str(item.get("category", "unknown")),
            phase=str(item.get("phase", "C")),
            selected=bool(item.get("selected", False)),
            invoked=bool(item.get("invoked", False)),
            evidence=bool(item.get("evidence", False)),
            outcome=bool(item.get("outcome", False)),
            gate_passed=bool(item.get("gate_passed", False)),
            evidence_refs=tuple(str(ref) for ref in item.get("evidence_refs", []) or []),
            failure_reason=str(item.get("failure_reason", "")),
        )
        for item in payload.get("capability_lifecycle", []) or []
        if isinstance(item, dict)
    )
    return LearningExperience(
        experience_id=str(payload.get("experience_id") or "exp:unknown"),
        task_id=str(payload.get("task_id") or "unknown"),
        task_type=str(payload.get("task_type") or ""),
        phase_continuity=dict(payload.get("phase_continuity", {}) or {}),
        capability_lifecycle=lifecycle,
        gate_chain=dict(payload.get("gate_chain", {}) or {}),
        outcome=str(payload.get("outcome") or "unverified"),
        route_decision_ref=str(payload.get("route_decision_ref") or ""),
        s2t_trace_refs=tuple(str(ref) for ref in payload.get("s2t_trace_refs", []) or []),
        learning_steward_decision=str(payload.get("learning_steward_decision") or "shadow"),
        nexus_policy_targets=tuple(str(item) for item in payload.get("nexus_policy_targets", []) or ()),
        model_training_targets=tuple(str(item) for item in payload.get("model_training_targets", []) or ()),
        promotion_status=str(payload.get("promotion_status") or "shadow"),
        schema_version=str(payload.get("schema_version") or LEARNING_EXPERIENCE_SCHEMA_VERSION),
    )


def build_learning_experience(
    *,
    task_id: str,
    task_type: str = "",
    usage_trace: dict[str, Any] | None = None,
    capability_receipts: list[dict[str, Any]] | None = None,
    route_decision_ref: str = "",
    learning_steward_decision: str = "shadow",
) -> LearningExperience:
    usage = usage_trace or {}
    receipts = capability_receipts or usage.get("capability_receipts", []) or []
    phase_trace = usage.get("phase_trace", {}) if isinstance(usage.get("phase_trace"), dict) else {}
    observed = [phase for phase in PHASE_CHAIN if phase in phase_trace or phase in usage.get("phase_wall_sec", {})]
    capabilities = tuple(_lifecycle_from_receipt(item) for item in receipts if isinstance(item, dict))
    gate_chain = _gate_chain(usage)
    outcome = "verified_success" if all(gate_chain.get(key) == "pass" for key in ("artifact", "claim", "delivery")) else "unverified"
    s2t = usage.get("s2t", {}) if isinstance(usage.get("s2t"), dict) else {}
    s2t_refs = tuple(str(ref) for ref in [s2t.get("trace_path", "")] if str(ref).strip())
    experience_id = f"exp:{task_id or 'unknown'}:{abs(hash((task_id, len(capabilities), outcome))) % 10_000_000}"
    return LearningExperience(
        experience_id=experience_id,
        task_id=task_id or "unknown",
        task_type=task_type,
        phase_continuity={
            "expected": list(PHASE_CHAIN),
            "observed": observed,
            "complete": observed == list(PHASE_CHAIN),
            "broken_at": _first_missing_phase(observed),
            "phase_wall_sec": dict(usage.get("phase_wall_sec", {}) or {}),
        },
        capability_lifecycle=capabilities,
        gate_chain=gate_chain,
        outcome=outcome,
        route_decision_ref=route_decision_ref,
        s2t_trace_refs=s2t_refs,
        learning_steward_decision=learning_steward_decision,
        promotion_status="shadow" if outcome == "verified_success" else "frozen",
    )


def project_nexus_policy(experience: LearningExperience) -> dict[str, Any]:
    complete = [item.capability for item in experience.capability_lifecycle if item.funnel_complete]
    unnecessary = [item.capability for item in experience.capability_lifecycle if item.selected and not item.invoked]
    escalation = build_escalation_recommendations(experience)
    return {
        "schema_version": "nexus_policy_learning_projection.v1",
        "experience_id": experience.experience_id,
        "promotion_status": experience.promotion_status,
        "route_weight_updates": complete,
        "capability_penalties": unnecessary,
        "escalation_recommendations": escalation,
        "s2t_prior_eligible": bool(experience.s2t_trace_refs and experience.outcome == "verified_success"),
    }


def project_model_training(experience: LearningExperience) -> dict[str, Any]:
    eligible = experience.outcome == "verified_success" and experience.gate_chain.get("claim") == "pass"
    return {
        "schema_version": "nexus_model_training_projection.v1",
        "experience_id": experience.experience_id,
        "training_eligible": eligible,
        "targets": list(experience.model_training_targets) if eligible else ["hard_negative"],
        "source_trace_refs": list(experience.s2t_trace_refs),
    }


def apply_autodata_quality_gate(projection: dict[str, Any], quality_row: dict[str, Any] | None) -> dict[str, Any]:
    """Fail closed model export when trajectory quality is not training-grade."""
    gated = dict(projection)
    reasons: list[str] = []

    def fail_closed() -> None:
        gated["training_eligible"] = False
        gated["targets"] = ["hard_negative"]

    if not gated.get("source_trace_refs"):
        reasons.append("missing_s2t_trace_refs")
    if not quality_row:
        reasons.append("missing_autodata_quality_row")
        fail_closed()
        gated["autodata_gate"] = {"attached": False, "status": "not_attached"}
        gated["model_training_gate"] = {"status": "fail", "reasons": reasons}
        return gated

    eligible = bool(quality_row.get("eligible_for_training", False))
    if not eligible:
        reasons.append("autodata_not_training_eligible")
    if bool(quality_row.get("leakage_risk", False)):
        reasons.append("leakage_risk")
    if bool(quality_row.get("reward_hacking_risk", False)):
        reasons.append("reward_hacking_risk")
    quality_reasons = [str(reason) for reason in quality_row.get("reasons", []) or [] if str(reason).strip()]
    if any("leakage" in reason for reason in quality_reasons):
        reasons.append("leakage_risk")
    if any("reward_hacking" in reason for reason in quality_reasons):
        reasons.append("reward_hacking_risk")

    gated["training_eligible"] = bool(gated.get("training_eligible") and eligible)
    if reasons:
        fail_closed()
    gated["autodata_gate"] = {
        "attached": True,
        "status": "pass" if eligible and not reasons else "fail",
        "reasons": quality_reasons,
        "trajectory_steps": int(quality_row.get("trajectory_steps", quality_row.get("trajectory_step_count", 0)) or 0),
        "information_density": float(quality_row.get("information_density", 0.0) or 0.0),
    }
    gated["model_training_gate"] = {"status": "pass" if gated["training_eligible"] else "fail", "reasons": sorted(set(reasons))}
    return gated


def build_escalation_recommendations(experience: LearningExperience) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    by_capability = {item.capability: item for item in experience.capability_lifecycle}
    hyper = by_capability.get("hyper")
    if hyper and hyper.selected and hyper.invoked and not hyper.outcome:
        recommendations.append(
            {
                "from": "hyper",
                "to": "nightshift",
                "reason": "hyper_invoked_without_outcome",
            }
        )
    autoreason = by_capability.get("autoreason")
    if autoreason and autoreason.selected and not autoreason.evidence:
        recommendations.append(
            {
                "from": "autoreason",
                "to": "judge_panel",
                "reason": "autoreason_selected_without_evidence",
            }
        )
    if experience.gate_chain.get("delivery") != "pass" and experience.gate_chain.get("artifact") == "pass":
        recommendations.append(
            {
                "from": "artifact_gate",
                "to": "delivery_gate",
                "reason": "artifact_passed_delivery_not_verified",
            }
        )
    return recommendations


def build_promoted_learning_policy(experiences: list[LearningExperience]) -> dict[str, Any]:
    promoted: list[str] = []
    penalized: list[str] = []
    escalation: list[dict[str, str]] = []
    source_experiences: list[str] = []
    for exp in experiences:
        if exp.outcome != "verified_success":
            continue
        projection = project_nexus_policy(exp)
        source_experiences.append(exp.experience_id)
        promoted.extend(str(item) for item in projection["route_weight_updates"])
        penalized.extend(str(item) for item in projection["capability_penalties"])
        escalation.extend(projection["escalation_recommendations"])
    return {
        "schema_version": "nexus_promoted_learning_policy.v1",
        "source_experiences": source_experiences,
        "promoted_capabilities": sorted(set(promoted)),
        "penalized_capabilities": sorted(set(penalized)),
        "escalation_recommendations": escalation,
        "capability_roi": _aggregate_capability_roi(experiences),
        "penalty_candidates": _derive_penalty_candidates(_aggregate_capability_roi(experiences)),
        "enforce_penalties": False,
    }


def save_promoted_learning_policy(path: Path, experiences: list[LearningExperience]) -> dict[str, Any]:
    current = build_promoted_learning_policy(experiences)
    prior = load_promoted_learning_policy(path)
    merged_roi = _merge_capability_roi(prior.get("capability_roi", {}) if isinstance(prior, dict) else {}, current.get("capability_roi", {}))
    penalty_candidates = _derive_penalty_candidates(merged_roi)
    policy = {
        "schema_version": "nexus_promoted_learning_policy.v1",
        "source_experiences": sorted(
            set(str(item) for item in (prior.get("source_experiences", []) if isinstance(prior, dict) else []) or [])
            | set(current.get("source_experiences", []) or [])
        ),
        "promoted_capabilities": sorted(
            set(str(item) for item in (prior.get("promoted_capabilities", []) if isinstance(prior, dict) else []) or [])
            | set(current.get("promoted_capabilities", []) or [])
        ),
        "penalized_capabilities": sorted(
            set(str(item) for item in (prior.get("penalized_capabilities", []) if isinstance(prior, dict) else []) or [])
            | set(current.get("penalized_capabilities", []) or [])
            | set(penalty_candidates)
        ),
        "escalation_recommendations": list((prior.get("escalation_recommendations", []) if isinstance(prior, dict) else []) or [])
        + list(current.get("escalation_recommendations", []) or []),
        "capability_roi": merged_roi,
        "penalty_candidates": penalty_candidates,
        "enforce_penalties": bool(penalty_candidates),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return policy


def load_promoted_learning_policy(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "nexus_promoted_learning_policy.v1",
            "source_experiences": [],
            "promoted_capabilities": [],
            "penalized_capabilities": [],
            "escalation_recommendations": [],
            "capability_roi": {},
            "penalty_candidates": [],
            "enforce_penalties": False,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _lifecycle_from_receipt(receipt: dict[str, Any]) -> CapabilityLifecycle:
    name = str(receipt.get("name") or receipt.get("capability") or "unknown")
    meta = CAPABILITY_TAXONOMY.get(name, {"category": "unknown", "phases": ("C",)})
    refs = tuple(str(ref) for ref in receipt.get("evidence_refs", []) or [] if str(ref).strip())
    return CapabilityLifecycle(
        capability=name,
        category=str(meta["category"]),
        phase=str(tuple(meta["phases"])[0]),
        selected=bool(receipt.get("selected", False)),
        invoked=bool(receipt.get("invoked", False)),
        evidence=bool(receipt.get("evidence_present", False) or refs),
        outcome=bool(receipt.get("outcome_contributed", False)),
        gate_passed=bool(receipt.get("gate_passed", False)),
        evidence_refs=refs,
        failure_reason=str(receipt.get("failure_reason") or ""),
    )


def _gate_chain(usage: dict[str, Any]) -> dict[str, str]:
    caps = usage.get("capabilities", {}) if isinstance(usage.get("capabilities"), dict) else {}

    def status(key: str) -> str:
        value = caps.get(f"{key}_gate_passed")
        if value is True:
            return "pass"
        if value is False and (caps.get(f"{key}_refs") or caps.get(f"{key}_invoked")):
            return "fail"
        return "not_run"

    return {
        "mempalace": status("mempalace"),
        "belief": status("belief"),
        "artifact": status("artifact"),
        "claim": "pass" if caps.get("claim_verified") or caps.get("claim_gate_passed") else "not_run",
        "delivery": status("delivery"),
    }


def _first_missing_phase(observed: list[str]) -> str:
    for phase in PHASE_CHAIN:
        if phase not in observed:
            return phase
    return ""


def _aggregate_capability_roi(experiences: list[LearningExperience]) -> dict[str, dict[str, int]]:
    roi: dict[str, dict[str, int]] = {}
    for exp in experiences:
        for item in exp.capability_lifecycle:
            entry = roi.setdefault(
                item.capability,
                {
                    "selected": 0,
                    "invoked": 0,
                    "evidence": 0,
                    "outcome": 0,
                    "gate_passed": 0,
                },
            )
            entry["selected"] += int(bool(item.selected))
            entry["invoked"] += int(bool(item.invoked))
            entry["evidence"] += int(bool(item.evidence))
            entry["outcome"] += int(bool(item.outcome))
            entry["gate_passed"] += int(bool(item.gate_passed))
    return roi


def _merge_capability_roi(
    prior: dict[str, Any],
    current: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    merged: dict[str, dict[str, int]] = {}
    names = set(prior) | set(current)
    for name in names:
        base = prior.get(name, {}) if isinstance(prior.get(name, {}), dict) else {}
        now = current.get(name, {})
        merged[name] = {
            "selected": int(base.get("selected", 0) or 0) + int(now.get("selected", 0) or 0),
            "invoked": int(base.get("invoked", 0) or 0) + int(now.get("invoked", 0) or 0),
            "evidence": int(base.get("evidence", 0) or 0) + int(now.get("evidence", 0) or 0),
            "outcome": int(base.get("outcome", 0) or 0) + int(now.get("outcome", 0) or 0),
            "gate_passed": int(base.get("gate_passed", 0) or 0) + int(now.get("gate_passed", 0) or 0),
        }
    return merged


def _derive_penalty_candidates(roi: dict[str, dict[str, int]]) -> list[str]:
    penalty: list[str] = []
    for name, counts in roi.items():
        selected = int(counts.get("selected", 0) or 0)
        invoked = int(counts.get("invoked", 0) or 0)
        outcome = int(counts.get("outcome", 0) or 0)
        if name not in HIGH_COST_CAPABILITIES or selected < 2:
            continue
        if invoked * 2 < selected or outcome * 2 < selected:
            penalty.append(name)
    return sorted(set(penalty))
