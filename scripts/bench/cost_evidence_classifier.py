from __future__ import annotations

from typing import Any


PROVIDER_TOKEN_SOURCES = {"stats", "usage_metadata", "codex_stdout"}
LOCAL_SUCCESS_SOURCES = {
    "local",
    "local_only",
    "local_hidden_shadow",
    "local_hidden_contract_fast_path",
    "local_preflight",
    "local_deterministic_success",
    "nexus_tool_success",
}


def classify_token_unreliable_reason(
    row: dict[str, Any],
    *,
    token_status: str,
    total_tokens: int,
) -> str | None:
    model_calls = int(row.get("model_calls", 0) or 0)
    model_total_tokens = int(row.get("model_total_tokens", 0) or 0)
    model_token_status = str(row.get("model_token_capture_status") or "").strip().lower()
    token_source = str(row.get("gateway_token_source") or "").strip().lower()
    token_failure_class = str(row.get("token_accounting_failure_class") or "").strip().lower()
    token_outlier_reason = str(row.get("gateway_token_outlier_reason") or "").strip().lower()
    gateway_error = str(row.get("gateway_error_category") or row.get("baseline_gateway_error_category") or "").lower()
    winner_source = str(row.get("nexus_winner_source") or row.get("source") or "").lower()
    provider_model_tokens_measured = bool(
        model_calls > 0
        and model_total_tokens > 0
        and model_token_status == "measured"
        and token_source in PROVIDER_TOKEN_SOURCES
    )
    model_timeout_local_fallback = bool(
        model_calls > 0
        and row.get("fallback_used", False)
        and "timeout" in gateway_error
        and (winner_source.startswith("local") or token_status == "not_applicable_local_only")
    )
    if model_timeout_local_fallback:
        return "model_timeout_with_local_fallback"
    if model_calls > 0 and total_tokens <= 0:
        return "model_call_without_tokens"
    if (
        token_source == "estimated_from_stats_outlier"
        or token_failure_class == "provider_stats_outlier"
        or token_outlier_reason == "stats_outlier_possible_cumulative"
    ):
        return "stats_outlier_possible_cumulative"
    if token_status in {"estimated", "fallback_est", "unknown", ""}:
        return "estimated_tokens" if token_status == "estimated" else "unknown_token_capture"
    if token_status == "not_applicable_local_only" and model_calls > 0:
        if provider_model_tokens_measured:
            return None
        return "local_only_rescue_not_model_comparable"
    if (
        str(row.get("gateway_token_source") or "") == "stats"
        and total_tokens > max(200000, int(row.get("gateway_total_chars", 0) or 0) * 40)
    ):
        return "stats_outlier_possible_cumulative"
    return None


def row_has_measured_provider_tokens(row: dict[str, Any]) -> bool:
    """True only when token telemetry came from a provider-level source."""
    token_status = str(row.get("token_capture_status") or row.get("model_token_capture_status") or "").strip().lower()
    model_token_status = str(row.get("model_token_capture_status") or "").strip().lower()
    token_source = str(row.get("gateway_token_source") or "").strip().lower()
    model_total_tokens = int(row.get("model_total_tokens", 0) or 0)
    model_calls = int(row.get("model_calls", 0) or 0)
    if model_calls <= 0 and token_status in {"not_applicable_local_only", "not_applicable_no_model"}:
        return True
    direct_provider_tokens = bool(
        row.get("token_measured", False)
        and token_status == "measured"
        and token_source in PROVIDER_TOKEN_SOURCES
    )
    rescue_preserved_provider_tokens = bool(
        model_total_tokens > 0
        and model_token_status == "measured"
        and token_source in PROVIDER_TOKEN_SOURCES
    )
    return direct_provider_tokens or rescue_preserved_provider_tokens


def model_attempt_runner_overhead_polluted(row: dict[str, Any]) -> bool:
    if "model_attempt_runner_overhead_polluted" in row:
        return bool(row.get("model_attempt_runner_overhead_polluted", False))
    return bool(row.get("runner_overhead_polluted", False))


def annotate_cost_evidence(row: dict[str, Any]) -> dict[str, Any]:
    token_status = str(row.get("token_capture_status", "") or "").strip().lower()
    total_tokens = int(row.get("total_tokens", 0) or 0)
    model_calls = int(row.get("model_calls", 0) or 0)
    model_token_status = str(row.get("model_token_capture_status") or "").strip().lower()
    if not model_token_status:
        if model_calls <= 0:
            model_token_status = "not_applicable_no_model"
        elif token_status == "measured":
            model_token_status = "measured"
        elif total_tokens > 0:
            model_token_status = "estimated"
        else:
            model_token_status = "missing_gateway_stats"
    row["model_total_tokens"] = int(row.get("model_total_tokens", total_tokens if model_calls > 0 else 0) or 0)
    row["model_token_capture_status"] = model_token_status
    row["gateway_stats_present"] = bool(row.get("gateway_stats_present", False))
    row["gateway_usage_metadata_present"] = bool(row.get("gateway_usage_metadata_present", False))
    row["gateway_token_source"] = str(row.get("gateway_token_source") or "missing")
    row["gateway_token_outlier_reason"] = str(row.get("gateway_token_outlier_reason") or "")
    row["raw_provider_total_tokens"] = int(row.get("raw_provider_total_tokens", 0) or 0)
    row["raw_provider_token_source"] = str(row.get("raw_provider_token_source") or "")
    row["provider_stats_cumulative_suspected"] = bool(
        row.get("provider_stats_cumulative_suspected", False)
        or str(row.get("gateway_token_source") or "") == "estimated_from_stats_outlier"
    )
    row["token_accounting_failure_class"] = str(row.get("token_accounting_failure_class") or "")
    if row["provider_stats_cumulative_suspected"] and not row["token_accounting_failure_class"]:
        row["token_accounting_failure_class"] = "provider_stats_outlier"
    row["local_rescue_tokens"] = int(row.get("local_rescue_tokens", 0) or 0)
    default_rescue_cost_status = (
        "local_only" if bool(row.get("nexus_rescued", False)) or token_status == "not_applicable_local_only" else "not_rescue"
    )
    row["rescue_cost_status"] = str(row.get("rescue_cost_status") or default_rescue_cost_status)
    token_unreliable_reason = classify_token_unreliable_reason(
        row,
        token_status=token_status,
        total_tokens=total_tokens,
    )
    row["model_timeout_local_fallback"] = token_unreliable_reason == "model_timeout_with_local_fallback"
    if row["model_timeout_local_fallback"]:
        row["rescue_cost_status"] = "local_after_model_timeout"
    if token_unreliable_reason == "stats_outlier_possible_cumulative":
        row["provider_stats_cumulative_suspected"] = True
        if not row["token_accounting_failure_class"]:
            row["token_accounting_failure_class"] = "provider_stats_outlier"
    row["token_reliable"] = token_unreliable_reason is None
    row["token_unreliable_reason"] = token_unreliable_reason
    row["provider_token_measured"] = row_has_measured_provider_tokens(row)
    row["public_cost_evidence"] = bool(row["provider_token_measured"] and row["token_reliable"])
    success_source = str(row.get("nexus_winner_source") or row.get("source") or "").strip()
    local_success = bool(
        success_source in LOCAL_SUCCESS_SOURCES
        or success_source.startswith("local_preflight")
        or row["rescue_cost_status"].startswith("local")
        or bool(row.get("nexus_rescued", False))
    )
    clean_model_cost_evidence = bool(
        model_calls > 0
        and row["provider_token_measured"]
        and row["token_reliable"]
        and not model_attempt_runner_overhead_polluted(row)
        and not local_success
    )
    if clean_model_cost_evidence:
        cost_evidence_class = "clean_model_cost"
    elif model_attempt_runner_overhead_polluted(row):
        cost_evidence_class = "runner_overhead_polluted"
    elif model_calls <= 0:
        cost_evidence_class = (
            "rescue_only_no_model_call" if local_success or row.get("nexus_internal_delivery_valid") else "no_model_call"
        )
    elif local_success:
        if model_calls > 0:
            if row["provider_token_measured"]:
                cost_evidence_class = "rescue_with_model_fallback_measured"
            else:
                cost_evidence_class = "rescue_with_model_fallback"
        else:
            cost_evidence_class = "rescue_only_local_success"
    elif not row["provider_token_measured"] or not row["token_reliable"]:
        cost_evidence_class = "token_unreliable"
    else:
        cost_evidence_class = "not_clean_model_cost"
    row["local_success_source"] = local_success
    row["clean_model_cost_evidence"] = clean_model_cost_evidence
    row["cost_evidence_class"] = cost_evidence_class
    has_hidden_verifier = bool(row.get("hidden_verifier_passed", False))
    has_gwt_artifact = bool(row.get("gwt_artifact_present", False))
    feature_reflex_training_ok = bool(
        row.get("feature_reflex_route", False)
        and has_gwt_artifact
        and has_hidden_verifier
    )
    training_eligible_cost_evidence = bool(
        row["provider_token_measured"]
        and row["token_reliable"]
        and not model_attempt_runner_overhead_polluted(row)
        and (
            clean_model_cost_evidence
            or feature_reflex_training_ok
        )
    )
    training_reasons: list[str] = []
    if not row["provider_token_measured"]:
        training_reasons.append("provider_tokens_not_measured")
    if not row["token_reliable"]:
        training_reasons.append("token_unreliable")
    if model_attempt_runner_overhead_polluted(row):
        training_reasons.append("runner_overhead_polluted")
    if local_success and not feature_reflex_training_ok:
        training_reasons.append("local_rescue_not_training_eligible")
    if row.get("feature_reflex_route", False) and not has_gwt_artifact:
        training_reasons.append("gwt_artifact_missing")
    if row.get("feature_reflex_route", False) and not has_hidden_verifier:
        training_reasons.append("hidden_verifier_missing")
    row["training_eligible_cost_evidence"] = training_eligible_cost_evidence
    row["training_cost_evidence_class"] = (
        "training_clean_model_cost"
        if clean_model_cost_evidence
        else (
            "training_feature_reflex_verified"
            if feature_reflex_training_ok and training_eligible_cost_evidence
            else "not_training_eligible_cost"
        )
    )
    row["training_cost_evidence_reasons"] = sorted(set(training_reasons))
    winner_source = str(row.get("nexus_winner_source") or "")
    gateway_error_category = str(row.get("gateway_error_category") or "")
    row["local_fallback_unhelpful"] = bool(
        winner_source.startswith("local")
        and model_calls > 0
        and not bool(row.get("semantic_completed", False))
        and (
            total_tokens <= 512
            or gateway_error_category in {"timeout", "parse_failure", "gateway_error"}
            or bool(row.get("fallback_used", False))
        )
    )
    return row
