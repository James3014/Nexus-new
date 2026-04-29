import pytest
import json
from types import SimpleNamespace
from pathlib import Path
from nexus.app import research_flow_service
from nexus.research.learn_mode import LearnModeService

def test_build_route_returns_complete_fields(tmp_path: Path):
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="Fix flaky timeout",
        task_type="bug",
        candidate_count=2,
        root_cause_confidence=0.4,
        findings_query=None,
    )
    
    assert "should_research" in out
    assert "mode" in out
    assert "reason" in out
    assert "recommended_flow" in out
    assert "explain_payload" in out
    assert "route_features" in out
    assert "consensus" in out
    assert "capability_stack" in out
    assert out["capability_stack"]["selected_capabilities"] == ["hyper_sprint", "autoreason"]
    assert out["capability_stack"]["acceleration_layers"] == ["ddtree"]
    assert out["capability_stack"]["governance_layers"] == ["ultra_review"]
    assert out["explain_payload"]["risk"] == "CRITICAL"
    assert out["route_features"]["risk_score"] >= 50
    assert out["consensus"]["winner"] in {"baseline", "hyper_sprint"}
    assert out["recommended_flow"] == "hyper_sprint"
    assert out["recommended_reason"] == "complex_bug_prefer_hyper"
    assert out["should_research"] is True


def test_compose_capability_plan_preserves_legacy_stack_shape():
    out = research_flow_service.compose_capability_plan(
        task_desc="Fix flaky timeout with evidence and governance risk",
        task_type="bug",
        recommended_flow="hyper_sprint",
        route_features={
            "candidate_count": 3,
            "risk_score": 80,
            "has_hard_signal": True,
            "adjusted_root_cause_confidence": 0.4,
        },
        target_file="nexus/app/research_flow_service.py",
    )

    assert out["selected_capabilities"] == ["hyper_sprint", "autoreason"]
    assert out["acceleration_layers"] == ["ddtree"]
    assert out["governance_layers"] == ["ultra_review"]
    assert out["stop_policy"]["type"] == "a_streak"
    assert out["explain_caps"][0]["capability"] == "hyper_sprint"


def test_collect_route_signals_includes_history_memory_hits(tmp_path: Path):
    history_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "a|b": [
                    {
                        "flow": "hyper_sprint",
                        "status": "SUCCESS",
                        "reason": "stage1_pass",
                        "task_type": "bug",
                        "task_desc": "fix websocket timeout race in coordinator",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    signals = research_flow_service._collect_route_signals(
        repo_root=tmp_path,
        task_desc="fix websocket timeout race in orchestrator",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query="",
        target_file="demo.py",
    )

    assert signals["memory_hits"] >= 1
    assert signals["adjusted_root_cause_confidence"] == pytest.approx(0.8)
    assert signals["has_hard_signal"] is True


def test_decide_flow_preserves_core_route_cases(tmp_path: Path):
    def decide(task_desc, task_type, confidence=0.9, candidate_count=1, target_file=None):
        signals = research_flow_service._collect_route_signals(
            repo_root=tmp_path,
            task_desc=task_desc,
            task_type=task_type,
            candidate_count=candidate_count,
            root_cause_confidence=confidence,
            findings_query="",
            target_file=target_file,
        )
        return research_flow_service._decide_flow(
            task_desc=task_desc,
            task_type=task_type,
            candidate_count=candidate_count,
            target_file=target_file,
            signals=signals,
        )

    doc = decide("fix typo in README", "bug", target_file="README.md")
    public = decide("Fix claim verification evidence governance", "public_feature")
    hard_bug = decide("Fix flaky websocket timeout", "bug", confidence=0.4)
    feature = decide("Add small UI option", "feature")
    refactor = decide("Refactor helper", "refactor")

    assert (doc["recommended_flow"], doc["recommended_reason"]) == ("baseline", "Matched Doc-Fix Rule")
    assert (public["recommended_flow"], public["recommended_reason"]) == (
        "hyper_sprint",
        "commercial_public_task_prefers_hyper",
    )
    assert (hard_bug["recommended_flow"], hard_bug["recommended_reason"]) == ("hyper_sprint", "complex_bug_prefer_hyper")
    assert feature["recommended_flow"] == "baseline"
    assert refactor["recommended_flow"] == "baseline"


def test_route_executor_flags_enable_dynamic_controls_for_repair_and_governance():
    route = {
        "capability_stack": {"selected_capabilities": ["baseline"], "acceleration_layers": []},
        "route_features": {"candidate_count": 1},
    }
    repair = research_flow_service.build_route_executor_flags(
        task_desc="Repair a flaky-looking timeout calculation without deleting assertions.",
        task_type="public_test_repair",
        route=route,
    )
    governance = research_flow_service.build_route_executor_flags(
        task_desc="Refactor credential scrubber while preserving secret redaction.",
        task_type="public_refactor",
        route=route,
    )

    assert repair["enable_autoreason_executor"] is True
    assert repair["enable_ddtree_executor"] is True
    assert governance["enable_autoreason_executor"] is True


def test_codeintel_context_is_injected_into_task_text():
    text = research_flow_service._task_with_codeintel_context(
        "Fix parser",
        {
            "impact_report_present": True,
            "impact_report_path": ".nexus/reports/codeintel/impact.json",
            "risk_score": 42,
            "impacted_files_count": 3,
            "risk_reason": ["reverse_import_impact"],
        },
    )

    assert "[Nexus CodeIntel]" in text
    assert "impact_report" in text
    assert "risk_score: 42" in text


def test_build_hyper_execution_profile_boosts_hard_bug():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="Fix flaky websocket timeout race with deadlock symptoms",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.6,
        route_recommended_flow="hyper_sprint",
    )

    assert profile["effective_candidate_count"] >= 4
    assert profile["effective_max_rounds"] >= 3
    assert profile["effective_stage1_max_parallel"] >= 2
    assert profile["is_hard_task"] is True


def test_build_hyper_execution_profile_honors_llm_candidate_cap(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_CANDIDATE_CAP", "1")
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="Fix flaky websocket timeout race with deadlock symptoms",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.6,
        route_recommended_flow="hyper_sprint",
    )

    assert profile["effective_candidate_count"] == 1


def test_build_route_cross_module_task_has_high_risk_feature(tmp_path: Path):
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="Cross-module refactor for swarm/drone/nightshift handoff",
        task_type="cross_module_refactor_drone",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query=None,
    )
    assert out["route_features"]["is_cross_module_task"] is True
    assert out["route_features"]["risk_score"] >= 50


def test_build_route_treats_public_commercial_tasks_as_hard(tmp_path: Path):
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="Fix claim verification so only fully supported successful claims are accepted.",
        task_type="public_feature",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query=None,
    )

    assert out["recommended_flow"] == "hyper_sprint"
    assert out["should_research"] is True
    assert out["route_features"]["has_hard_signal"] is True
    assert out["route_features"]["risk_score"] >= 50
    assert out["reason"] == "commercial_public_task_prefers_hyper"


def test_build_hyper_execution_profile_treats_public_commercial_tasks_as_hard():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="Fix claim verification so only fully supported successful claims are accepted.",
        task_type="public_feature",
        candidate_count=1,
        root_cause_confidence=0.9,
        route_recommended_flow="hyper_sprint",
    )

    assert profile["is_hard_task"] is True
    assert profile["effective_candidate_count"] >= 3
    assert "commercial_public_task" in profile["tuning_reasons"]


def test_build_hyper_execution_profile_prefers_direct_hyper_for_cross_module():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="cross-module refactor for swarm and drone coordination",
        task_type="cross_module_refactor_swarm",
        candidate_count=1,
        root_cause_confidence=0.9,
        route_recommended_flow="hyper_sprint",
    )
    assert profile["is_cross_module"] is True
    assert profile["prefer_direct_hyper"] is True


def test_nexus_tier_marks_low_risk_as_light_and_high_risk_as_full():
    light = research_flow_service._nexus_tier({"risk_score": 20}, force_flow=None)
    full = research_flow_service._nexus_tier({"risk_score": 65}, force_flow=None)
    forced = research_flow_service._nexus_tier({"risk_score": 10}, force_flow="hyper_sprint")

    assert light == {"tier": "light", "reason": "low_risk_light_governance", "risk_score": 20}
    assert full["tier"] == "full"
    assert forced["tier"] == "full"


def test_capability_evidence_requires_real_swarm_signal():
    out = research_flow_service._capability_evidence(
        result_report={
            "winner_source": "llm",
            "candidate_summaries": [{"source": "llm", "hint": "plain candidate"}],
        },
        learning_trace={},
        nightshift_recommended=False,
    )

    assert out["swarm_used"] is False
    assert out["swarm_evidence_count"] == 0

    with_swarm = research_flow_service._capability_evidence(
        result_report={
            "candidate_summaries": [
                {"source": "llm", "hint": "patch | create:0.10s sync:0.20s test:0.30s"}
            ],
        },
        learning_trace={},
        nightshift_recommended=True,
    )

    assert with_swarm["swarm_used"] is True
    assert with_swarm["swarm_evidence_count"] == 1
    assert with_swarm["swarm_consensus"] == "candidate_summary_evidence"
    assert with_swarm["swarm_report"]["schema_version"] == "nexus_swarm_receipt_v1"
    assert with_swarm["swarm_report"]["evidence_refs"] == ["candidate_summary:0"]
    assert with_swarm["nightshift_recommended"] is True
    assert with_swarm["nightshift_failure_reason"] == "recommended_without_report"


def test_capability_evidence_splits_nightshift_and_drone_signals():
    out = research_flow_service._capability_evidence(
        result_report={},
        learning_trace={
            "nightshift_report_path": ".nexus/reports/nightshift/run.json",
            "nightshift_recovered": True,
            "drone_crystals": ["d1_crystal.json", "d2_crystal.json"],
        },
        nightshift_recommended=True,
    )

    assert out["nightshift_recommended"] is True
    assert out["nightshift_invoked"] is True
    assert out["nightshift_recovered"] is True
    assert out["drone_used"] is True
    assert out["drone_invoked_count"] == 2
    assert out["drone_artifact_path"] == "d1_crystal.json"
    assert out["drone_report"] == {
        "schema_version": "nexus_drone_receipt_v1",
        "source": "drone_crystals",
        "artifact_paths": ["d1_crystal.json", "d2_crystal.json"],
        "artifact_count": 2,
    }
    assert out["nightshift_report"] == {
        "schema_version": "nexus_nightshift_receipt_v1",
        "recommended": True,
        "invoked": True,
        "recovered": True,
        "report_path": ".nexus/reports/nightshift/run.json",
        "failure_reason": "",
    }
    assert out["nightshift_failure_reason"] == ""


def test_write_msa_receipt_reports_persists_swarm_and_drone_artifacts(tmp_path: Path):
    evidence = {
        "swarm_report": {
            "schema_version": "nexus_swarm_receipt_v1",
            "evidence_count": 2,
            "consensus": "candidate_summary_evidence",
            "evidence_refs": ["candidate_summary:0", "candidate_summary:1"],
        },
        "drone_report": {
            "schema_version": "nexus_drone_receipt_v1",
            "artifact_count": 1,
            "artifact_paths": [".nexus/reports/drones/d1_crystal.json"],
        },
    }

    out = research_flow_service._write_msa_receipt_reports(tmp_path, task_id="xmod-hard-001", evidence=evidence)

    swarm_path = Path(out["swarm_report_path"])
    drone_path = Path(out["drone_report_path"])
    assert swarm_path.exists()
    assert drone_path.exists()
    assert json.loads(swarm_path.read_text(encoding="utf-8"))["schema_version"] == "nexus_swarm_receipt_v1"
    assert json.loads(drone_path.read_text(encoding="utf-8"))["artifact_count"] == 1


def test_run_auto_flow_exposes_swarm_report_in_usage_trace(tmp_path: Path, monkeypatch):
    target = tmp_path / "demo.py"
    test_file = tmp_path / "test_demo.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    test_file.write_text("from demo import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8")

    def fake_hyper(*, repo_root, config):
        from nexus.research.sprint_service import SprintResult

        return SprintResult(
            status="SUCCESS",
            reason="ok",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            learning_trace={"mempalace_verified": True, "learn_phase_bridge": True},
            candidates=[],
            pytest_cmd=[],
            patch="def value():\n    return 2\n",
        )

    monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_hyper)

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix cross-module swarm issue",
        target_file="demo.py",
        test_file="test_demo.py",
        task_type="cross_module_refactor_swarm",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=10,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=0.0,
        history_window=1,
        history_fail_threshold=999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=1,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
        task_id="case-123",
    )

    capabilities = payload["nexus_usage_trace"]["capabilities"]
    assert capabilities["swarm_report"]["schema_version"] == "nexus_swarm_receipt_v1"
    assert capabilities["drone_report"]["schema_version"] == "nexus_drone_receipt_v1"
    assert capabilities["nightshift_report"]["schema_version"] == "nexus_nightshift_receipt_v1"


def test_ultra_review_gate_evidence_is_feature_flagged(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_ULTRA_REVIEW_DRY_GATE", raising=False)

    out = research_flow_service._ultra_review_gate_evidence(
        repo_root=tmp_path,
        task_desc="fix risky orchestrator bug",
        capability_stack={"governance_layers": ["ultra_review"]},
    )

    assert out["recommended"] is True
    assert out["invoked"] is False
    assert out["gate_passed"] is None
    assert out["reason"] == "feature_flag_disabled"


def test_ultra_review_gate_evidence_runs_dry_gate_when_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DRY_GATE", "1")

    class _Service:
        def __init__(self, repo_root):
            self.repo_root = repo_root

        def run(self, **kwargs):
            return {
                "schema_version": "ultra-review.v1",
                "gate_passed": True,
                "mode": "dry-run",
                "sandbox_path": str(tmp_path / "sandbox"),
                "artifacts": {"diff": str(tmp_path / "diff"), "git_status": str(tmp_path / "status")},
                "diff": {"changed_files": []},
                "verification": {"reproduction_required": True},
                "ghost_regression": {"passed": True},
                "logic_breaker": {"passed": True},
                "security_sentry": {"passed": True},
                "fleet": [
                    {"lane": "security_sentry"},
                    {"lane": "logic_breaker"},
                    {"lane": "ghost_regression"},
                ],
                "findings": [],
            }

    monkeypatch.setattr("nexus.engine.ultra_review_service.UltraReviewService", _Service)
    monkeypatch.setattr("scripts.ops.ultra_gate.evaluate_report", lambda payload, check_artifacts=False: (True, []))

    out = research_flow_service._ultra_review_gate_evidence(
        repo_root=tmp_path,
        task_desc="fix risky orchestrator bug",
        capability_stack={"governance_layers": ["ultra_review"]},
    )

    assert out["recommended"] is True
    assert out["invoked"] is True
    assert out["gate_passed"] is True
    assert out["reason"] == "dry_gate_passed"


def test_build_hyper_execution_profile_keeps_light_for_simple_task():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="Fix typo in markdown title",
        task_type="doc-fix",
        candidate_count=1,
        root_cause_confidence=0.95,
        route_recommended_flow="baseline",
    )

    assert profile["effective_candidate_count"] == 1
    assert profile["effective_max_rounds"] == 1
    assert profile["effective_stage1_max_parallel"] == 1
    assert profile["is_hard_task"] is False


def test_build_hyper_execution_profile_promotes_budget_for_low_belief():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="fix parser bug",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.95,
        route_recommended_flow="baseline",
        belief_confidence=0.4,
    )
    assert profile["effective_candidate_count"] >= 4
    assert profile["effective_max_rounds"] >= 3
    assert "low_belief_confidence" in profile["tuning_reasons"]


def test_read_belief_confidence_fast_reads_file(tmp_path: Path):
    path = tmp_path / ".nexus" / "belief_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"confidence": 0.42}', encoding="utf-8")
    out = research_flow_service.read_belief_confidence_fast(tmp_path)
    assert out == 0.42


def test_read_capability_tuning_fast_reads_file(tmp_path: Path):
    path = tmp_path / ".nexus" / "config" / "capability_tuning.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"knobs":{"candidate_boost":1}}', encoding="utf-8")
    out = research_flow_service.read_capability_tuning_fast(tmp_path)
    assert out["knobs"]["candidate_boost"] == 1


def test_read_capability_tuning_fast_honors_env_override(tmp_path: Path, monkeypatch):
    override = tmp_path / "override.json"
    override.write_text('{"knobs":{"max_rounds_boost":2}}', encoding="utf-8")
    monkeypatch.setenv("NEXUS_CAPABILITY_TUNING_FILE", str(override))
    out = research_flow_service.read_capability_tuning_fast(tmp_path)
    assert out["knobs"]["max_rounds_boost"] == 2


def test_build_hyper_execution_profile_applies_tuning_and_prior_fix_hits():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="fix flaky websocket timeout race",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.95,
        route_recommended_flow="hyper_sprint",
        belief_confidence=1.0,
        prior_fix_hits=3,
        tuning={"knobs": {"candidate_boost": -1, "max_rounds_boost": 1, "stage1_parallel_boost": -1}},
    )
    assert profile["effective_candidate_count"] >= 4
    assert profile["effective_max_rounds"] >= 3
    assert profile["effective_stage1_max_parallel"] >= 1
    assert "prior_fix_hits_boost" in profile["tuning_reasons"]
    assert any(item.startswith("tuning_") for item in profile["tuning_reasons"])


def test_build_hyper_execution_profile_accelerates_first_pass_for_strong_prior_hits():
    profile = research_flow_service.build_hyper_execution_profile(
        task_desc="fix flaky websocket timeout race",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.7,
        route_recommended_flow="hyper_sprint",
        prior_fix_hits=3,
        tuning={},
    )
    assert profile["effective_candidate_count"] >= 6
    assert profile["effective_stage1_max_parallel"] >= 3
    assert "prior_fix_hits_first_pass_accelerate" in profile["tuning_reasons"]


def test_read_phase_slo_summary_fast_reads_existing_file(tmp_path: Path):
    path = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"phase_slo_pass": true, "global": {"required_done_ratio": 1.0}}', encoding="utf-8")
    payload = research_flow_service.read_phase_slo_summary_fast(tmp_path)
    assert payload["phase_slo_pass"] is True
    assert payload["global"]["required_done_ratio"] == 1.0


def test_read_phase_slo_summary_fast_returns_default_when_missing(tmp_path: Path):
    payload = research_flow_service.read_phase_slo_summary_fast(tmp_path)
    assert payload["phase_slo_pass"] is False
    assert payload["status"] == "UNAVAILABLE"


def test_build_route_uses_auto_findings_query_when_not_provided(tmp_path: Path, monkeypatch):
    captured = {}

    class _Hit:
        def __init__(self):
            self.retrieval_hints = ["retry", "websocket"]

    class _Store:
        def __init__(self, _root):
            pass

        def search(self, query):
            captured["query"] = query
            return [_Hit()]

    monkeypatch.setattr(research_flow_service, "FindingsMemoryStore", _Store)
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query=None,
        target_file="demo.py",
    )
    assert "flaky websocket timeout race" in captured["query"]
    assert "demo.py" in captured["query"]
    assert out["findings_hits"] == 1
    assert out["prior_fix_hits"] == 1
    assert out["route_features"]["findings_hits"] == 1


def test_build_route_includes_history_memory_hits(tmp_path: Path):
    history_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "a|b": [
                    {
                        "flow": "hyper_sprint",
                        "status": "SUCCESS",
                        "reason": "stage1_pass",
                        "task_type": "bug",
                        "task_desc": "fix websocket timeout race in coordinator",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="fix websocket timeout race in orchestrator",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query="",
        target_file="demo.py",
    )
    assert out["route_features"]["memory_hits"] >= 1
    assert out["prior_fix_hits"] >= 1


def test_build_route_ignores_unrelated_same_type_history(tmp_path: Path):
    history_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "a|b": [
                    {
                        "flow": "baseline",
                        "status": "SUCCESS",
                        "reason": "stage1_pass",
                        "task_type": "bug",
                        "task_desc": "fix invoice rounding drift",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = research_flow_service.build_route(
        repo_root=tmp_path,
        task_desc="repair websocket timeout in orchestrator",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=0.9,
        findings_query="",
        target_file="demo.py",
    )
    assert out["route_features"]["memory_hits"] == 0
    assert out["prior_fix_hits"] == 0


def test_baseline_local_mutation_ignores_prior_art_keyword_pollution(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text(
        "def compute_backoff(attempt: int) -> int:\n"
        "    return 1\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_target.py"
    test_file.write_text(
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
        "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
        "_MOD = importlib.util.module_from_spec(_SPEC)\n"
        "assert _SPEC is not None and _SPEC.loader is not None\n"
        "_SPEC.loader.exec_module(_MOD)\n\n"
        "def test_compute_backoff_hard():\n"
        "    assert _MOD.compute_backoff(1) == 1\n"
        "    assert _MOD.compute_backoff(2) == 2\n"
        "    assert _MOD.compute_backoff(3) == 4\n",
        encoding="utf-8",
    )

    class _FakeLearnModeService(LearnModeService):
        def ask(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return {
                "citations": [
                    {"claim": "Fix flaky websocket timeout race under concurrent retries"},
                    {"claim": "Fix deadlock in distributed lock release path"},
                ]
            }

    monkeypatch.setattr("nexus.research.learn_mode.LearnModeService", _FakeLearnModeService)

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix eventual consistency bug in asynchronous writeback",
        target_file=str(target),
        test_file=str(test_file),
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=99.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="baseline",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
    )

    assert payload["result"]["status"] == "SUCCESS"
    assert payload["strategy"]["path"] == "baseline_only"
    assert "artifact_summary" in payload
    assert payload["artifact_summary"]["changed"] is True
    trace = payload["nexus_usage_trace"]
    assert trace["nexus_context_delivered"] is True
    assert trace["gemini_uses_nexus"] is False
    assert trace["pillars"]["lancedb"]["active"] is True
    assert trace["pillars"]["memory"]["active"] is True
    assert trace["pillars"]["mempalace"]["active"] is False
    assert trace["pillars"]["belief"]["route_influenced"] is True
    assert trace["pillars"]["artifact"]["tests_passed"] is True
    assert trace["phase_trace"]["P"] == "route_built"
    assert trace["phase_trace"]["A"] == "artifact_verified"
    assert trace["capabilities"]["claim_verified"] is True
    assert trace["codeintel"]["scan_report_present"] is True
    assert trace["codeintel"]["impact_report_present"] is True
    assert trace["codeintel"]["claim_bundle_present"] is True
    assert Path(trace["codeintel"]["scan_report_path"]).exists()
    assert Path(trace["codeintel"]["impact_report_path"]).exists()
    assert trace["codeintel"]["impacted_files_count"] >= 1
    assert trace["capability_plan"]["schema_version"] == "nexus_capability_plan_v1"
    assert trace["capability_plan"]["planner_mode"] == "dry_run"
    assert {"mempalace_gate", "artifact_gate", "claim_gate"} <= set(trace["capability_plan"]["required_capabilities"])
    assert any(item["phase"] == "A" for item in trace["capability_plan"]["replan_trace"])
    assert payload["timing"]["cli_elapsed_sec"] >= 0
    for phase in ["P", "X", "D", "R", "A", "C"]:
        assert phase in payload["timing"]["phase_wall_sec"]


def test_run_auto_flow_writes_rlm_trace_when_enabled(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text(
        "def compute_backoff(attempt: int) -> int:\n"
        "    return 1\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "test_target.py"
    test_file.write_text(
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
        "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
        "_MOD = importlib.util.module_from_spec(_SPEC)\n"
        "assert _SPEC is not None and _SPEC.loader is not None\n"
        "_SPEC.loader.exec_module(_MOD)\n\n"
        "def test_compute_backoff_hard():\n"
        "    assert _MOD.compute_backoff(1) == 1\n"
        "    assert _MOD.compute_backoff(2) == 1\n"
        "    assert _MOD.compute_backoff(3) == 1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_RLM_REPAIR_LOOP", "1")

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="RLM trace bridge smoke",
        target_file=str(target),
        test_file=str(test_file),
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=99.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="baseline",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
    )

    trace_path = Path(payload["nexus_usage_trace"]["rlm_trace_path"])
    assert trace_path.exists()
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["phase"] for event in events] == ["R", "A"]
    assert events[0]["action_type"] == "research_auto_flow"
    assert events[0]["stop_reason"] == "submit"
    assert events[1]["stop_reason"] in {"verified", "audit_rejected"}


def test_run_auto_flow_writes_recursive_research_x_trace_when_enabled(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text("def identity(value):\n    return value\n", encoding="utf-8")
    test_file = tmp_path / "test_target.py"
    test_file.write_text(
        "from target import identity\n\n"
        "def test_identity():\n"
        "    assert identity(3) == 3\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_RLM_RESEARCH_LOOP", "1")

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="RLM research loop smoke",
        target_file=str(target),
        test_file=str(test_file),
        task_type="research",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=99.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="baseline",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
    )

    trace = payload["nexus_usage_trace"]
    trace_path = Path(trace["rlm_trace_path"])
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["phase"] for event in events] == ["X", "R", "A"]
    assert events[0]["action_type"] == "research_candidate"
    assert events[0]["stop_reason"] == "candidate_selected"
    assert trace["rlm_loop_phase"] == "X"
    assert trace["rlm_x_loop_budget_observed"] is True
    assert trace["rlm_x_loop_budget_summary"]["iterations_observed"] == 1
    assert trace["rlm_x_loop_budget_summary"]["model_calls"] == 0
    assert trace["rlm_x_loop_budget_summary"]["phase_wall_sec"] >= 0
    assert trace["rlm_x_loop_budget_summary"]["exhausted"] is False


def test_cross_module_hyper_failure_can_rescue_with_original_artifact_verification(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    test_file = tmp_path / "test_target.py"
    test_file.write_text("def test_existing_contract():\n    assert True\n", encoding="utf-8")

    def fake_hyper(*, repo_root, config):
        return SimpleNamespace(
            status="FAILED",
            reason="stage1_no_passing_candidate",
            patch="",
            winner_source="local",
            error_codes=["stage1_no_passing_candidate"],
            rejection_summary={"pytest_failed": 1},
            attempt_count=5,
            model_calls=5,
            total_tokens=1234,
            token_capture_status="measured",
            learning_trace={"mempalace_verified": True},
            candidates=[
                SimpleNamespace(
                    seed=1,
                    score=0.4,
                    source="llm",
                    hint="baseline",
                    error="",
                    stdout="pytest failed: expected normalized value",
                    candidate_code="VALUE = 2\n",
                    elapsed_sec=0.2,
                )
            ],
        )

    monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_hyper)
    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Cross-module refactor: stabilize drone semantic completion over multi-step repair handoff",
        target_file=str(target),
        test_file=str(test_file),
        task_type="cross_module_refactor_drone",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query="",
        llm_mode=True,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=9.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
        success_criteria="all_target_tests_pass",
    )

    assert payload["result"]["status"] == "SUCCESS"
    assert payload["artifact_summary"]["changed"] is False
    assert payload["artifact_summary"]["verification_only"] is True
    trace = payload["nexus_usage_trace"]
    assert trace["gemini_uses_nexus"] is True
    assert trace["usage_valid"] is True
    assert trace["nexus_rescued"] is True
    assert trace["winner_source"] == "verification_only"
    assert trace["capabilities"]["self_heal_used"] is False
    assert trace["capabilities"]["claim_verified"] is True


def test_hyper_learning_trace_exposes_autoreason_and_ddtree(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    test_file = tmp_path / "test_target.py"
    test_file.write_text("def test_existing_contract():\n    assert True\n", encoding="utf-8")

    def fake_hyper(*, repo_root, config):
        return SimpleNamespace(
            status="SUCCESS",
            reason="stage1_pass",
            patch="VALUE = 2\n",
            winner_source="llm",
            error_codes=[],
            rejection_summary={},
            attempt_count=2,
            model_calls=1,
            model_name="gemini-3-flash-preview",
            model_patch_generated=True,
            fallback_used=False,
            total_tokens=1234,
            token_capture_status="measured",
            learning_trace={
                "mempalace_verified": True,
                "autoreason": {"enabled": True, "winner": "llm:2", "status": "SUCCESS"},
                "ddtree": {"enabled": True, "actual_saved_steps": 1, "selected_candidate_ids": ["llm:2"]},
            },
            candidates=[],
        )

    monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_hyper)
    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix hard candidate selection",
        target_file=str(target),
        test_file=str(test_file),
        task_type="bug",
        candidate_count=3,
        root_cause_confidence=1.0,
        findings_query="",
        llm_mode=True,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=0.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
        success_criteria="artifact_changed_and_tests_pass",
    )

    trace = payload["nexus_usage_trace"]
    assert trace["autoreason"]["winner"] == "llm:2"
    assert trace["ddtree"]["actual_saved_steps"] == 1


def test_hyper_guard_fallback_preserves_gateway_token_source(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text("def normalize_flag(text):\n    return text\n", encoding="utf-8")
    test_file = tmp_path / "test_target.py"
    test_file.write_text(
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('target', r'%s')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "def test_normalize_flag():\n"
        "    assert mod.normalize_flag(' YES ') == 'yes'\n" % target,
        encoding="utf-8",
    )

    def fake_hyper(*, repo_root, config):
        import time

        time.sleep(0.02)
        return SimpleNamespace(
            status="SUCCESS",
            reason="stage1_pass",
            patch="def normalize_flag(text):\n    return text.strip().lower()\n",
            winner_source="llm",
            error_codes=[],
            rejection_summary={},
            attempt_count=1,
            model_calls=1,
            model_name="gemini-3-flash-preview",
            model_patch_generated=True,
            fallback_used=False,
            total_tokens=333,
            token_capture_status="measured",
            gateway_stats_present=True,
            gateway_usage_metadata_present=False,
            gateway_token_source="stats",
            gateway_error_category="",
            gateway_prompt_chars=10,
            gateway_payload_chars=20,
            gateway_total_chars=30,
            gateway_timeout_sec=60,
            learning_trace={"mempalace_verified": True},
        )

    def fake_subprocess_run(*_args, **_kwargs):
        import time

        time.sleep(0.06)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_hyper)
    monkeypatch.setattr(research_flow_service.subprocess, "run", fake_subprocess_run)

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix flaky websocket normalization timeout",
        target_file=str(target),
        test_file=str(test_file),
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query="",
        llm_mode=True,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=0.01,
        baseline_fast_sec=0.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
        success_criteria="artifact_changed_and_tests_pass",
    )

    report = payload["result"]["report"]
    assert payload["strategy"]["path"] == "hyper_guard_fallback_to_baseline"
    assert report["guard_fallback_from"]["gateway_token_source"] == "stats"
    assert report["gateway_stats_present"] is True
    assert report["gateway_token_source"] == "stats"
    assert report["gateway_error_category"] == ""
    assert report["gateway_total_chars"] == 30
    assert report["gateway_timeout_sec"] == 60
    assert report["guard_fallback_from"]["gateway_total_chars"] == 30
    assert report["token_capture_status"] == "measured"
    assert report["model_calls"] == 1
    assert payload["nexus_usage_trace"]["gemini_uses_nexus"] is True


def test_auto_flow_writes_explicit_output_file(tmp_path: Path):
    target = tmp_path / "target.py"
    target.write_text("def normalize_flag(text):\n    return text\n", encoding="utf-8")
    test_file = tmp_path / "test_target.py"
    test_file.write_text(
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('target', r'%s')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "def test_normalize_flag():\n"
        "    assert mod.normalize_flag(' YES ') == 'yes'\n" % target,
        encoding="utf-8",
    )
    output_file = Path(".nexus/reports/research/test-output.json")

    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Fix normalize flag helper",
        target_file=str(target),
        test_file=str(test_file),
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query="",
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=99.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="baseline",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=output_file,
        success_criteria="artifact_changed_and_tests_pass",
    )

    written = tmp_path / output_file
    assert payload["io"]["output_written"] is True
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8"))["io"]["output_written"] is True


def test_cross_module_mutation_required_does_not_use_verification_only_rescue(tmp_path: Path, monkeypatch):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    test_file = tmp_path / "test_target.py"
    test_file.write_text("def test_existing_contract():\n    assert True\n", encoding="utf-8")

    def fake_hyper(*, repo_root, config):
        return SimpleNamespace(
            status="FAILED",
            reason="stage1_no_passing_candidate",
            patch="",
            winner_source="llm_self_heal",
            error_codes=["stage1_no_passing_candidate", "llm_self_heal_attempted"],
            rejection_summary={"pytest_failed": 1},
            attempt_count=5,
            model_calls=5,
            total_tokens=1234,
            token_capture_status="measured",
            learning_trace={"mempalace_verified": True},
            candidates=[
                SimpleNamespace(
                    seed=1,
                    score=0.4,
                    source="llm",
                    hint="baseline",
                    error="",
                    stdout="pytest failed: expected normalized value",
                    candidate_code="VALUE = 2\n",
                    elapsed_sec=0.2,
                )
            ],
        )

    monkeypatch.setattr(research_flow_service, "run_hyper_sprint", fake_hyper)
    payload, _ = research_flow_service.run_auto_flow(
        repo_root=tmp_path,
        task_desc="Cross-module refactor: mutate drone engine contract",
        target_file=str(target),
        test_file=str(test_file),
        task_type="cross_module_refactor_drone",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query="",
        llm_mode=True,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.5,
        baseline_fast_sec=9.0,
        history_window=1,
        history_fail_threshold=9999,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/test-auto-flow.json",
        output_file=None,
        success_criteria="artifact_changed_and_tests_pass",
    )

    assert payload["result"]["status"] == "FAILED"
    assert payload["artifact_summary"]["verification_only"] is False
    assert payload["success_criteria"]["mutation_required"] is True
    trace = payload["nexus_usage_trace"]
    assert trace["usage_valid"] is False
    assert trace["capabilities"]["self_heal_used"] is True
    assert trace["capabilities"]["claim_verified"] is False
    summaries = payload["result"]["report"]["candidate_summaries"]
    assert summaries[0]["source"] == "llm"
    assert "pytest failed" in summaries[0]["stdout_tail"]
    assert summaries[0]["candidate_len"] > 0
