from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple, Union


class Phase1AArm(str, Enum):
    A = "PHASE1A_ARM_A"
    B = "PHASE1A_ARM_B"
    C = "PHASE1A_ARM_C"


class ComparabilityStatus(str, Enum):
    COMPARABLE = "COMPARABLE"
    NON_COMPARABLE = "NON_COMPARABLE"
    INVALID = "INVALID"


class ComparabilityReason(str, Enum):
    MATCH = "MATCH"
    ARM_MISMATCH = "ARM_MISMATCH"
    TASK_IDENTITY_DRIFT = "TASK_IDENTITY_DRIFT"
    TASK_CONTRACT_DRIFT = "TASK_CONTRACT_DRIFT"
    SOURCE_CORPUS_DRIFT = "SOURCE_CORPUS_DRIFT"
    ONLINE_PROVIDER_DRIFT = "ONLINE_PROVIDER_DRIFT"
    ONLINE_MODEL_DRIFT = "ONLINE_MODEL_DRIFT"
    ONLINE_PROMPT_POLICY_DRIFT = "ONLINE_PROMPT_POLICY_DRIFT"
    TOOL_SURFACE_DRIFT = "TOOL_SURFACE_DRIFT"
    BUDGET_TIMEOUT_DRIFT = "BUDGET_TIMEOUT_DRIFT"
    FINAL_VERIFIER_CONTRACT_DRIFT = "FINAL_VERIFIER_CONTRACT_DRIFT"
    QUALITY_GATE_CONTRACT_DRIFT = "QUALITY_GATE_CONTRACT_DRIFT"
    PLANNER_DECISION_DRIFT = "PLANNER_DECISION_DRIFT"
    INVALID_SPEC = "INVALID_SPEC"


@dataclass(frozen=True)
class Phase1AArmSemantics:
    nexus_baseline: bool
    deterministic_evidence_mediation: bool
    bounded_local_semantic_exploration: bool
    online_required: bool = True
    independent_final_verifier_required: bool = True


_ARM_SEMANTICS = {
    Phase1AArm.A: Phase1AArmSemantics(
        nexus_baseline=True,
        deterministic_evidence_mediation=False,
        bounded_local_semantic_exploration=False,
    ),
    Phase1AArm.B: Phase1AArmSemantics(
        nexus_baseline=False,
        deterministic_evidence_mediation=True,
        bounded_local_semantic_exploration=False,
    ),
    Phase1AArm.C: Phase1AArmSemantics(
        nexus_baseline=False,
        deterministic_evidence_mediation=True,
        bounded_local_semantic_exploration=True,
    ),
}


def _canonical_normalize(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _canonical_normalize(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (set, frozenset)):
        raise TypeError("unordered set/frozenset is not permitted in Phase 1A fingerprint input")
    if isinstance(obj, (list, tuple)):
        return [_canonical_normalize(x) for x in obj]
    return obj


def _canonical_json(obj: Any) -> str:
    normalized = _canonical_normalize(obj)
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(_canonical_json(obj).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Phase1AArmIdentity:
    arm: Union[Phase1AArm, str]
    task_id: str
    task_contract_hash: str
    source_corpus_id: str
    online_provider: str
    online_model: str
    online_prompt_policy_hash: str
    tool_surface: Union[Dict[str, Any], List[Any], Tuple[Any, ...]]
    budgets_timeouts: Dict[str, Any]
    final_verifier_contract_hash: str
    quality_gate_contract_hash: str
    planner_decision_id: str
    has_online_stage: bool = True
    local_provider_called: bool = False
    local_is_routing_authority: bool = False
    local_is_final_verifier: bool = False
    local_is_approval_authority: bool = False
    local_is_authoritative_patch_producer: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "arm", self._validate_arm(self.arm))

        self._validate_str_field("task_id", self.task_id)
        self._validate_str_field("task_contract_hash", self.task_contract_hash)
        self._validate_str_field("source_corpus_id", self.source_corpus_id)
        self._validate_str_field("online_provider", self.online_provider)
        self._validate_str_field("online_model", self.online_model)
        self._validate_str_field("online_prompt_policy_hash", self.online_prompt_policy_hash)
        self._validate_str_field("final_verifier_contract_hash", self.final_verifier_contract_hash)
        self._validate_str_field("quality_gate_contract_hash", self.quality_gate_contract_hash)
        self._validate_str_field("planner_decision_id", self.planner_decision_id)

        self._validate_container_field("tool_surface", self.tool_surface)
        self._validate_container_field("budgets_timeouts", self.budgets_timeouts)

        if not self.has_online_stage:
            raise ValueError("Phase 1A arms require an Online stage")

        if self.arm == Phase1AArm.A and self.local_provider_called:
            raise ValueError("Arm A Nexus baseline rejects any Phase 1A Local provider call")
        if self.arm == Phase1AArm.B and self.local_provider_called:
            raise ValueError("Arm B rejects any Phase 1A Local provider call")

        if self.local_is_routing_authority:
            raise ValueError("Local can never be routing authority")
        if self.local_is_final_verifier:
            raise ValueError("Local can never be final semantic verifier")
        if self.local_is_approval_authority:
            raise ValueError("Local can never be approval authority")
        if self.local_is_authoritative_patch_producer:
            raise ValueError("Local can never be automatically authoritative patch/result producer")

    @staticmethod
    def _validate_arm(arm_val: Any) -> Phase1AArm:
        if isinstance(arm_val, Phase1AArm):
            return arm_val

        raw_str = str(arm_val.value if hasattr(arm_val, "value") else arm_val)
        normalized = raw_str.strip().upper()

        if normalized in ("STANDARD_REVIEW", "STRONG_PROTOCOL", "EPISTEMIC_WORKFLOW"):
            raise ValueError(f"Legacy BenchmarkArm '{raw_str}' is rejected for Phase 1A arms")

        if normalized in (
            "A",
            "B",
            "C",
            "D",
            "B_LEGACY",
            "D_LEGACY",
            "TREATMENT_B",
            "TREATMENT_D",
            "VAP_B",
            "VAP_D",
        ):
            raise ValueError(
                f"Legacy VAP B/D semantics/label '{raw_str}' rejected for Phase 1A arms"
            )

        try:
            return Phase1AArm(normalized)
        except ValueError:
            raise ValueError(f"Invalid Phase 1A arm: '{raw_str}'")

    @staticmethod
    def _validate_str_field(name: str, value: Any) -> None:
        if value is None:
            raise ValueError(f"Required field '{name}' cannot be None")
        if not isinstance(value, str):
            raise ValueError(
                f"Required field '{name}' must be a string, got {type(value).__name__}"
            )
        if not value.strip():
            raise ValueError(f"Required field '{name}' cannot be empty or whitespace")

    @staticmethod
    def _reject_unordered_containers(name: str, value: Any, path: str = "") -> None:
        if isinstance(value, (set, frozenset)):
            raise ValueError(
                f"Required container field '{name}{path}' cannot contain unordered set/frozenset"
            )
        if isinstance(value, dict):
            for key, nested in value.items():
                Phase1AArmIdentity._reject_unordered_containers(name, nested, f"{path}[{key!r}]")
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                Phase1AArmIdentity._reject_unordered_containers(name, nested, f"{path}[{index}]")

    @staticmethod
    def _validate_container_field(name: str, value: Any) -> None:
        if value is None:
            raise ValueError(f"Required container field '{name}' cannot be None")
        allowed_types = (dict, list, tuple) if name == "tool_surface" else (dict,)
        if not isinstance(value, allowed_types):
            allowed_names = ", ".join(t.__name__ for t in allowed_types)
            raise ValueError(
                f"Required container field '{name}' must be {allowed_names}, got {type(value).__name__}"
            )
        Phase1AArmIdentity._reject_unordered_containers(name, value)
        if len(value) == 0:
            raise ValueError(f"Required container field '{name}' cannot be empty")

    def treatment_semantics(self) -> Phase1AArmSemantics:
        return _ARM_SEMANTICS[self.arm]

    def shared_treatment_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_contract_hash": self.task_contract_hash,
            "source_corpus_id": self.source_corpus_id,
            "online_provider": self.online_provider,
            "online_model": self.online_model,
            "online_prompt_policy_hash": self.online_prompt_policy_hash,
            "tool_surface": self.tool_surface,
            "budgets_timeouts": self.budgets_timeouts,
            "final_verifier_contract_hash": self.final_verifier_contract_hash,
            "quality_gate_contract_hash": self.quality_gate_contract_hash,
            "planner_decision_id": self.planner_decision_id,
        }

    def shared_treatment_hash(self) -> str:
        return compute_canonical_sha256(self.shared_treatment_dict())

    def triplet_fingerprint(self) -> str:
        return self.shared_treatment_hash()

    def full_identity_dict(self) -> Dict[str, Any]:
        d = self.shared_treatment_dict()
        d["arm"] = self.arm.value
        d["has_online_stage"] = self.has_online_stage
        d["local_provider_called"] = self.local_provider_called
        d["local_is_routing_authority"] = self.local_is_routing_authority
        d["local_is_final_verifier"] = self.local_is_final_verifier
        d["local_is_approval_authority"] = self.local_is_approval_authority
        d["local_is_authoritative_patch_producer"] = self.local_is_authoritative_patch_producer
        return d

    def full_identity_hash(self) -> str:
        return compute_canonical_sha256(self.full_identity_dict())


@dataclass(frozen=True)
class ComparabilityResult:
    is_comparable: bool
    status: ComparabilityStatus
    reasons: Tuple[ComparabilityReason, ...]
    details: Dict[str, Any] = field(default_factory=dict)


def compare_arm_identities(
    left: Phase1AArmIdentity,
    right: Phase1AArmIdentity,
    require_same_arm: bool = False,
) -> ComparabilityResult:
    reasons: List[ComparabilityReason] = []
    details: Dict[str, Any] = {}

    if require_same_arm and left.arm != right.arm:
        reasons.append(ComparabilityReason.ARM_MISMATCH)
        details["arm_mismatch"] = {"left": left.arm.value, "right": right.arm.value}

    if left.task_id != right.task_id:
        reasons.append(ComparabilityReason.TASK_IDENTITY_DRIFT)
        details["task_id"] = {"left": left.task_id, "right": right.task_id}

    if left.task_contract_hash != right.task_contract_hash:
        reasons.append(ComparabilityReason.TASK_CONTRACT_DRIFT)
        details["task_contract_hash"] = {
            "left": left.task_contract_hash,
            "right": right.task_contract_hash,
        }

    if left.source_corpus_id != right.source_corpus_id:
        reasons.append(ComparabilityReason.SOURCE_CORPUS_DRIFT)
        details["source_corpus_id"] = {
            "left": left.source_corpus_id,
            "right": right.source_corpus_id,
        }

    if left.online_provider != right.online_provider:
        reasons.append(ComparabilityReason.ONLINE_PROVIDER_DRIFT)
        details["online_provider"] = {"left": left.online_provider, "right": right.online_provider}

    if left.online_model != right.online_model:
        reasons.append(ComparabilityReason.ONLINE_MODEL_DRIFT)
        details["online_model"] = {"left": left.online_model, "right": right.online_model}

    if left.online_prompt_policy_hash != right.online_prompt_policy_hash:
        reasons.append(ComparabilityReason.ONLINE_PROMPT_POLICY_DRIFT)
        details["online_prompt_policy_hash"] = {
            "left": left.online_prompt_policy_hash,
            "right": right.online_prompt_policy_hash,
        }

    if _canonical_json(left.tool_surface) != _canonical_json(right.tool_surface):
        reasons.append(ComparabilityReason.TOOL_SURFACE_DRIFT)
        details["tool_surface"] = {"left": left.tool_surface, "right": right.tool_surface}

    if _canonical_json(left.budgets_timeouts) != _canonical_json(right.budgets_timeouts):
        reasons.append(ComparabilityReason.BUDGET_TIMEOUT_DRIFT)
        details["budgets_timeouts"] = {
            "left": left.budgets_timeouts,
            "right": right.budgets_timeouts,
        }

    if left.final_verifier_contract_hash != right.final_verifier_contract_hash:
        reasons.append(ComparabilityReason.FINAL_VERIFIER_CONTRACT_DRIFT)
        details["final_verifier_contract_hash"] = {
            "left": left.final_verifier_contract_hash,
            "right": right.final_verifier_contract_hash,
        }

    if left.quality_gate_contract_hash != right.quality_gate_contract_hash:
        reasons.append(ComparabilityReason.QUALITY_GATE_CONTRACT_DRIFT)
        details["quality_gate_contract_hash"] = {
            "left": left.quality_gate_contract_hash,
            "right": right.quality_gate_contract_hash,
        }

    if left.planner_decision_id != right.planner_decision_id:
        reasons.append(ComparabilityReason.PLANNER_DECISION_DRIFT)
        details["planner_decision_id"] = {
            "left": left.planner_decision_id,
            "right": right.planner_decision_id,
        }

    if not reasons:
        return ComparabilityResult(
            is_comparable=True,
            status=ComparabilityStatus.COMPARABLE,
            reasons=(ComparabilityReason.MATCH,),
            details={},
        )
    return ComparabilityResult(
        is_comparable=False,
        status=ComparabilityStatus.NON_COMPARABLE,
        reasons=tuple(reasons),
        details=details,
    )


def validate_triplet_comparability(
    arm_a: Phase1AArmIdentity,
    arm_b: Phase1AArmIdentity,
    arm_c: Phase1AArmIdentity,
) -> ComparabilityResult:
    reasons: List[ComparabilityReason] = []
    details: Dict[str, Any] = {}

    if arm_a.arm != Phase1AArm.A:
        reasons.append(ComparabilityReason.ARM_MISMATCH)
        details["arm_a_mismatch"] = f"Expected Arm A, got {arm_a.arm.value}"

    if arm_b.arm != Phase1AArm.B:
        reasons.append(ComparabilityReason.ARM_MISMATCH)
        details["arm_b_mismatch"] = f"Expected Arm B, got {arm_b.arm.value}"

    if arm_c.arm != Phase1AArm.C:
        reasons.append(ComparabilityReason.ARM_MISMATCH)
        details["arm_c_mismatch"] = f"Expected Arm C, got {arm_c.arm.value}"

    res_ab = compare_arm_identities(arm_a, arm_b, require_same_arm=False)
    res_ac = compare_arm_identities(arm_a, arm_c, require_same_arm=False)

    for res in (res_ab, res_ac):
        if not res.is_comparable:
            for r in res.reasons:
                if r not in reasons and r != ComparabilityReason.MATCH:
                    reasons.append(r)
            details.update(res.details)

    if not reasons:
        return ComparabilityResult(
            is_comparable=True,
            status=ComparabilityStatus.COMPARABLE,
            reasons=(ComparabilityReason.MATCH,),
            details={"triplet_fingerprint": arm_a.triplet_fingerprint()},
        )
    return ComparabilityResult(
        is_comparable=False,
        status=ComparabilityStatus.NON_COMPARABLE,
        reasons=tuple(reasons),
        details=details,
    )


def compute_triplet_comparability_fingerprint(
    arm_a: Phase1AArmIdentity,
    arm_b: Phase1AArmIdentity,
    arm_c: Phase1AArmIdentity,
) -> str:
    res = validate_triplet_comparability(arm_a, arm_b, arm_c)
    if not res.is_comparable:
        reasons_str = ", ".join(r.value for r in res.reasons)
        raise ValueError(
            f"Cannot compute triplet fingerprint for non-comparable triplet: {reasons_str}"
        )
    return arm_a.triplet_fingerprint()
