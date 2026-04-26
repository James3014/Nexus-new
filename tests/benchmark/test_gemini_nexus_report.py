from __future__ import annotations

import json

from scripts.bench.gemini_nexus_report import render_markdown_report


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
                        "gemini_uses_nexus": True,
                        "nexus_context_delivered": True,
                        "nexus_usage_valid": True,
                        "nexus_rescued": True,
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

    assert "Without Nexus scope: 2 unique tasks x 1 trials = 2 rows" in out
    assert "With Nexus scope: 2 unique tasks x 1 trials = 2 rows" in out
    assert "Solve rate | 50.0% | 100.0% | 50.0%" in out
    assert "Token public-safe claim | NO | NO | n/a" in out
    assert "| measured | 2 | 1 |" in out
    assert "| estimated | 0 | 1 |" in out
    assert "Formal treatment valid: 2/2 (100.0%)" in out
    assert "Gemini uses Nexus rate: 100.0%" in out
    assert "Token/cost claims are not public-safe" in out


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
