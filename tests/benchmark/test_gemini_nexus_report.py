from __future__ import annotations

import json

from scripts.bench.gemini_nexus_report import _public_claim_gate, render_markdown_report


def test_public_claim_gate_rejects_rlm_submit_without_a_gate():
    gate = _public_claim_gate(
        rows_without=[{"task_id": "a", "trial_index": 1, "token_measured": True}],
        rows_with=[
            {
                "task_id": "a",
                "trial_index": 1,
                "rlm_trace_present": True,
                "rlm_submit_count": 1,
                "rlm_verified_count": 0,
                "rlm_audit_rejected_count": 0,
                "rlm_trace_quality_score": 45,
                "status": "SUCCESS",
                "capability_claim_verified": True,
            }
        ],
        summary_without={"token_measured_rate": 1.0},
        summary_with={
            "token_measured_rate": 1.0,
            "gemini_uses_nexus_rate": 1.0,
            "nexus_usage_valid_rate": 1.0,
            "phase_completion_rate": 1.0,
            "claim_verified_rate": 1.0,
        },
        formal={"valid_rate": 1.0},
    )

    assert gate["verdict"] == "FAIL"
    assert "rlm_submit_without_a_gate" in gate["failures"]
    assert "rlm_trace_quality_below_threshold" in gate["failures"]


def test_public_claim_gate_rejects_parallel_smoke_rows():
    gate = _public_claim_gate(
        rows_without=[
            {
                "task_id": "a",
                "trial_index": 1,
                "token_measured": False,
                "parallel_arms_mode": "smoke-only",
            }
        ],
        rows_with=[
            {
                "task_id": "a",
                "trial_index": 1,
                "token_measured": False,
                "parallel_arms_mode": "smoke-only",
            }
        ],
        summary_without={"token_measured_rate": 1.0},
        summary_with={
            "token_measured_rate": 1.0,
            "gemini_uses_nexus_rate": 1.0,
            "nexus_usage_valid_rate": 1.0,
            "phase_completion_rate": 1.0,
            "claim_verified_rate": 1.0,
        },
        formal={"valid_rate": 1.0},
    )

    assert gate["verdict"] == "FAIL"
    assert "parallel_smoke" in gate["failures"]


def test_render_markdown_report_includes_lift_and_wearing_evidence(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    without.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "a",
                        "semantic_status": "VERIFIED",
                        "trial_index": 1,
                        "wall_duration_sec": 10,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                    }
                ),
                json.dumps(
                    {
                        "task_id": "b",
                        "semantic_status": "UNVERIFIED",
                        "trial_index": 1,
                        "wall_duration_sec": 20,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with_nexus.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "a",
                        "semantic_status": "VERIFIED",
                        "trial_index": 1,
                        "wall_duration_sec": 8,
                        "model_calls": 1,
                        "total_tokens": 90,
                        "token_capture_status": "measured",
                        "model_total_tokens": 90,
                        "model_token_capture_status": "measured",
                        "rescue_cost_status": "local_only",
                        "guard_hit": True,
                        "artifact_verification_only": True,
                        "gemini_uses_nexus": True,
                        "nexus_context_delivered": True,
                        "nexus_usage_valid": True,
                        "nexus_rescued": True,
                        "nexus_winner_source": "local",
                        "pillar_lancedb_active": True,
                        "pillar_memory_active": True,
                        "pillar_mempalace_active": True,
                        "pillar_belief_active": True,
                        "pillar_artifact_active": True,
                        "phase_p": "route_built",
                        "phase_x": "retrieval_checked",
                        "phase_d": "guard_decision",
                        "phase_r": "hyper_executed",
                        "phase_a": "artifact_verified",
                        "phase_c": "closure_written",
                        "capability_claim_verified": True,
                        "capability_self_heal_used": False,
                        "capability_hyper_used": True,
                        "capability_swarm_used": True,
                        "capability_drone_used": False,
                        "capability_nightshift_recommended": True,
                        "capability_nightshift_invoked": True,
                        "capability_nightshift_recovered": False,
                        "rlm_trace_present": True,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "b",
                        "semantic_status": "VERIFIED",
                        "trial_index": 1,
                        "wall_duration_sec": 10,
                        "model_calls": 1,
                        "total_tokens": 90,
                        "token_capture_status": "estimated",
                        "gemini_uses_nexus": True,
                        "nexus_context_delivered": True,
                        "nexus_usage_valid": True,
                        "nexus_rescued": False,
                        "nexus_winner_source": "llm_self_heal",
                        "pillar_lancedb_active": True,
                        "pillar_memory_active": True,
                        "pillar_mempalace_active": True,
                        "pillar_belief_active": True,
                        "pillar_artifact_active": True,
                        "phase_p": "route_built",
                        "phase_x": "retrieval_checked",
                        "phase_d": "guard_decision",
                        "phase_r": "hyper_executed",
                        "phase_a": "artifact_verified",
                        "phase_c": "closure_written",
                        "capability_claim_verified": True,
                        "capability_self_heal_used": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "# nexus Benchmark Report" in out
    assert "Without Nexus scope: 2 unique tasks x 1 trials = 2 rows" in out
    assert "With Nexus scope: 2 unique tasks x 1 trials = 2 rows" in out
    assert "Usable rows | 2/2 | 2/2 | n/a" in out
    assert "Infra invalid rows | 0 | 0 | n/a" in out
    assert "Solve rate | 50.0% | 100.0% | 50.0%" in out
    assert "Cost-comparable rate | 100.0% | 50.0% | -50.0%" in out
    assert "Model token measured rate | 0.0% | 50.0% | 50.0%" in out
    assert "Local rescue rate | 0.0% | 50.0% | 50.0%" in out
    assert "Guard fallback rate | 0.0% | 50.0% | 50.0%" in out
    assert "Verification rescue rate | 0.0% | 50.0% | 50.0%" in out
    assert "LLM self-heal rate | 0.0% | 50.0% | 50.0%" in out
    assert "RLM trace present | 0.0% | 50.0% | 50.0%" in out
    assert "## Five-Pillar Contribution" in out
    assert "MemPalace | 0.0% | 100.0% | 100.0%" in out
    assert "Belief | 0.0% | 100.0% | 100.0%" in out
    assert "Artifact / Claim | 0.0% | 100.0% | 100.0%" in out
    assert "Claim verified | 0.0% | 100.0% | 100.0%" in out
    assert "## MSA / Orchestration Trace" in out
    assert "Hyper | 0.0% | 50.0% | 50.0%" in out
    assert "Self-heal | 0.0% | 50.0% | 50.0%" in out
    assert "Swarm | 0.0% | 50.0% | 50.0%" in out
    assert "Drone | 0.0% | 0.0% | 0.0%" in out
    assert "Nightshift recommended | 0.0% | 50.0% | 50.0%" in out
    assert "Nightshift invoked | 0.0% | 50.0% | 50.0%" in out
    assert "Nightshift recovered | 0.0% | 0.0% | 0.0%" in out
    assert "## Capability Win Map" in out
    assert "Token public-safe claim | NO | NO | n/a" in out
    assert "| measured | 2 | 1 |" in out
    assert "| estimated | 0 | 1 |" in out
    assert "Without Nexus infra invalid reasons: none" in out
    assert "Public claim gate: FAIL" in out
    assert "with_token_measured_below_threshold" in out
    assert "Formal treatment valid: 2/2 (100.0%)" in out
    assert "Model uses Nexus rate: 100.0%" in out
    assert "Token/cost claims are not public-safe" in out


def test_render_markdown_report_maps_task_wins_to_capabilities(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    without.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "rlm-harder-v2-governance-001",
                        "trial_index": 1,
                        "semantic_status": "UNVERIFIED",
                        "status": "FAILED",
                        "wall_duration_sec": 20,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                        "run_eligible": True,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "rlm-harder-v2-belief-001",
                        "trial_index": 1,
                        "semantic_status": "UNVERIFIED",
                        "status": "FAILED",
                        "wall_duration_sec": 30,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                        "run_eligible": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with_nexus.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "rlm-harder-v2-governance-001",
                        "trial_index": 1,
                        "semantic_status": "VERIFIED",
                        "status": "SUCCESS",
                        "wall_duration_sec": 10,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                        "run_eligible": True,
                        "gemini_uses_nexus": True,
                        "nexus_context_delivered": True,
                        "nexus_usage_valid": True,
                        "pillar_lancedb_active": True,
                        "pillar_memory_active": True,
                        "pillar_mempalace_active": True,
                        "pillar_belief_active": True,
                        "pillar_artifact_active": True,
                        "phase_p": "route_built",
                        "phase_x": "retrieval_checked",
                        "phase_d": "guard_decision",
                        "phase_r": "hyper_executed",
                        "phase_a": "artifact_verified",
                        "phase_c": "closure_written",
                        "capability_claim_verified": True,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "rlm-harder-v2-belief-001",
                        "trial_index": 1,
                        "semantic_status": "VERIFIED",
                        "status": "SUCCESS",
                        "wall_duration_sec": 12,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                        "run_eligible": True,
                        "gemini_uses_nexus": True,
                        "nexus_context_delivered": True,
                        "nexus_usage_valid": True,
                        "pillar_lancedb_active": True,
                        "pillar_memory_active": True,
                        "pillar_mempalace_active": True,
                        "pillar_belief_active": True,
                        "pillar_artifact_active": True,
                        "phase_p": "route_built",
                        "phase_x": "retrieval_checked",
                        "phase_d": "guard_decision",
                        "phase_r": "hyper_executed",
                        "phase_a": "artifact_verified",
                        "phase_c": "closure_written",
                        "capability_claim_verified": True,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "| rlm-harder-v2-governance-001 | 1 | MemPalace / governance | UNVERIFIED | VERIFIED |" in out
    assert "| rlm-harder-v2-belief-001 | 1 | Belief / Memory | UNVERIFIED | VERIFIED |" in out


def test_render_markdown_report_marks_token_claim_unsafe_when_tokens_missing(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    base = {
        "task_id": "a",
        "trial_index": 2,
        "semantic_status": "VERIFIED",
        "wall_duration_sec": 10,
        "model_calls": 1,
        "total_tokens": 0,
        "token_capture_status": "unknown",
    }
    without.write_text(json.dumps(base) + "\n", encoding="utf-8")
    row = {
        **base,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
        "capability_claim_verified": True,
    }
    with_nexus.write_text(json.dumps(row) + "\n", encoding="utf-8")

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "1 unique tasks x 2 trials = 1 rows" in out
    assert "Token public-safe claim | NO | NO | n/a" in out


def test_render_markdown_report_surfaces_infra_invalid_rows(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    without.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "a",
                        "trial_index": 1,
                        "semantic_status": "VERIFIED",
                        "wall_duration_sec": 10,
                        "model_calls": 1,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                        "run_eligible": True,
                    }
                ),
                json.dumps(
                    {
                        "task_id": "b",
                        "trial_index": 1,
                        "semantic_status": "UNVERIFIED",
                        "wall_duration_sec": 10,
                        "model_calls": 1,
                        "total_tokens": 0,
                        "token_capture_status": "unknown",
                        "run_eligible": False,
                        "infra_invalid_reason": "parse_error",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with_nexus.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "VERIFIED",
                "wall_duration_sec": 8,
                "model_calls": 1,
                "total_tokens": 100,
                "token_capture_status": "measured",
                "run_eligible": True,
                "gemini_uses_nexus": True,
                "nexus_context_delivered": True,
                "nexus_usage_valid": True,
                "pillar_lancedb_active": True,
                "pillar_memory_active": True,
                "pillar_mempalace_active": True,
                "pillar_belief_active": True,
                "pillar_artifact_active": True,
                "phase_p": "route_built",
                "phase_x": "retrieval_checked",
                "phase_d": "guard_decision",
                "phase_r": "hyper_executed",
                "phase_a": "artifact_verified",
                "phase_c": "closure_written",
                "capability_claim_verified": True,
                "autoreason_enabled": True,
                "ddtree_enabled": True,
                "ddtree_eligible": True,
                "ultra_review_recommended": True,
                "ultra_review_invoked": True,
                "capability_plan_trace_present": True,
                "capability_plan_node_count": 12,
                "capability_plan_score": 24,
                "rlm_trace_present": True,
                "rlm_trace_quality_score": 90,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "Usable rows | 1/2 | 1/1 | n/a" in out
    assert "Infra invalid rows | 1 | 0 | n/a" in out
    assert "Eligible solve rate | 100.0% | 100.0% | 0.0%" in out
    assert "Public claim gate: FAIL" in out
    assert "task_trial_mismatch" in out
    assert "Without Nexus infra invalid reasons: parse_error:1" in out
    assert "With Nexus infra invalid reasons: none" in out


def test_render_markdown_report_allows_public_claim_when_gate_passes(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    without.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "UNVERIFIED",
                "wall_duration_sec": 12,
                "model_calls": 1,
                "total_tokens": 120,
                "token_capture_status": "measured",
                "run_eligible": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with_nexus.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "VERIFIED",
                "wall_duration_sec": 9,
                "model_calls": 1,
                "total_tokens": 100,
                "token_capture_status": "measured",
                "run_eligible": True,
                "gemini_uses_nexus": True,
                "nexus_context_delivered": True,
                "nexus_usage_valid": True,
                "pillar_lancedb_active": True,
                "pillar_memory_active": True,
                "pillar_mempalace_active": True,
                "pillar_belief_active": True,
                "pillar_artifact_active": True,
                "phase_p": "route_built",
                "phase_x": "retrieval_checked",
                "phase_d": "guard_decision",
                "phase_r": "hyper_executed",
                "phase_a": "artifact_verified",
                "phase_c": "closure_written",
                "capability_claim_verified": True,
                "autoreason_enabled": True,
                "ddtree_enabled": True,
                "ddtree_eligible": True,
                "ultra_review_recommended": True,
                "ultra_review_invoked": True,
                "capability_plan_trace_present": True,
                "capability_plan_node_count": 12,
                "capability_plan_score": 24,
                "rlm_trace_present": True,
                "rlm_trace_quality_score": 90,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "Public claim gate: PASS" in out
    assert "Public claim gate failures: none" in out
    assert "| RLM trace quality | 0.00 | 90.00 | 90.00 |" in out
    assert "| Autoreason | 0.0% | 100.0% | 100.0% |" in out
    assert "| DDTree enabled | 0.0% | 100.0% | 100.0% |" in out
    assert "| Ultra Review invoked | 0.0% | 100.0% | 100.0% |" in out
    assert "| Capability plan trace | 0.0% | 100.0% | 100.0% |" in out
    assert "## Capability Coverage Matrix" in out
    assert "| autoreason | 100.0% | 100.0% |" in out
    assert "| ddtree | 100.0% | 100.0% |" in out
    assert "| ultra_review | 100.0% | 100.0% |" in out
    assert "Per-capability public gate: FAIL" in out
    assert "Per-capability gate failures:" in out
    assert "| Capability plan nodes | 0.00 | 12.00 | 12.00 |" in out
    assert "On this fixed benchmark set, `nexus` improved eligible solve rate" in out


def test_render_markdown_report_allows_capability_claim_only_with_receipts(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    without.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "UNVERIFIED",
                "wall_duration_sec": 12,
                "model_calls": 1,
                "total_tokens": 120,
                "token_capture_status": "measured",
                "run_eligible": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with_nexus.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "VERIFIED",
                "wall_duration_sec": 9,
                "model_calls": 1,
                "total_tokens": 100,
                "token_capture_status": "measured",
                "run_eligible": True,
                "gemini_uses_nexus": True,
                "nexus_context_delivered": True,
                "nexus_usage_valid": True,
                "pillar_lancedb_active": True,
                "pillar_memory_active": True,
                "pillar_mempalace_active": True,
                "pillar_belief_active": True,
                "pillar_artifact_active": True,
                "phase_p": "route_built",
                "phase_x": "retrieval_checked",
                "phase_d": "guard_decision",
                "phase_r": "hyper_executed",
                "phase_a": "artifact_verified",
                "phase_c": "closure_written",
                "capability_claim_verified": True,
                "capability_receipts": [
                    {
                        "name": "artifact_gate",
                        "selected": True,
                        "invoked": False,
                        "evidence_present": False,
                        "gate_passed": False,
                        "outcome_contributed": False,
                    },
                    {
                        "name": "autoreason",
                        "selected": True,
                        "invoked": True,
                        "evidence_present": True,
                        "gate_passed": True,
                        "outcome_contributed": True,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "Performance claim gate: PASS" in out
    assert "Wearing claim gate: PASS" in out
    assert "Capability-specific claim gate: PASS" in out
    assert "Cost claim gate: PASS" in out
    assert "Per-capability public-safe capabilities: autoreason" in out
    assert "| autoreason | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | YES | capability_receipts | none |" in out


def test_render_markdown_report_explains_selected_only_capability_receipts(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    without.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "VERIFIED",
                "wall_duration_sec": 12,
                "model_calls": 1,
                "total_tokens": 120,
                "token_capture_status": "measured",
                "run_eligible": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with_nexus.write_text(
        json.dumps(
            {
                "task_id": "a",
                "trial_index": 1,
                "semantic_status": "VERIFIED",
                "wall_duration_sec": 9,
                "model_calls": 1,
                "total_tokens": 100,
                "token_capture_status": "measured",
                "run_eligible": True,
                "gemini_uses_nexus": True,
                "nexus_context_delivered": True,
                "nexus_usage_valid": True,
                "phase_p": "route_built",
                "phase_x": "retrieval_checked",
                "phase_d": "guard_decision",
                "phase_r": "hyper_executed",
                "phase_a": "artifact_verified",
                "phase_c": "closure_written",
                "capability_claim_verified": True,
                "capability_receipts": [
                    {
                        "name": "autoreason",
                        "selected": True,
                        "invoked": True,
                        "evidence_present": True,
                        "gate_passed": True,
                        "outcome_contributed": True,
                    },
                    {
                        "name": "swarm",
                        "selected": True,
                        "invoked": False,
                        "evidence_present": False,
                        "gate_passed": False,
                        "outcome_contributed": False,
                        "failure_reason": "selected_without_invocation",
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "Capability-specific claim gate: FAIL" in out
    assert "Per-capability public-safe capabilities: autoreason" in out
    assert "swarm:invoked+evidence+gate" in out
    assert "artifact_gate:invoked+evidence+gate" not in out
    assert "| swarm | 100.0% | 0.0% | 0.0% | 0.0% | 0.0% | NO | capability_receipts | selected_without_invocation:1 |" in out


def test_render_markdown_report_does_not_claim_lift_when_solve_rate_ties(tmp_path):
    without = tmp_path / "without.jsonl"
    with_nexus = tmp_path / "with.jsonl"
    bare = {
        "task_id": "a",
        "trial_index": 1,
        "semantic_status": "VERIFIED",
        "wall_duration_sec": 8,
        "model_calls": 1,
        "total_tokens": 100,
        "token_capture_status": "measured",
        "run_eligible": True,
    }
    nexus = {
        **bare,
        "wall_duration_sec": 9,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
        "capability_claim_verified": True,
    }
    without.write_text(json.dumps(bare) + "\n", encoding="utf-8")
    with_nexus.write_text(json.dumps(nexus) + "\n", encoding="utf-8")

    out = render_markdown_report(
        without_path=str(without),
        with_path=str(with_nexus),
        label_without="bare",
        label_with="nexus",
        benchmark_date="2026-04-27",
    )

    assert "Public claim gate: PASS" in out
    assert "matched eligible solve rate at 100.0%" in out
    assert "improved eligible solve rate from 100.0% to 100.0%" not in out
