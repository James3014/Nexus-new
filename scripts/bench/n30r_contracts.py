"""N30R canonical evaluation contracts.

Immutable dataclass structures for task, arm, attempt, terminal-status,
hash, and leakage-validation contracts.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Terminal status
# ---------------------------------------------------------------------------

class N30RTerminalStatus(str, Enum):
    VERIFIED_SOLVE = "VERIFIED_SOLVE"
    VERIFIED_FAIL = "VERIFIED_FAIL"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    INFRA_INVALID = "INFRA_INVALID"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    LEAKAGE_INVALID = "LEAKAGE_INVALID"


# ---------------------------------------------------------------------------
# Task spec (public — no golden patch body)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class N30RTaskSpec:
    task_id: str
    split: str  # "smoke" | "heldout"
    source_relpath: str
    source_sha256: str
    task_statement: str
    expected_failure_signature: str
    verifier_command: tuple[str, ...]
    verifier_contract_sha256: str
    environment_sha256: str
    task_bundle_sha256: str
    golden_patch_sha256: str
    golden_patch_private_ref: str
    original_verifier_expected: str  # "FAIL"
    golden_verifier_expected: str  # "PASS"

    def __post_init__(self) -> None:
        if self.split not in ("smoke", "heldout"):
            raise ValueError(f"Invalid split: {self.split}")
        if self.original_verifier_expected != "FAIL":
            raise ValueError("original_verifier_expected must be FAIL")
        if self.golden_verifier_expected != "PASS":
            raise ValueError("golden_verifier_expected must be PASS")


# ---------------------------------------------------------------------------
# Arm spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class N30RArmSpec:
    arm_id: str
    model_provider: str
    model_name: str
    model_parameters: Dict[str, Any]
    nexus_enabled: bool
    core_armor_enabled: bool
    additional_capability: str  # empty for initial arms
    arm_config_sha256: str

    VALID_ARM_IDS = frozenset({
        "N30R_A_7B_BARE",
        "N30R_B_7B_REAL_CORE",
    })


# ---------------------------------------------------------------------------
# Attempt receipt
# ---------------------------------------------------------------------------

@dataclass
class N30RAttemptReceipt:
    run_id: str
    task_id: str
    trial_index: int
    seed: int
    arm_id: str
    provider_requested: str
    provider_actual: str
    model_requested: str
    model_actual: str
    model_parameters_sha256: str
    task_bundle_sha256: str
    source_sha256: str
    verifier_contract_sha256: str
    environment_sha256: str
    arm_config_sha256: str
    rendered_prompt_sha256: str
    model_call_started: bool
    model_response_received: bool
    raw_output_sha256: str
    raw_output_length: int
    patch_sha256: str
    patch_length: int
    apply_status: str
    verifier_status: str
    terminal_status: str
    timeout_limit_sec: float
    wall_time_sec: float
    timed_out: bool
    timeout_stage: str
    candidate_isolated: bool
    trust_mismatch: bool
    receipt_complete: bool
    # N30R-R1: production path evidence fields
    execution_path_kind: str = ""  # "bare_direct_provider" | "nexus_production_localheal_pipeline"
    planner_called: bool = False
    planner_version: str = ""
    route_truth_source: str = ""
    signal_snapshot_sha256: str = ""
    selected_executor: str = ""
    execution_topology: str = ""
    local_model_executor_called: bool = False
    production_local_path_used: bool = False
    legacy_adapter_called: bool = False
    model_call_count: int = 0
    semantic_retry_count: int = 0
    candidate_id: str = ""
    candidate_workspace_id: str = ""
    production_receipt_sha256: str = ""

    def validate_terminal_invariants(self) -> list[str]:
        """Return list of invariant violations (empty = valid)."""
        errors: list[str] = []
        ts = self.terminal_status

        if ts not in {s.value for s in N30RTerminalStatus}:
            errors.append(f"unknown terminal_status: {ts}")

        if ts == "VERIFIED_SOLVE":
            if not self.model_call_started:
                errors.append("VERIFIED_SOLVE requires model_call_started")
            if not self.model_response_received:
                errors.append("VERIFIED_SOLVE requires model_response_received")
            if not self.raw_output_sha256:
                errors.append("VERIFIED_SOLVE requires non-empty raw_output_sha256")
            if not self.patch_sha256:
                errors.append("VERIFIED_SOLVE requires non-empty patch_sha256")
            if self.apply_status != "success":
                errors.append("VERIFIED_SOLVE requires apply_status=success")
            if self.verifier_status != "pass":
                errors.append("VERIFIED_SOLVE requires verifier_status=pass")
            if not self.candidate_isolated:
                errors.append("VERIFIED_SOLVE requires candidate_isolated=true")
            if self.trust_mismatch:
                errors.append("VERIFIED_SOLVE requires trust_mismatch=false")
            if not self.receipt_complete:
                errors.append("VERIFIED_SOLVE requires receipt_complete=true")

        if not self.raw_output_sha256 and ts == "VERIFIED_FAIL":
            errors.append("empty output cannot be VERIFIED_FAIL")

        if self.timed_out and ts != "MODEL_TIMEOUT":
            errors.append("timed_out=true but terminal_status is not MODEL_TIMEOUT")

        if self.provider_actual != self.provider_requested and not self.trust_mismatch:
            errors.append("provider mismatch requires trust_mismatch=true")
        if self.model_actual != self.model_requested and not self.trust_mismatch:
            errors.append("model mismatch requires trust_mismatch=true")

        if not self.receipt_complete:
            for f in ("raw_output_sha256", "task_bundle_sha256", "source_sha256",
                       "verifier_contract_sha256", "environment_sha256", "arm_config_sha256"):
                if not getattr(self, f, ""):
                    errors.append(f"receipt_complete=true requires {f}")

        return errors


# ---------------------------------------------------------------------------
# Task gate receipt (private — never exposed to model)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class N30RTaskGateReceipt:
    task_id: str
    original_exit_codes: list[int]
    original_failure_signatures: list[str]
    golden_exit_codes: list[int]
    source_sha256: str
    golden_patch_sha256: str
    verifier_contract_sha256: str
    environment_sha256: str
    task_bundle_sha256: str
    eligible: bool
    ineligibility_reasons: list[str]


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_str(text: str) -> str:
    return sha256_hex(text.encode("utf-8"))
