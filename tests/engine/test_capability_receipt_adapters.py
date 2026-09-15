from __future__ import annotations

from nexus.engine.capability_receipts import build_trace_receipts


def test_swarm_receipt_requires_report_evidence_for_public_claim():
    plan = {"selected_capabilities": ["swarm"]}

    missing = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": True,
                "swarm_evidence_count": 0,
                "swarm_report": {"schema_version": "nexus_swarm_receipt_v1"},
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "swarm_used": True,
                "swarm_report": {
                    "schema_version": "nexus_swarm_receipt_v1",
                    "source": "local_msa_bench_executor",
                    "evidence_count": 2,
                    "consensus": "pass",
                    "evidence_refs": ["role:logic:evidence:artifact_verified"],
                    "report_path": ".nexus/reports/swarm/run.json",
                },
            },
        )
    }

    assert missing["swarm"].public_claim_safe is False
    assert missing["swarm"].gate_passed is False
    assert missing["swarm"].failure_reason == "invoked_without_evidence"
    assert proven["swarm"].gate_passed is True
    assert proven["swarm"].outcome_contributed is False
    assert proven["swarm"].public_claim_safe is False
    assert "report:.nexus/reports/swarm/run.json" in proven["swarm"].evidence_refs
    assert "role_findings:2" in proven["swarm"].evidence_refs


def test_nightshift_receipt_requires_invoked_recovered_report():
    plan = {"selected_capabilities": ["nightshift"]}

    recommended = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "nightshift_recommended": True,
                "nightshift_invoked": False,
                "nightshift_recovered": False,
                "nightshift_failure_reason": "recommended_without_report",
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "nightshift_report": {
                    "schema_version": "nexus_nightshift_receipt_v1",
                    "source": "local_msa_bench_executor",
                    "recommended": True,
                    "invoked": True,
                    "recovered": True,
                    "report_path": ".nexus/reports/nightshift/run.json",
                    "failure_reason": "",
                },
            },
        )
    }

    assert recommended["nightshift"].public_claim_safe is False
    assert recommended["nightshift"].gate_passed is False
    assert recommended["nightshift"].failure_reason == "recommended_without_report"
    assert proven["nightshift"].gate_passed is True
    assert proven["nightshift"].outcome_contributed is False
    assert proven["nightshift"].public_claim_safe is False
    assert proven["nightshift"].evidence_refs == (".nexus/reports/nightshift/run.json",)


def test_semantic_searcher_receipt_requires_refs_and_gate():
    plan = {"selected_capabilities": ["semantic_searcher"]}

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "semantic_searcher_hits": 2,
                "semantic_searcher_refs": ["semantic:policy:r1"],
                "semantic_searcher_gate_passed": True,
            },
        )
    }

    assert receipts["semantic_searcher"].gate_passed is True
    assert receipts["semantic_searcher"].outcome_contributed is False
    assert receipts["semantic_searcher"].public_claim_safe is False
    assert receipts["semantic_searcher"].evidence_refs == ("semantic:policy:r1",)


def test_harness_receipts_fail_closed_without_typed_evidence():
    plan = {
        "selected_capabilities": [
            "harness_preflight_sensor",
            "semantic_failure_sensor",
            "bdd_acceptance_skill",
        ]
    }

    missing = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "harness_preflight_sensor_used": True,
                "semantic_failure_sensor_used": True,
                "bdd_acceptance_skill_used": True,
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "harness_preflight_sensor_used": True,
                "harness_preflight_refs": [".nexus/reports/capabilities/harness/preflight.json"],
                "capability_wired": True,
                "executor_ready": True,
                "cost_lane": "lite",
                "harness_preflight_sensor_gate_passed": True,
                "semantic_failure_sensor_used": True,
                "semantic_failure_refs": [".nexus/reports/capabilities/failure/sensor.json"],
                "failure_cause": "assertion_mismatch",
                "likely_fix": "align implementation with failing assertion and preserve existing contract",
                "retry_policy": {
                    "max_retries": 1,
                    "allow_blind_retry": False,
                    "requires_evidence_delta": True,
                },
                "semantic_failure_sensor_gate_passed": True,
                "bdd_acceptance_skill_used": True,
                "bdd_acceptance_refs": [".nexus/reports/capabilities/bdd/receipt.json", "artifact:task:tests_passed"],
                "business_verified": True,
                "bdd_acceptance_skill_gate_passed": True,
            },
        )
    }

    for name, receipt in missing.items():
        assert receipt.gate_passed is False, name
        assert receipt.public_claim_safe is False, name
    for name, receipt in proven.items():
        assert receipt.gate_passed is True, name
        assert receipt.outcome_contributed is False, name
        assert receipt.public_claim_safe is False, name

    diagnostic_only = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": False,
                "semantic_failure_sensor_used": True,
                "semantic_failure_refs": [".nexus/reports/capabilities/failure/sensor.json"],
                "failure_cause": "assertion_mismatch",
                "likely_fix": "align implementation with failing assertion and preserve existing contract",
                "retry_policy": {
                    "max_retries": 1,
                    "allow_blind_retry": False,
                    "requires_evidence_delta": True,
                },
                "semantic_failure_sensor_gate_passed": True,
            },
        )
    }
    assert diagnostic_only["semantic_failure_sensor"].gate_passed is True
    assert diagnostic_only["semantic_failure_sensor"].outcome_contributed is False
    assert diagnostic_only["semantic_failure_sensor"].public_claim_safe is False


def test_codeintel_receipt_includes_dci_refs():
    plan = {"selected_capabilities": ["codeintel"]}

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            codeintel={
                "scan_report_present": True,
                "impact_report_present": True,
                "claim_bundle_present": True,
                "scan_report_path": ".nexus/reports/codeintel/scan.json",
                "impact_report_path": ".nexus/reports/codeintel/impact.json",
                "dci_locator_report_path": ".nexus/reports/codeintel/dci.json",
                "dci_evidence_refs": ["dci:nexus/parser.py:L1"],
            },
        )
    }

    assert receipts["codeintel"].gate_passed is True
    assert receipts["codeintel"].outcome_contributed is False
    assert receipts["codeintel"].public_claim_safe is False
    assert ".nexus/reports/codeintel/dci.json" in receipts["codeintel"].evidence_refs
    assert "dci:nexus/parser.py:L1" in receipts["codeintel"].evidence_refs


def test_swarm_quiet_moment_receipt_requires_non_mutating_event():
    plan = {"selected_capabilities": ["swarm_quiet_moment"]}

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "quiet_moment": {
                    "schema_version": "nexus_quiet_moment.v1",
                    "production_writes_allowed": False,
                    "allowed_actions": ["observe", "report", "rollback"],
                    "observe": {"status": "observed"},
                    "rollback": {"status": "armed"},
                },
            },
        )
    }

    assert receipts["swarm_quiet_moment"].gate_passed is False
    assert receipts["swarm_quiet_moment"].outcome_contributed is False
    assert receipts["swarm_quiet_moment"].public_claim_safe is False
    assert "observe:observed" in receipts["swarm_quiet_moment"].evidence_refs


def test_semantic_research_runtime_receipts_require_evidence_and_gate():
    plan = {
        "selected_capabilities": [
            "judge_panel",
            "asi_constraint_extractor",
            "architecture_scout",
            "external_doc_scout",
            "formal_report",
        ]
    }

    missing = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "judge_panel_used": True,
                "asi_constraints": [],
                "architecture_scout_used": True,
                "external_doc_scout_used": True,
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "judge_panel_used": True,
                "judge_panel_votes": [{"judge": "fake", "ranking": ["B", "A"]}],
                "judge_panel_winner": "B",
                "judge_panel_mode": "deterministic_evidence_quality",
                "judge_panel_report_path": ".nexus/reports/judge/panel.json",
                "judge_panel_gate_passed": True,
                "asi_constraints": [{"blocked_pattern": "flow:retry_delay"}],
                "blocked_assumptions": ["flow:retry_delay"],
                "asi_constraint_lookup_refs": ["abc123"],
                "asi_constraint_lookup_matched_count": 1,
                "asi_constraint_lookup_store_path": ".nexus/reports/asi/global_constraints.jsonl",
                "asi_constraint_report_path": ".nexus/reports/asi/constraints.json",
                "asi_constraint_gate_passed": True,
                "architecture_scout_used": True,
                "architecture_scout_report_path": ".nexus/reports/architecture/scout.json",
                "architecture_refs": ["component:timeout_policy"],
                "blast_radius_refs": ["nexus/app/research_flow_service.py"],
                "architecture_scout_gate_passed": True,
                "external_doc_scout_used": True,
                "external_doc_refs": ["https://github.example/issues/42"],
                "verified_claims": ["timeout race known"],
                "external_doc_scout_providers_used": ["github_issue_fetch"],
                "external_doc_scout_cache_status": "miss",
                "external_doc_scout_verified_source_count": 1,
                "external_doc_scout_source_count": 1,
                "external_doc_scout_error_count": 0,
                "external_doc_scout_latency_ms": 2.5,
                "external_doc_scout_cache_age_sec": 0.0,
                "external_doc_scout_gate_passed": True,
                "formal_report_path": ".nexus/reports/formal/report.md",
                "formal_report_schema_version": "nexus_formal_report_v1",
                "verification_summary_ref": "pytest:PASS",
                "formal_report_gate_passed": True,
            },
        )
    }

    for name, receipt in missing.items():
        assert receipt.public_claim_safe is False, name
        assert receipt.gate_passed is False, name
        assert receipt.failure_reason in {"invoked_without_evidence", "selected_without_invocation", "evidence_without_gate_pass"}

    for name, receipt in proven.items():
        assert receipt.gate_passed is True, name
        assert receipt.outcome_contributed is False, name
        assert receipt.public_claim_safe is False, name
        assert receipt.evidence_refs
    assert "lookup_matches:1" in proven["asi_constraint_extractor"].evidence_refs
    assert "verified_sources:1" in proven["external_doc_scout"].evidence_refs
    assert "sources:1" in proven["external_doc_scout"].evidence_refs
    assert "errors:0" in proven["external_doc_scout"].evidence_refs


def test_external_doc_scout_gate_requires_verified_source_count():
    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["external_doc_scout"]},
            capabilities={
                "claim_verified": True,
                "external_doc_scout_used": True,
                "external_doc_refs": ["https://github.example/issues/42"],
                "verified_claims": ["timeout race known"],
                "external_doc_scout_gate_passed": True,
                "external_doc_scout_verified_source_count": 0,
            },
        )
    }

    assert receipts["external_doc_scout"].public_claim_safe is False
    assert receipts["external_doc_scout"].failure_reason == "evidence_without_gate_pass"


def test_external_doc_scout_rejected_only_payload_is_not_invoked_evidence():
    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["external_doc_scout"]},
            capabilities={
                "claim_verified": True,
                "rejected_claims": ["unverified_api_contract"],
                "external_doc_scout_cache_status": "disabled",
                "external_doc_scout_error_count": 0,
            },
        )
    }

    assert receipts["external_doc_scout"].invoked is False
    assert receipts["external_doc_scout"].evidence_present is False
    assert receipts["external_doc_scout"].failure_reason == "selected_without_invocation"


def test_legacy_llm_judge_panel_selected_capability_canonicalizes_to_judge_panel():
    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["llm_judge_panel", "judge_panel"]},
            capabilities={
                "claim_verified": True,
                "llm_judge_panel_used": True,
                "llm_judge_panel_votes": [{"judge": "legacy", "ranking": ["B", "A"]}],
                "llm_judge_panel_winner": "B",
                "llm_judge_panel_mode": "deterministic_evidence_quality",
                "llm_judge_panel_report_path": ".nexus/reports/judge/legacy.json",
                "llm_judge_panel_gate_passed": True,
            },
        )
    }

    assert "llm_judge_panel" not in receipts
    assert receipts["judge_panel"].gate_passed is True
    assert receipts["judge_panel"].outcome_contributed is False
    assert receipts["judge_panel"].public_claim_safe is False


def test_autoreason_receipt_records_discriminator_and_blocks_fatal_winner():
    plan = {"selected_capabilities": ["autoreason"]}

    safe_winner = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            autoreason={
                "enabled": True,
                "status": "SUCCESS",
                "winner": "safe",
                "judge_votes": [{"judge": "deterministic", "ranking": ["safe", "unsafe"]}],
                "adversarial_critique": {
                    "safe": {"fatal": False, "critiques": ["edge risk"], "defenses": ["test covered"]},
                    "unsafe": {"fatal": True, "critiques": ["drops scope guard"], "defenses": []},
                },
            },
        )
    }
    fatal_winner = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={"claim_verified": True},
            autoreason={
                "enabled": True,
                "status": "SUCCESS",
                "winner": "unsafe",
                "judge_votes": [{"judge": "deterministic", "ranking": ["unsafe", "safe"]}],
                "adversarial_critique": {
                    "safe": {"fatal": False, "critiques": [], "defenses": ["test covered"]},
                    "unsafe": {"fatal": True, "critiques": ["drops scope guard"], "defenses": []},
                },
            },
        )
    }

    assert safe_winner["autoreason"].gate_passed is True
    assert safe_winner["autoreason"].outcome_contributed is False
    assert safe_winner["autoreason"].public_claim_safe is False
    assert "discriminator_fatal:unsafe" in safe_winner["autoreason"].evidence_refs
    assert "discriminator_defenses:safe:1" in safe_winner["autoreason"].evidence_refs
    assert fatal_winner["autoreason"].gate_passed is False
    assert fatal_winner["autoreason"].outcome_contributed is False
    assert fatal_winner["autoreason"].public_claim_safe is False
    assert fatal_winner["autoreason"].failure_reason == "evidence_without_gate_pass"


def test_belief_receipt_can_cite_semantic_searcher_evidence_ref():
    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["belief"]},
            capabilities={
                "claim_verified": True,
                "belief_confidence": 0.82,
                "belief_gate_passed": True,
                "semantic_searcher_refs": ["semantic:policy:r1"],
                "semantic_searcher_confidence_source": "semantic_searcher:policy:r1",
            },
        )
    }

    assert receipts["belief"].gate_passed is True
    assert receipts["belief"].outcome_contributed is False
    assert receipts["belief"].public_claim_safe is False
    assert "semantic:policy:r1" in receipts["belief"].evidence_refs
    assert "confidence_source:semantic_searcher:policy:r1" in receipts["belief"].evidence_refs


def test_repair_loop_receipt_requires_trace_and_verified_claim():
    missing = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["repair_loop"]},
            capabilities={"claim_verified": True},
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["repair_loop"]},
            capabilities={
                "claim_verified": True,
                "rlm_trace_present": True,
                "rlm_trace_path": ".nexus/reports/rlm/trace.jsonl",
            },
        )
    }

    assert missing["repair_loop"].gate_passed is False
    assert missing["repair_loop"].public_claim_safe is False
    assert missing["repair_loop"].failure_reason == "selected_without_invocation"
    assert proven["repair_loop"].gate_passed is True
    assert proven["repair_loop"].outcome_contributed is False
    assert proven["repair_loop"].public_claim_safe is False
    assert proven["repair_loop"].evidence_refs == (".nexus/reports/rlm/trace.jsonl",)


def test_repair_loop_receipt_cites_readable_trace_and_attempt_id(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"attempt_id":"r1","status":"APPROVED"}\n', encoding="utf-8")

    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan={"selected_capabilities": ["repair_loop"]},
            capabilities={
                "claim_verified": True,
                "rlm_trace_present": True,
                "rlm_trace_path": str(trace),
                "rlm_attempt_id": "r1",
            },
        )
    }

    assert receipts["repair_loop"].gate_passed is True
    assert receipts["repair_loop"].outcome_contributed is False
    assert receipts["repair_loop"].public_claim_safe is False
    assert f"{trace}" in receipts["repair_loop"].evidence_refs
    assert "rlm_attempt:r1" in receipts["repair_loop"].evidence_refs
    assert "rlm_trace_status:readable_jsonl" in receipts["repair_loop"].evidence_refs


def test_contract_valid_measured_receipt_is_public_claim_safe():
    """G10 Positive Control: prove public_claim_safe is True when all contracts (basic + honest measured telemetry) are met."""
    from nexus.engine.capability_contracts import CapabilityReceipt

    valid_positive = CapabilityReceipt(
        name="test_capability",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_alignment=True,
        telemetries={
            "telemetry_source": "measured",
            "wall_time_ms": 120.0,
            "token_usage": 450,
            "provider_costs": 0.002,
            "overhead_ms": 15.0,
            "model_calls": 1,
            "claimable": True,
        },
    )
    assert valid_positive.public_claim_safe is True

    # G9 Negative Controls: fail-closed on missing key or unavailable source
    missing_key = CapabilityReceipt(
        name="test_capability",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_alignment=True,
        telemetries={
            "telemetry_source": "measured",
            "wall_time_ms": 120.0,
            # token_usage missing
            "provider_costs": 0.002,
            "overhead_ms": 15.0,
        },
    )
    assert missing_key.public_claim_safe is False

    unavailable_telemetry = CapabilityReceipt(
        name="test_capability",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_alignment=True,
        telemetries={
            "telemetry_source": "unavailable",
            "wall_time_ms": None,
            "token_usage": None,
            "provider_costs": None,
            "overhead_ms": None,
            "claimable": False,
        },
    )
    assert unavailable_telemetry.public_claim_safe is False
