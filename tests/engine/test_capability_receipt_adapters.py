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
    assert missing["swarm"].failure_reason == "invoked_without_evidence"
    assert proven["swarm"].public_claim_safe is True
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
    assert recommended["nightshift"].failure_reason == "recommended_without_report"
    assert proven["nightshift"].public_claim_safe is True
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

    assert receipts["semantic_searcher"].public_claim_safe is True
    assert receipts["semantic_searcher"].evidence_refs == ("semantic:policy:r1",)


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

    assert receipts["swarm_quiet_moment"].public_claim_safe is True
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
        assert receipt.failure_reason in {"invoked_without_evidence", "selected_without_invocation", "evidence_without_gate_pass"}

    for name, receipt in proven.items():
        assert receipt.public_claim_safe is True, name
        assert receipt.evidence_refs
    assert "lookup_matches:1" in proven["asi_constraint_extractor"].evidence_refs
    assert "verified_sources:1" in proven["external_doc_scout"].evidence_refs


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
    assert receipts["judge_panel"].public_claim_safe is True
