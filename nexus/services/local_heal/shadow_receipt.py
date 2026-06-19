"""Trace-only shadow receipt implementation v0."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class GateDecision(Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    PASS = "PASS"
    BLOCK_ADOPTION = "BLOCK_ADOPTION"
    TRUST_MISMATCH_BLOCK = "TRUST_MISMATCH_BLOCK"
    FORBIDDEN_OUTPUT_BLOCK = "FORBIDDEN_OUTPUT_BLOCK"


FORBIDDEN_OUTPUT_PATTERNS = {
    "patch_generation": ["generate_patch", "apply_patch", "write_patch"],
    "routing_decision": ["route_to_model", "select_model", "change_routing"],
    "verifier_override": ["bypass_verifier", "skip_verifier", "override_verifier"],
    "solve_claim": ["solved", "bug_fixed", "repair_complete"],
    "training_export_decision": ["export_training", "export_dpo", "export_ppo"],
    "public_claim": ["public_benchmark", "solve_rate_claim", "parity_claim"],
    "diff_like_patch": ["diff --git", "@@ -", "apply this patch"],
    "search_replace_block": ["<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE", "SEARCH/REPLACE"],
    "patch_instruction": ["replace this code", "modify the file", "write this patch", "change the implementation"],
    "routing_recommendation": ["route to 14b", "send this to production", "use this model", "switch router"],
    "verifier_override_extended": ["ignore verifier", "verifier is wrong", "treat as solved", "skip verifier"],
    "solve_claim_extended": ["verified solve", "verified repair", "repair complete", "bug fixed", "this is solved"],
    "training_export_suggestion": ["export for training", "use as dpo", "training data", "fine-tune on"],
    "public_benchmark_extended": ["swe-bench", "solve rate", "public benchmark", "benchmark score"],
    "model_parity_claim": ["matches gpt", "接近 gemini", "equivalent to claude", "parity with"],
    "source_mutation": ["overwrite file", "modify source", "change the file"],
    "ambiguous_claim": ["capability claim", "performance improvement"],
    "safe_mention": ["discussed in", "mentioned in", "reference to"],
}


@dataclass
class ShadowReceipt:
    receipt_id: str
    task_id: str
    dry_row_id: str
    model: str
    task_type: str
    source_stage: str
    input_ref: str
    output_ref: str
    redacted_input_only: bool
    model_call_executed: bool
    eval_executed: bool
    runtime_effect: bool
    routing_changed: bool
    patch_apply_allowed: bool
    verifier_override_allowed: bool
    source_mutation_allowed: bool
    training_export_allowed: bool
    output_schema_valid: bool
    forbidden_output_detected: bool
    authority_creep_detected: bool
    trust_mismatch_flags: list
    trust_mismatch_score: Optional[float]
    gate_decision: str
    adoption_allowed: bool
    owner_approval_ref: Optional[str]
    governance: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ValidationResult:
    ok: bool
    errors: list
    warnings: list


def detect_forbidden_output(output_text: str) -> list:
    detected = []
    text_lower = output_text.lower()
    for category, patterns in FORBIDDEN_OUTPUT_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in text_lower:
                detected.append(category)
                break
    return detected


def validate_receipt(receipt: ShadowReceipt) -> ValidationResult:
    errors = []
    warnings = []

    if receipt.runtime_effect:
        errors.append("runtime_effect must be false")
    if receipt.routing_changed:
        errors.append("routing_changed must be false")
    if receipt.patch_apply_allowed:
        errors.append("patch_apply_allowed must be false")
    if receipt.verifier_override_allowed:
        errors.append("verifier_override_allowed must be false")
    if receipt.source_mutation_allowed:
        errors.append("source_mutation_allowed must be false")
    if receipt.training_export_allowed:
        errors.append("training_export_allowed must be false")
    if receipt.adoption_allowed:
        errors.append("adoption_allowed must be false")

    if receipt.forbidden_output_detected:
        errors.append("forbidden_output_detected must be false for valid receipt")
    if receipt.authority_creep_detected:
        errors.append("authority_creep_detected must be false for valid receipt")

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def create_dry_run_receipt(
    task_id: str,
    dry_row_id: str,
    model: str,
    task_type: str,
    input_ref: str,
    output_ref: str = "none",
) -> ShadowReceipt:
    receipt_id = hashlib.sha256(f"dry_{task_id}_{dry_row_id}_{model}".encode()).hexdigest()[:16]

    governance = {
        "model_calls_executed": False,
        "eval_executed": False,
        "runtime_effect": False,
        "routing_changed": False,
        "patch_apply_allowed": False,
        "verifier_override_allowed": False,
        "source_mutation_allowed": False,
        "training_export": False,
        "public_claim_allowed": False,
    }

    return ShadowReceipt(
        receipt_id=receipt_id,
        task_id=task_id,
        dry_row_id=dry_row_id,
        model=model,
        task_type=task_type,
        source_stage="dry_run",
        input_ref=input_ref,
        output_ref=output_ref,
        redacted_input_only=True,
        model_call_executed=False,
        eval_executed=False,
        runtime_effect=False,
        routing_changed=False,
        patch_apply_allowed=False,
        verifier_override_allowed=False,
        source_mutation_allowed=False,
        training_export_allowed=False,
        output_schema_valid=True,
        forbidden_output_detected=False,
        authority_creep_detected=False,
        trust_mismatch_flags=[],
        trust_mismatch_score=None,
        gate_decision=GateDecision.NOT_EVALUATED.value,
        adoption_allowed=False,
        owner_approval_ref=None,
        governance=governance,
    )
