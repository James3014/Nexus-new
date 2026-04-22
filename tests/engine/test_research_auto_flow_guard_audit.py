import json
import time
from pathlib import Path

from nexus.app import research_flow_service as rfs
from nexus.research.sprint_service import SprintResult


def _write_task_files(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("print('buggy')\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_demo.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")


def _patch_common_success(monkeypatch) -> None:
    class _Res:
        def __init__(self, returncode: int = 0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*_args, **_kwargs):
        return _Res(returncode=0)

    monkeypatch.setattr("nexus.app.research_flow_service.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr(
        "nexus.app.research_flow_service.generate_local_candidate",
        lambda source, *_args, **_kwargs: source.replace("buggy", "fixed"),
    )


def test_hard_task_not_demoted_by_learn_guard_when_phase_slo_missing(tmp_path, monkeypatch):
    _write_task_files(tmp_path)
    _patch_common_success(monkeypatch)

    def fake_run_hyper_sprint(*_args, **_kwargs):
        return SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        )

    monkeypatch.setattr("nexus.app.research_flow_service.run_hyper_sprint", fake_run_hyper_sprint)

    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.2,
        baseline_fast_sec=0,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )

    assert payload["chosen_flow"] == "hyper_sprint"
    assert payload["result"]["status"] == "SUCCESS"
    assert payload["guard"]["learn_forced_baseline"] is False


def test_hard_task_not_demoted_by_time_ratio_guard_with_tiny_probe(tmp_path, monkeypatch):
    _write_task_files(tmp_path)
    _patch_common_success(monkeypatch)

    def fake_run_hyper_sprint(*_args, **_kwargs):
        # Keep this above baseline probe runtime to emulate slower hyper execution.
        time.sleep(0.06)
        return SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        )

    monkeypatch.setattr("nexus.app.research_flow_service.run_hyper_sprint", fake_run_hyper_sprint)

    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.01,
        baseline_fast_sec=0,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow=None,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )

    assert payload["chosen_flow"] == "hyper_sprint"
    assert payload["guard"]["hit"] is False


def test_history_forces_baseline_when_recent_hyper_failures_reach_threshold(tmp_path, monkeypatch):
    _write_task_files(tmp_path)
    _patch_common_success(monkeypatch)

    history_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    flow_key = "demo.py|tests/test_demo.py"
    history_path.write_text(
        json.dumps(
            {
                flow_key: [
                    {"flow": "hyper_sprint", "status": "FAILED", "reason": "timeout"},
                    {"flow": "hyper_sprint", "status": "FAILED", "reason": "stage1_no_passing_candidate"},
                ]
            }
        ),
        encoding="utf-8",
    )

    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.2,
        baseline_fast_sec=0,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow=None,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )

    assert payload["chosen_flow"] == "baseline"
    assert payload["guard"]["history_forced_baseline"] is True
    assert payload["guard"]["nightshift_recommended"] is True
    assert payload["guard"]["stage1_fail_signals"] >= 1


def test_force_flow_hyper_sprint_bypasses_history_forced_baseline(tmp_path, monkeypatch):
    _write_task_files(tmp_path)
    _patch_common_success(monkeypatch)

    history_path = tmp_path / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    flow_key = "demo.py|tests/test_demo.py"
    history_path.write_text(
        json.dumps(
            {
                flow_key: [
                    {"flow": "hyper_sprint", "status": "FAILED", "reason": "timeout"},
                    {"flow": "hyper_sprint", "status": "FAILED", "reason": "stage1_no_passing_candidate"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_run_hyper_sprint(*_args, **_kwargs):
        return SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        )

    monkeypatch.setattr("nexus.app.research_flow_service.run_hyper_sprint", fake_run_hyper_sprint)

    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.2,
        baseline_fast_sec=0,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow="hyper_sprint",
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )

    assert payload["chosen_flow"] == "hyper_sprint"
    assert payload["guard"]["history_forced_baseline"] is False
    assert payload["guard"]["nightshift_recommended"] is True


def test_skip_baseline_probe_for_hard_task_when_tuning_enabled(tmp_path, monkeypatch):
    _write_task_files(tmp_path)
    _patch_common_success(monkeypatch)

    tuning_path = tmp_path / ".nexus" / "config" / "capability_tuning.json"
    tuning_path.parent.mkdir(parents=True, exist_ok=True)
    tuning_path.write_text(
        json.dumps({"knobs": {"skip_baseline_probe_for_hard": True, "baseline_fast_sec": 99.0}}),
        encoding="utf-8",
    )

    calls = {"generate_local": 0, "hyper": 0}

    def fake_generate_local(source, *_args, **_kwargs):
        calls["generate_local"] += 1
        return source.replace("buggy", "fixed")

    def fake_run_hyper_sprint(*_args, **_kwargs):
        calls["hyper"] += 1
        return SprintResult(
            status="SUCCESS",
            reason="stage1_pass",
            target_file="demo.py",
            winner_source="local",
            final_score=1.0,
            elapsed_sec=0.1,
            attempt_count=1,
            model_calls=0,
            quota_backoffs=0,
            test_timeouts=0,
            error_codes=[],
            candidates=[],
            pytest_cmd=["uv", "run", "pytest", "-q", "--maxfail=1", "tests/test_demo.py"],
            promotable=True,
            patch="print('fixed')\n",
        )

    monkeypatch.setattr("nexus.app.research_flow_service.generate_local_candidate", fake_generate_local)
    monkeypatch.setattr("nexus.app.research_flow_service.run_hyper_sprint", fake_run_hyper_sprint)

    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.2,
        baseline_fast_sec=99,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow=None,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )

    assert payload["guard"]["baseline_probe_skipped"] is True
    assert payload["chosen_flow"] == "hyper_sprint"
    assert calls["hyper"] == 1
    assert calls["generate_local"] == 0


def test_early_baseline_shortcut_reuses_probe_result_without_second_generation(tmp_path, monkeypatch):
    _write_task_files(tmp_path)
    calls = {"generate_local": 0}

    class _Res:
        def __init__(self, returncode: int = 0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_subprocess_run(*_args, **_kwargs):
        return _Res(returncode=0)

    def fake_generate_local(source, *_args, **_kwargs):
        calls["generate_local"] += 1
        return source.replace("buggy", "fixed")

    monkeypatch.setattr("nexus.app.research_flow_service.subprocess.run", fake_subprocess_run)
    monkeypatch.setattr("nexus.app.research_flow_service.generate_local_candidate", fake_generate_local)

    payload, _ = rfs.run_auto_flow(
        repo_root=tmp_path,
        task_desc="fix flaky websocket timeout race",
        target_file="demo.py",
        test_file="tests/test_demo.py",
        task_type="bug",
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=30,
        stage1_timeout_sec=20,
        max_time_ratio_guard=1.2,
        baseline_fast_sec=99.0,
        history_window=3,
        history_fail_threshold=2,
        dynamic_timeout_multiplier=1.0,
        min_dynamic_stage1_timeout=20,
        force_flow=None,
        report_file=".nexus/reports/research/auto-flow-report.json",
        output_file=None,
    )

    assert payload["chosen_flow"] == "baseline"
    assert payload["guard"]["early_baseline_shortcut"] is True
    assert payload["result"]["report"]["reused_from_probe"] is True
    assert calls["generate_local"] == 1
