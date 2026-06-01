from nexus.research.flow.auto_flow_payload import AutoFlowPayloadParts, build_auto_flow_payload


def test_auto_flow_payload_builder_preserves_public_report_shape():
    payload = build_auto_flow_payload(
        AutoFlowPayloadParts(
            task_desc="Fix websocket timeout race",
            task_type="bug",
            asi_ledger=[{"run_id": 1}],
            route={"recommended_flow": "hyper_sprint", "distant_scout_plan": {"status": "not_needed"}},
            execution_profile={"is_hard_task": True},
            chosen_flow="hyper_sprint",
            guard_hit=True,
            early_baseline_shortcut=False,
            history_forced_baseline=False,
            learn_gate_blocked=True,
            force_flow=None,
            recent_hyper_fails=2,
            nightshift_recommended=True,
            stage1_fail_signals=1,
            history_window=0,
            baseline_fast_sec=0.25,
            max_time_ratio_guard=2.0,
            baseline_probe_skipped=True,
            baseline_probe={"status": "SKIPPED"},
            plateau_hard_pivot=False,
            learn_phase_slo={
                "phase_slo_pass": False,
                "global": {"required_done_ratio": 0.9},
                "status": "WARN",
                "reason": "fixture",
            },
            result={"status": "SUCCESS", "report": {"total_tokens": 3}},
            claim_check={"verified": True},
            hitl={"required": False},
            research_preflight={"decision": "allow_with_research_receipt"},
            route_confidence=0.73,
            strategy_path="probe_then_hyper",
            plateau={"detected": False},
            artifact_summary={"changed": True},
            success_criteria_name="artifact_changed_and_tests_pass",
            mutation_required=True,
            verification_only_allowed=False,
            nexus_usage_trace={"phase_wall_sec": {"P": 0.1}},
            cli_elapsed_sec=1.23456,
            phase_wall_sec={"P": 0.1, "R": 0.2},
            timing_breakdown_sec={"target_io_sec": 0.02},
        )
    )

    assert payload["schema_version"] == "1.0"
    assert payload["guard"]["learn_forced_baseline"] is False
    assert payload["guard"]["history_window"] == 1
    assert payload["learn_phase_slo"] == {
        "phase_slo_pass": False,
        "required_done_ratio": 0.9,
        "status": "WARN",
        "reason": "fixture",
    }
    assert payload["strategy"]["path"] == "probe_then_hyper"
    assert payload["strategy"]["forced_flow"] == "auto"
    assert payload["success_criteria"] == {
        "name": "artifact_changed_and_tests_pass",
        "mutation_required": True,
        "verification_only_allowed": False,
    }
    assert payload["timing"]["cli_elapsed_sec"] == 1.2346
    assert payload["io"] == {"output_written": False, "output_path": None}
