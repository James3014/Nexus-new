"""Paired Local Advisor experiment harness — offline injected transports only."""

from __future__ import annotations

from pathlib import Path

from nexus.research.local_assist_paired_experiment import (
    ARM_A,
    ARM_B,
    FIXTURE_MEASURED,
    LOCALLY_MEASURED,
    UNAVAILABLE,
    assert_arm_receipt_complete,
    assert_deltas_match_stored,
    compare_arms,
    load_task_defs,
    local_contribution_truth,
    recompute_deltas,
    run_paired_task_injected,
    write_experiment_summary,
)
import pytest
from nexus.services.local_assist_service import LocalAssistService
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider
from nexus.services.unified_runtime import normalize_online_invoker_payload


def _online_invoker(*, tokens: int | None, label: str):
    def invoker(context):
        task_id = str(context.get("task_id", ""))
        prompt = str(context.get("online_prompt") or "")
        usage = {}
        quality_path = tokens is not None
        if quality_path:
            usage = {"total_tokens": tokens, "input_tokens": tokens // 2, "output_tokens": tokens // 2}
        local = context.get("local", {}) if isinstance(context.get("local"), dict) else {}
        local_resp = local.get("response", {}) if isinstance(local.get("response"), dict) else {}
        local_outputs = local_resp.get("local_outputs") or {}
        refs = [f"online:fixture:{task_id}:{label}"]
        if local_outputs:
            refs.append(f"online:fixture:{task_id}:local_context_forwarded")
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=task_id,
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "APPROVED", "patch": f"ok-{label}", "prompt_seen": prompt[:80]},
            raw_response=f"raw-{label}",
            usage=usage,
            error="",
            evidence_refs=refs,
            transport="structured_callable",
            selection_source="injected_transport",
        )

    return invoker


def test_load_task_defs_from_campaign_tree() -> None:
    tasks = load_task_defs("docs/bench/local_assist/tasks")
    assert len(tasks) >= 3
    assert all(t.get("task_id") for t in tasks)


def test_paired_arms_share_identity_and_separate_policies(tmp_path: Path) -> None:
    task = {
        "task_id": "paired-1",
        "task_statement": "advise demo.py advisory",
        "workspace_revision": "rev-paired",
        "allowed_files": ["demo.py"],
        "task_type": "repair",
    }
    (tmp_path / "demo.py").write_text("x=1\n", encoding="utf-8")
    local = LocalAssistService(
        provider=InjectedLocalModelProvider(lambda _r: "local diagnosis for arm B")
    )
    comparison = run_paired_task_injected(
        task,
        online_invoker_a=_online_invoker(tokens=100, label="A"),
        online_invoker_b=_online_invoker(tokens=80, label="B"),
        local_service_b=local,
        project_root=tmp_path,
    )
    assert comparison["arm_a"]["arm"] == ARM_A
    assert comparison["arm_b"]["arm"] == ARM_B
    assert comparison["arm_a"]["local_assist_policy"] == "disabled"
    assert comparison["arm_b"]["local_assist_policy"] == "advisor"
    assert comparison["arm_a"]["task_id"] == comparison["arm_b"]["task_id"] == "paired-1"
    assert comparison["arm_a"]["workspace_revision"] == "rev-paired"
    assert comparison["arm_a"]["local_invoked"] is False
    assert comparison["arm_b"]["local_invoked"] is True
    assert comparison["arm_b"]["local_contribution_observed"] is True
    assert comparison["deltas"]["online_token_delta"]["quality"] == FIXTURE_MEASURED
    assert comparison["deltas"]["online_token_delta"]["value"] == -20
    assert comparison["deltas"]["end_to_end_latency_delta"]["quality"] == LOCALLY_MEASURED
    assert comparison["arm_a"]["total_tokens"]["quality"] == FIXTURE_MEASURED
    assert comparison["claim_eligibility"]["token_savings_claim_allowed"] is False
    assert comparison["claim_boundary"]["proven_token_savings"] is False
    assert_deltas_match_stored(comparison)


def test_missing_usage_is_unavailable_not_zero(tmp_path: Path) -> None:
    task = {
        "task_id": "paired-missing-usage",
        "task_statement": "advisory",
        "workspace_revision": "rev-2",
        "allowed_files": ["demo.py"],
    }
    (tmp_path / "demo.py").write_text("x=1\n", encoding="utf-8")
    comparison = run_paired_task_injected(
        task,
        online_invoker_a=_online_invoker(tokens=None, label="A"),
        online_invoker_b=_online_invoker(tokens=None, label="B"),
        local_service_b=None,
        project_root=tmp_path,
    )
    assert comparison["arm_a"]["total_tokens"]["quality"] == UNAVAILABLE
    assert comparison["arm_a"]["total_tokens"]["value"] is None
    assert comparison["deltas"]["online_token_delta"]["quality"] == UNAVAILABLE
    assert comparison["claim_eligibility"]["paired_measured"] is False


def test_write_experiment_summary_claim_boundary(tmp_path: Path) -> None:
    path = write_experiment_summary(
        tmp_path / "summary.json",
        [{"task_id": "x"}],
        status="HARNESS_READY_NOT_LIVE_MEASURED",
    )
    data = path.read_text(encoding="utf-8")
    assert "HARNESS_READY_NOT_LIVE_MEASURED" in data
    assert "proven_token_savings" in data


def test_local_contribution_requires_full_chain() -> None:
    assert (
        local_contribution_truth(
            local_invoked=True,
            local_output_delivered=True,
            local_context_forwarded=True,
            online_received_context=True,
            online_output_delivered=True,
        )
        is True
    )
    assert (
        local_contribution_truth(
            local_invoked=True,
            local_output_delivered=True,
            local_context_forwarded=True,
            online_received_context=False,
            online_output_delivered=True,
        )
        is False
    )
    # Advisor mode alone is insufficient.
    assert (
        local_contribution_truth(
            local_invoked=False,
            local_output_delivered=False,
            local_context_forwarded=False,
            online_received_context=False,
            online_output_delivered=True,
        )
        is False
    )


def test_recompute_deltas_fail_closed_on_incomplete() -> None:
    with pytest.raises(ValueError, match="incomplete_arm_data"):
        recompute_deltas({"total_tokens": {"value": 1, "quality": FIXTURE_MEASURED}}, {})


def test_same_revision_arm_enforcement(tmp_path: Path) -> None:
    from nexus.research.local_assist_paired_experiment import ArmResult, MetricValue

    a = ArmResult(
        arm=ARM_A,
        task_id="t",
        workspace_revision="rev-a",
        local_assist_policy="disabled",
        online_provider="fixture",
        total_tokens=MetricValue(10, FIXTURE_MEASURED),
        online_latency_ms=MetricValue(1, LOCALLY_MEASURED),
        end_to_end_latency_ms=MetricValue(1, LOCALLY_MEASURED),
    )
    b = ArmResult(
        arm=ARM_B,
        task_id="t",
        workspace_revision="rev-b",
        local_assist_policy="advisor",
        online_provider="fixture",
        total_tokens=MetricValue(8, FIXTURE_MEASURED),
        online_latency_ms=MetricValue(1, LOCALLY_MEASURED),
        end_to_end_latency_ms=MetricValue(1, LOCALLY_MEASURED),
    )
    with pytest.raises(ValueError, match="arm_workspace_revision_mismatch"):
        compare_arms(a, b)


def test_same_provider_arm_enforcement() -> None:
    from nexus.research.local_assist_paired_experiment import ArmResult, MetricValue

    a = ArmResult(
        arm=ARM_A,
        task_id="t",
        workspace_revision="rev-1",
        local_assist_policy="disabled",
        online_provider="gemini",
        total_tokens=MetricValue(10, FIXTURE_MEASURED),
        online_latency_ms=MetricValue(1, LOCALLY_MEASURED),
        end_to_end_latency_ms=MetricValue(1, LOCALLY_MEASURED),
        online_invoked=False,
    )
    b = ArmResult(
        arm=ARM_B,
        task_id="t",
        workspace_revision="rev-1",
        local_assist_policy="advisor",
        online_provider="codex",
        total_tokens=MetricValue(8, FIXTURE_MEASURED),
        online_latency_ms=MetricValue(1, LOCALLY_MEASURED),
        end_to_end_latency_ms=MetricValue(1, LOCALLY_MEASURED),
        online_invoked=False,
    )
    with pytest.raises(ValueError, match="arm_online_provider_mismatch"):
        compare_arms(a, b)


def test_incomplete_receipt_rejected() -> None:
    from nexus.research.local_assist_paired_experiment import ArmResult, MetricValue

    incomplete = ArmResult(
        arm=ARM_A,
        task_id="t",
        workspace_revision="rev-1",
        local_assist_policy="disabled",
        online_provider="fixture",
        online_invoked=True,
        total_tokens=MetricValue(10, FIXTURE_MEASURED),
        end_to_end_latency_ms=MetricValue(5, LOCALLY_MEASURED),
        receipt={},  # missing online receipt payload
        receipt_path="",
    )
    with pytest.raises(ValueError, match="incomplete_receipt"):
        assert_arm_receipt_complete(incomplete)


def test_online_auth_error_is_not_delivery() -> None:
    from nexus.services.unified_runtime import (
        normalize_online_invoker_payload,
        online_payload_indicates_non_delivery,
    )

    raw = (
        "Error authenticating: IneligibleTierError: This client is no longer "
        "supported for Gemini Code Assist for individuals."
    )
    payload = normalize_online_invoker_payload(
        provider="gemini",
        task_id="t-auth",
        invoked=True,
        output_delivered=True,  # caller may mis-mark; normalize must fail closed
        gate_passed=True,
        provider_call_count=1,
        response={"status": "FAIL", "error": "IneligibleTierError"},
        raw_response=raw,
        usage={},
        error="",
        evidence_refs=["online:t-auth:gateway"],
        transport="gateway_compatibility",
        selection_source="cli_task_policy",
    )
    assert online_payload_indicates_non_delivery(payload) is True
    assert payload["output_delivered"] is False
    assert payload["gate_passed"] is False
    assert payload["error"]
