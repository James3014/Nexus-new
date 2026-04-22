import pytest
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
    assert out["explain_payload"]["risk"] == "CRITICAL"


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
