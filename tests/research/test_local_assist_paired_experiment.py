"""Paired Local Advisor experiment harness — offline injected transports only."""

from __future__ import annotations

from pathlib import Path

from nexus.research.local_assist_paired_experiment import (
    ARM_A,
    ARM_B,
    UNAVAILABLE,
    compare_arms,
    load_task_defs,
    run_paired_task_injected,
    write_experiment_summary,
)
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
    assert comparison["deltas"]["online_token_delta"]["quality"] == "MEASURED"
    assert comparison["deltas"]["online_token_delta"]["value"] == -20
    assert comparison["claim_eligibility"]["token_savings_claim_allowed"] is False
    assert comparison["claim_boundary"]["proven_token_savings"] is False


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
