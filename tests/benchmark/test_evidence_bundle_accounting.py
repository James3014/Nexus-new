from __future__ import annotations

from scripts.bench.evidence_bundle_accounting import build_public_cost_accounting_context


def _row(
    *,
    task_id: str,
    trial_index: int,
    mode: str,
    wall: float,
    tokens: int,
    prompt_chars: int,
    hidden_retry_wall: float = 0.0,
    hidden_retry_tokens: int = 0,
) -> dict:
    return {
        "task_id": task_id,
        "trial_index": trial_index,
        "mode": mode,
        "run_eligible": True,
        "wall_duration_sec": wall,
        "total_tokens": tokens,
        "model_total_tokens": tokens,
        "model_calls": 1,
        "token_measured": True,
        "token_capture_status": "measured",
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_prompt_chars": prompt_chars,
        "hidden_retry_wall_sec": hidden_retry_wall,
        "hidden_retry_tokens": hidden_retry_tokens,
    }


def test_build_public_cost_accounting_context_centralizes_cost_ratios_and_rates():
    with_rows = [
        _row(task_id="a", trial_index=0, mode="with_nexus", wall=3.0, tokens=60, prompt_chars=102),
        _row(
            task_id="b",
            trial_index=0,
            mode="with_nexus",
            wall=6.0,
            tokens=90,
            prompt_chars=102,
            hidden_retry_wall=0.3,
            hidden_retry_tokens=9,
        ),
    ]
    without_rows = [
        _row(task_id="a", trial_index=0, mode="without_nexus", wall=2.0, tokens=30, prompt_chars=100),
        _row(task_id="b", trial_index=0, mode="without_nexus", wall=4.0, tokens=45, prompt_chars=100),
    ]

    context = build_public_cost_accounting_context(
        with_rows=with_rows,
        without_rows=without_rows,
        eligible_with=with_rows,
        eligible_without=without_rows,
        config={"min_required_pairs_for_efficiency_claim": 2},
        with_semantic_verified_rate=0.75,
        without_semantic_verified_rate=0.25,
        with_trust_mismatch_rate=0.0,
        without_trust_mismatch_rate=0.0,
    )

    assert context.with_avg_wall_sec == 4.5
    assert context.without_avg_wall_sec == 3.0
    assert context.wall_cost_ratio_with_over_without == 1.5
    assert context.token_cost_ratio_with_over_without == 2.0
    assert context.model_call_ratio_with_over_without == 1.0
    assert context.verified_lift_rate == 0.5
    assert context.token_roi_status == "LIFT_WITH_OVERHEAD"
    assert context.retry_cost_share_wall == 0.0333
    assert context.retry_cost_share_tokens == 0.06
    assert context.paired_wall_ratios == [1.5, 1.5]
    assert context.paired_token_ratios == [2.0, 2.0]
    assert context.cost_efficiency_sample_sufficient is True
    assert context.valid_comparison_ready is True
    assert context.provider_token_measured_rate_with == 1.0
    assert context.provider_token_measured_rate_without == 1.0


def test_build_public_cost_accounting_context_keeps_prompt_purity_and_systemic_regression_flags():
    with_rows = [
        _row(task_id="a", trial_index=0, mode="with_nexus", wall=10.0, tokens=90, prompt_chars=140),
    ]
    without_rows = [
        _row(task_id="a", trial_index=0, mode="without_nexus", wall=4.0, tokens=30, prompt_chars=100),
    ]

    context = build_public_cost_accounting_context(
        with_rows=with_rows,
        without_rows=without_rows,
        eligible_with=with_rows,
        eligible_without=without_rows,
        config={
            "prompt_purity_threshold": 1.02,
            "route_cost_regression_wall_ratio_threshold": 1.8,
            "route_cost_regression_token_ratio_threshold": 1.5,
        },
        with_semantic_verified_rate=1.0,
        without_semantic_verified_rate=1.0,
        with_trust_mismatch_rate=0.0,
        without_trust_mismatch_rate=0.0,
    )

    assert context.max_prompt_purity_index == 1.4
    assert context.prompt_purity_gate_passed is False
    assert context.wall_regression_systemic is True
    assert context.token_regression_systemic is True
    assert context.verified_equal_without_lift is True
    assert context.eligibility_complete is True
