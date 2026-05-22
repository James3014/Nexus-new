from __future__ import annotations

from typing import Any

from scripts.bench.cost_evidence_classifier import annotate_cost_evidence


PILLAR_OBSERVATION_FIELDS = {
    "lancedb": "pillar_lancedb_active",
    "memory": "pillar_memory_active",
    "mempalace": "pillar_mempalace_active",
    "belief": "pillar_belief_active",
    "artifact": "pillar_artifact_active",
}
PHASE_OBSERVATION_FIELDS = {
    "P": "phase_p",
    "X": "phase_x",
    "D": "phase_d",
    "R": "phase_r",
    "A": "phase_a",
    "C": "phase_c",
}
LOCAL_INTERNAL_DELIVERY_SOURCES = {
    "local_hidden_contract_fast_path",
    "local_deterministic_pre_model_rescue",
    "local_preflight",
    "local",
}
MODEL_DELIVERY_SOURCES = {
    "llm",
    "model_patch",
    "nexus_llm_baseline",
    "llm_self_heal",
    "llm_candidate",
}


def observed_nexus_pillars(row: dict[str, Any]) -> list[str]:
    return [name for name, field in PILLAR_OBSERVATION_FIELDS.items() if bool(row.get(field, False))]


def observed_nexus_phases(row: dict[str, Any]) -> list[str]:
    return [name for name, field in PHASE_OBSERVATION_FIELDS.items() if bool(row.get(field))]


def model_uses_nexus(row: dict[str, Any]) -> bool:
    return bool(row.get("model_uses_nexus", row.get("gemini_uses_nexus", False)))


def hidden_verifier_infra_reason(row: dict[str, Any]) -> str | None:
    if row.get("hidden_verifier_passed") is not False:
        return None
    combined = "\n".join(
        [
            str(row.get("hidden_verifier_stdout_tail") or ""),
            str(row.get("hidden_verifier_stderr_tail") or ""),
        ]
    ).lower()
    if "operation not permitted" in combined or ".cache/uv" in combined:
        return "hidden_verifier_infra_error"
    if "no such file or directory" in combined and ("uv" in combined or "pytest" in combined):
        return "hidden_verifier_infra_error"
    if "permission denied" in combined:
        return "hidden_verifier_infra_error"
    return None


def classify_infra_invalid_reason(
    row: dict[str, Any],
    *,
    model_required: bool,
    nexus_required: bool,
) -> str | None:
    explicit_model_required_contract = str(row.get("eligibility_class") or "").strip() == "model_required"
    hidden_reason = str(row.get("hidden_verifier_infra_invalid_reason") or "").strip()
    if hidden_reason:
        return hidden_reason
    hidden_reason = hidden_verifier_infra_reason(row)
    if hidden_reason:
        return hidden_reason

    gateway_error = str(row.get("baseline_gateway_error_category") or "").strip()
    if not gateway_error and bool(row.get("baseline_llm_required", False)):
        gateway_error = str(row.get("gateway_error_category") or "").strip()
    raw_tail = str(row.get("baseline_raw_tail") or "")
    combined = f"{gateway_error}\n{raw_tail}".lower()
    model_calls = int(row.get("model_calls", 0) or 0)
    pillars = observed_nexus_pillars(row) if nexus_required else []
    phases = observed_nexus_phases(row) if nexus_required else []
    local_internal_delivery_source = str(row.get("nexus_winner_source") or "") in LOCAL_INTERNAL_DELIVERY_SOURCES
    local_preflight_verified = bool(
        nexus_required
        and local_internal_delivery_source
        and bool(row.get("semantic_completed", False))
        and bool(row.get("nexus_context_delivered", False))
        and len(pillars) >= len(PILLAR_OBSERVATION_FIELDS)
        and len(phases) >= len(PHASE_OBSERVATION_FIELDS)
    )

    if (
        "quota" in combined
        or "resource exhausted" in combined
        or "rate limit" in combined
        or "usage limit" in combined
        or "429" in combined
    ):
        return "quota_exhausted"
    if (
        "oauth" in combined
        or "login required" in combined
        or "permission denied" in combined
        or "authentication page" in combined
        or "auth_confirmation_required" in combined
    ):
        return "auth_failed"
    if gateway_error == "binary_missing":
        return "cli_missing"
    if gateway_error == "parse_failure":
        total_tokens = int(row.get("total_tokens", 0) or 0)
        token_status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "").strip().lower()
        if model_required and not nexus_required and model_calls > 0 and (
            total_tokens > 0 or token_status in {"measured", "ok"}
        ):
            return None
        if (
            model_required
            and nexus_required
            and model_calls > 0
            and total_tokens > 0
            and token_status in {"measured", "ok"}
            and bool(row.get("semantic_completed", False))
            and bool(row.get("hidden_verifier_passed", False))
            and bool(row.get("nexus_context_delivered", False))
            and bool(model_uses_nexus(row))
            and not bool(row.get("report_trust_mismatch", False))
        ):
            return None
        return "parse_error"
    if bool(row.get("baseline_llm_required", False)) and gateway_error in {"gateway_error", "binary_missing"}:
        return "cli_missing" if gateway_error == "binary_missing" else "model_gateway_error"
    if str(row.get("timeout_scope") or "") == "with_nexus_subprocess":
        return str(row.get("timeout_stage") or "timeout_before_receipt")
    if model_required and gateway_error == "timeout" and model_calls == 0:
        return "timeout_before_model_call"
    if model_required and model_calls > 0:
        total_tokens = int(row.get("total_tokens", 0) or 0)
        token_status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "").strip().lower()
        if total_tokens <= 0 and token_status not in {"measured", "ok"}:
            return "model_call_without_tokens"
    winner_source = str(row.get("nexus_winner_source") or row.get("source") or "").strip()
    model_delivery_source = bool(
        winner_source in MODEL_DELIVERY_SOURCES
        or winner_source.startswith("llm_")
        or winner_source.startswith("model_")
        or winner_source.startswith("nexus_llm")
    )
    nexus_failure_reason = str(row.get("nexus_failure_reason") or row.get("reason") or "").strip()
    nexus_error_codes = {str(item).strip() for item in (row.get("nexus_error_codes") or row.get("error_codes") or []) if str(item).strip()}
    if (
        explicit_model_required_contract
        and model_required
        and nexus_required
        and winner_source.startswith("local")
        and not model_delivery_source
        and (
            nexus_failure_reason == "model_required_local_delivery_blocked"
            or "model_required_local_delivery_blocked" in nexus_error_codes
        )
    ):
        return "model_required_local_delivery_blocked"
    if (
        explicit_model_required_contract
        and model_required
        and nexus_required
        and model_calls > 0
        and bool(row.get("semantic_completed", False))
        and winner_source.startswith("local")
        and not model_delivery_source
    ):
        return "model_required_local_delivery_blocked"

    if (
        nexus_required
        and str(row.get("capability_activation_contract") or "") == "required"
        and str(row.get("receipt_data_contract_status") or "") == "DATA_CONTRACT_VIOLATION"
    ):
        return "receipt_data_contract_violation"

    if nexus_required:
        if (
            not local_preflight_verified
            and (
                model_calls <= 0
                or not model_uses_nexus(row)
            )
            or not bool(row.get("nexus_context_delivered", False))
            or len(pillars) < len(PILLAR_OBSERVATION_FIELDS)
            or len(phases) < len(PHASE_OBSERVATION_FIELDS)
        ):
            return "nexus_delivery_invalid"

    if model_required and model_calls <= 0 and not local_preflight_verified:
        return "timeout_before_model_call"
    return None


def annotate_benchmark_eligibility(
    row: dict[str, Any],
    *,
    provider: str,
    model_required: bool,
    nexus_required: bool,
) -> dict[str, Any]:
    row["provider"] = provider
    row["model_uses_nexus"] = model_uses_nexus(row)
    row["nexus_pillars_observed"] = observed_nexus_pillars(row)
    row["nexus_phases_observed"] = observed_nexus_phases(row)
    row["nexus_internal_delivery_valid"] = bool(
        str(row.get("nexus_winner_source") or "") in LOCAL_INTERNAL_DELIVERY_SOURCES
        and bool(row.get("semantic_completed", False))
        and bool(row.get("nexus_context_delivered", False))
        and len(row["nexus_pillars_observed"]) >= len(PILLAR_OBSERVATION_FIELDS)
        and len(row["nexus_phases_observed"]) >= len(PHASE_OBSERVATION_FIELDS)
    )
    winner_source = str(row.get("nexus_winner_source") or row.get("source") or "").strip()
    model_calls = int(row.get("model_calls", 0) or 0)
    model_delivery_source = bool(
        winner_source in MODEL_DELIVERY_SOURCES
        or winner_source.startswith("llm_")
        or winner_source.startswith("model_")
        or winner_source.startswith("nexus_llm")
    )
    row["benchmark_contract_type"] = (
        str(row.get("benchmark_contract_type") or "").strip()
        or ("model_required" if model_required else "deterministic_or_local")
    )
    row["model_required"] = bool(model_required)
    row["nexus_required"] = bool(nexus_required)
    row["model_uplift_model_call_present"] = bool(model_calls > 0)
    row["model_uplift_model_delivery_source"] = model_delivery_source
    model_token_status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "").strip().lower()
    row["model_uplift_response_observed"] = bool(
        row.get("model_patch_generated", False)
        or int(row.get("total_tokens", 0) or 0) > 0
        or model_token_status in {"ok", "measured"}
    )
    row["model_uplift_blocked_by_local_delivery"] = bool(
        model_required
        and nexus_required
        and row["nexus_internal_delivery_valid"]
        and not model_delivery_source
    )
    gateway_error = str(row.get("baseline_gateway_error_category") or "").strip()
    row["invocation_started"] = bool(model_calls > 0 or gateway_error in {"cli_error", "parse_failure", "timeout"})
    row["model_response_received"] = bool(
        row.get("model_patch_generated", False)
        or int(row.get("total_tokens", 0) or 0) > 0
        or str(row.get("token_capture_status", "")) in {"ok", "measured"}
    )
    row["nexus_bootstrap_completed"] = bool(row.get("nexus_context_delivered", False) or row["nexus_phases_observed"])
    annotate_cost_evidence(row)
    reason = classify_infra_invalid_reason(row, model_required=model_required, nexus_required=nexus_required)
    row["infra_invalid_reason"] = reason
    row["run_eligible"] = reason is None
    row_mode = str(row.get("mode") or "").strip().lower()
    row["nexus_wearing_valid"] = bool((nexus_required or row_mode == "with_nexus") and reason is None)
    row["model_uplift_eligible"] = bool(
        reason is None
        and model_required
        and model_calls > 0
        and bool(row["model_uplift_response_observed"])
        and (not nexus_required or model_uses_nexus(row))
        and (not nexus_required or model_delivery_source)
    )
    if not model_required:
        row["model_uplift_ineligible_reason"] = "model_not_required"
    elif reason is not None:
        row["model_uplift_ineligible_reason"] = f"infra_invalid:{reason}"
    elif model_calls <= 0:
        row["model_uplift_ineligible_reason"] = "no_model_call"
    elif not bool(row["model_uplift_response_observed"]):
        row["model_uplift_ineligible_reason"] = "model_call_without_tokens"
    elif nexus_required and not model_uses_nexus(row):
        row["model_uplift_ineligible_reason"] = "model_did_not_use_nexus"
    elif nexus_required and not model_delivery_source:
        row["model_uplift_ineligible_reason"] = "final_delivery_not_model_source"
    else:
        row["model_uplift_ineligible_reason"] = None
    return row
