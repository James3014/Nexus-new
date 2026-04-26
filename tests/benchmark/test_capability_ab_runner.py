from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _benchmark_memory_db_path,
    _budget_exceeded,
    _classify_timeout_stage,
    _emit_progress,
    _extract_record,
    _extract_json_payload,
    expand_task_trials,
    _force_learn_slo_ready,
    _history_policy_name,
    _materialize_fixture,
    _read_preserved_target,
    _remaining_leg_timeout,
    _restore_preserved_target,
    _resolve_task_files,
    _tail_text,
    _task_uses_materialized_fixture,
    _with_nexus_timeout_payload,
    _write_trial_evidence,
    assert_clean_worktree,
    filter_tasks_by_id,
    filter_tasks_by_repo_kind,
    load_tasks,
    run_with_nexus,
    run_without_nexus,
    select_tasks,
    write_evidence_bundle,
    write_jsonl,
)


def test_load_tasks_parses_capability_schema(tmp_path: Path):
    payload = {
        "tasks": [
            {
                "id": "hard-001",
                "difficulty": "hard",
                "task_type": "bug",
                "task_desc": "Fix race",
                "target_file": "a.py",
                "test_file": "tests/test_a.py",
                "success_criteria": "all_target_tests_pass",
            }
        ]
    }
    src = tmp_path / "tasks.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    tasks = load_tasks(src)
    assert len(tasks) == 1
    assert tasks[0].id == "hard-001"
    assert tasks[0].difficulty == "hard"
    assert len(tasks[0].manifest_hash) == 64


def test_load_tasks_parses_public_manifest_metadata(tmp_path: Path):
    payload = {
        "tasks": [
            {
                "id": "pub-001",
                "category": "bugfix",
                "difficulty": "hard",
                "repo_kind": "neutral_fixture",
                "repo": "fixture://demo",
                "repo_ref": "v1",
                "task_desc": "Fix public task",
                "fixture_kind": "python_demo",
                "success_criteria": "patch_and_tests_pass",
            }
        ]
    }
    src = tmp_path / "public.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    tasks = load_tasks(src)
    assert tasks[0].task_type == "public_bugfix"
    assert tasks[0].target_file == "python_demo"
    assert tasks[0].category == "bugfix"
    assert tasks[0].repo_kind == "neutral_fixture"
    assert tasks[0].repo == "fixture://demo"
    assert tasks[0].repo_ref == "v1"


def test_expand_task_trials_repeats_and_shuffles_deterministically():
    tasks = [
        CapabilityTask(id="a", difficulty="hard", task_type="bug", task_desc="a", target_file="a", test_file="a", success_criteria="x"),
        CapabilityTask(id="b", difficulty="hard", task_type="bug", task_desc="b", target_file="b", test_file="b", success_criteria="x"),
    ]
    expanded = expand_task_trials(tasks, repeat_trials=2, shuffle_seed=7)
    assert sorted((task.id, task.trial_index) for task in expanded) == [("a", 1), ("a", 2), ("b", 1), ("b", 2)]
    assert [task.id for task in expanded] == [task.id for task in expand_task_trials(tasks, repeat_trials=2, shuffle_seed=7)]


def test_materialize_fixture_writes_files(tmp_path: Path):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="na",
        test_file="na",
        success_criteria="all_target_tests_pass",
    )
    target, test = _materialize_fixture(tmp_path, task)
    assert Path(target).exists()
    assert Path(test).exists()
    assert "normalize_flag" in Path(target).read_text(encoding="utf-8")


def test_resolve_task_files_can_fail_closed_without_materializing(tmp_path: Path):
    task = CapabilityTask(
        id="real-001",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Use real files",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="all_target_tests_pass",
    )
    try:
        _resolve_task_files(tmp_path, task, materialize_missing=False)
    except FileNotFoundError as exc:
        assert "real-001" in str(exc)
    else:
        raise AssertionError("missing real task files should fail closed")


def test_resolve_task_files_preserves_existing_real_paths(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_src.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    task = CapabilityTask(
        id="real-002",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Use real files",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="all_target_tests_pass",
    )
    target, test = _resolve_task_files(tmp_path, task, materialize_missing=False)
    assert target.endswith("src.py")
    assert test.endswith("tests/test_src.py")


def test_resolve_task_files_uses_real_paths_for_nexus_internal_even_when_materializing(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_src.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    task = CapabilityTask(
        id="pub-internal",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Use real internal files",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="patch_and_tests_pass",
        repo_kind="nexus_internal",
    )
    target, test = _resolve_task_files(tmp_path, task, materialize_missing=True)
    assert target.endswith("src.py")
    assert test.endswith("tests/test_src.py")
    assert _task_uses_materialized_fixture(task, materialize_missing=True) is False


def test_resolve_task_files_fails_closed_for_external_without_adapter(tmp_path: Path):
    task = CapabilityTask(
        id="pub-external",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="External task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="external",
    )
    try:
        _resolve_task_files(tmp_path, task, materialize_missing=True)
    except NotImplementedError as exc:
        assert "clone/setup adapter" in str(exc)
    else:
        raise AssertionError("external tasks must not materialize local fixtures")
    assert _task_uses_materialized_fixture(task, materialize_missing=True) is False


def test_preserve_target_helpers_restore_real_task_file(tmp_path: Path):
    target = tmp_path / "src.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    original = _read_preserved_target(str(target), materialize_missing=False)
    target.write_text("VALUE = 2\n", encoding="utf-8")
    _restore_preserved_target(str(target), original)
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert _read_preserved_target(str(target), materialize_missing=True) == "VALUE = 1\n"


def test_write_trial_evidence_and_bundle(tmp_path: Path):
    row = {"mode": "with_nexus", "task_id": "task/1", "trial_index": 2, "status": "SUCCESS"}
    evidence = _write_trial_evidence(
        evidence_root=tmp_path / "evidence",
        row=row,
        target_before="VALUE = 1\n",
        target_after="VALUE = 2\n",
    )
    row.update(evidence)
    assert Path(evidence["evidence_record_file"]).exists()
    diff_text = Path(evidence["evidence_diff_file"]).read_text(encoding="utf-8")
    assert "-VALUE = 1" in diff_text
    assert "+VALUE = 2" in diff_text

    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    write_jsonl(with_path, [row])
    write_jsonl(without_path, [])
    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[row],
        config={"repeat_trials": 1},
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus_public_benchmark_evidence_bundle_v1"
    assert payload["raw_files"]["with_nexus"]["sha256"]
    assert len(payload["artifact_files"]) == 2


def test_total_timeout_budget_helper():
    assert _budget_exceeded(0.0, 1) is True
    assert _budget_exceeded(0.0, 0) is False
    assert _remaining_leg_timeout(30, 0.0, 0) == 30
    assert _remaining_leg_timeout(30, 0.0, 1) == 1


def test_emit_progress_writes_json_to_stderr(capsys):
    task = CapabilityTask(
        id="real-003",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Progress",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="all_target_tests_pass",
    )
    _emit_progress(enabled=True, event="task_start", mode="with_nexus", task=task, elapsed_sec=1.25)
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["event"] == "task_start"
    assert payload["mode"] == "with_nexus"
    assert payload["task_id"] == "real-003"


def test_extract_record_maps_semantic_fields():
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix race",
        target_file="a.py",
        test_file="tests/test_a.py",
        success_criteria="all_target_tests_pass",
    )
    payload = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "runtime_classification": "runtime_defect",
        "route": {
            "recommended_flow": "hyper_sprint",
            "recommended_reason": "complex_bug_prefer_hyper",
            "findings_hits": 2,
            "prior_fix_hits": 2,
            "consensus": {"winner": "hyper_sprint", "votes": {"hyper_sprint": 3, "baseline": 1}},
            "route_features": {"risk_score": 87, "memory_hits": 1},
        },
        "guard": {"hit": False, "nightshift_recommended": True, "stage1_fail_signals": 1},
        "strategy": {"path": "probe_then_hyper"},
        "execution_profile": {"belief_confidence": 0.72},
        "learn_phase_slo": {"phase_slo_pass": True},
        "artifact_summary": {
            "changed": True,
            "verification_only": False,
            "diff_line_count": 12,
            "success_criteria": "artifact_changed_and_tests_pass",
            "mutation_required": True,
            "verification_only_allowed": False,
        },
        "success_criteria": {
            "name": "artifact_changed_and_tests_pass",
            "mutation_required": True,
            "verification_only_allowed": False,
        },
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "gemini_patch_status": "failed",
            "nexus_rescued": True,
            "winner_source": "nexus_rescue",
            "pillars": {
                "lancedb": {"active": True, "hits": 2},
                "memory": {"active": True, "hits": 1},
                "mempalace": {"active": True, "verified": True},
                "belief": {"active": True},
                "artifact": {"active": True, "tests_passed": True},
            },
            "phase_trace": {"P": "route_built", "X": "retrieval_checked", "D": "guard_decision", "R": "hyper_executed", "A": "artifact_verified", "C": "closure_written"},
            "phase_wall_sec": {"P": 0.1, "X": 0.2, "D": 0.3, "R": 1.1, "A": 0.4, "C": 0.5},
            "capabilities": {"research_used": True, "hyper_used": True, "self_heal_used": True, "claim_verified": True, "nightshift_recommended": False, "swarm_used": False, "drone_used": False},
        },
        "timing": {"cli_elapsed_sec": 2.4, "phase_wall_sec": {"P": 0.1, "X": 0.2, "D": 0.3, "R": 1.1, "A": 0.4, "C": 0.5}},
        "result": {
            "elapsed_sec": 2.3,
            "report": {
                "attempt_count": 4,
                "model_calls": 1,
                "total_tokens": 321,
                "token_capture_status": "measured",
            },
        },
    }
    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=2.5)
    assert out["task_id"] == "hard-001"
    assert out["trial_index"] == 1
    assert out["semantic_status"] == "UNVERIFIED"
    assert out["attempt_count"] == 4
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 321
    assert out["token_capture_status"] == "measured"
    assert out["report_trust_mismatch"] is False
    assert out["route_risk_score"] == 87
    assert out["route_consensus_winner"] == "hyper_sprint"
    assert out["route_consensus_hyper_votes"] == 3
    assert out["route_memory_hits"] == 1
    assert out["guard_nightshift_recommended"] is True
    assert out["strategy_path"] == "probe_then_hyper"
    assert out["learn_phase_slo_pass"] is True
    assert out["artifact_changed"] is True
    assert out["artifact_verification_only"] is False
    assert out["artifact_diff_line_count"] == 12
    assert out["success_criteria"] == "artifact_changed_and_tests_pass"
    assert out["mutation_required"] is True
    assert out["verification_only_allowed"] is False
    assert out["gemini_uses_nexus"] is True
    assert out["nexus_usage_valid"] is True
    assert out["nexus_rescued"] is True
    assert out["pillar_mempalace_verified"] is True
    assert out["phase_r"] == "hyper_executed"
    assert out["cli_elapsed_sec"] == 2.4
    assert out["phase_wall_r_sec"] == 1.1
    assert out["capability_hyper_used"] is True
    assert out["capability_claim_verified"] is True
    assert out["semantic_completed"] is False


def test_extract_record_treats_patch_and_tests_pass_as_mutation_required():
    task = CapabilityTask(
        id="pub-001",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public task",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    out = _extract_record(
        mode="with_nexus",
        task=task,
        payload={"status": "SUCCESS", "semantic_status": "VERIFIED", "artifact_summary": {"changed": True}},
        wall_time_sec=1.0,
    )
    assert out["success_criteria"] == "patch_and_tests_pass"
    assert out["mutation_required"] is True
    assert out["verification_only_allowed"] is False


def test_timeout_payload_preserves_stage_and_partial_output():
    payload = _with_nexus_timeout_payload(timeout_sec=7)
    task = CapabilityTask(
        id="pub-timeout",
        difficulty="medium",
        task_type="public_refactor",
        task_desc="Replay timeout",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=7.2)
    assert out["runtime_classification"] == "subprocess_timeout"
    assert out["timeout_scope"] == "with_nexus_subprocess"
    assert out["timeout_stage"] == "timeout_before_receipt"
    assert out["timeout_sec"] == 7
    assert out["model_calls"] == 0
    assert out["gemini_uses_nexus"] is False


def test_tail_text_decodes_bytes_and_limits_output():
    assert _tail_text(b"abc") == "abc"
    assert _tail_text("abcdef", max_chars=3) == "def"


def test_classify_timeout_stage_from_partial_output():
    assert _classify_timeout_stage("running pytest", "") == "timeout_during_artifact_verify"
    assert _classify_timeout_stage("Gemini model call started", "") == "timeout_during_gemini"
    assert _classify_timeout_stage("", "MemoryService auto-init skipped\n[Gateway] Dynamic timeout") == "timeout_during_gemini"
    assert _classify_timeout_stage("hyper sprint candidate", "") == "timeout_during_hyper"
    assert _classify_timeout_stage("", "MemoryService auto-init warning: Table 'policy' already exists") == "timeout_during_memory_bootstrap"
    assert _classify_timeout_stage("", "") == "timeout_before_receipt"


def test_benchmark_memory_db_path_is_per_task_trial(tmp_path: Path):
    task = CapabilityTask(
        id="pub/test:002",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public task",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        trial_index=3,
    )
    path = _benchmark_memory_db_path(tmp_path, task, 123.456)
    assert path == tmp_path / ".nexus" / "reports" / "bench_runtime" / "memory" / "pub_test_002_trial3_123456"


def test_extract_json_payload_from_prefixed_output():
    raw = """Redis init failed
Memory warning
{
  "status": "SUCCESS",
  "semantic_status": "VERIFIED"
}"""
    payload = _extract_json_payload(raw)
    assert payload["status"] == "SUCCESS"
    assert payload["semantic_status"] == "VERIFIED"


def test_select_tasks_balances_buckets_for_all_mode():
    tasks = [
        CapabilityTask(id="easy-1", difficulty="easy", task_type="bug", task_desc="e1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="easy-2", difficulty="easy", task_type="bug", task_desc="e2", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="medium-1", difficulty="medium", task_type="bug", task_desc="m1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="medium-2", difficulty="medium", task_type="bug", task_desc="m2", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="hard-1", difficulty="hard", task_type="bug", task_desc="h1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="hard-2", difficulty="hard", task_type="bug", task_desc="h2", target_file="a", test_file="b", success_criteria="x"),
    ]
    selected = select_tasks(tasks, difficulty="all", max_tasks=6)
    assert [task.id for task in selected] == ["easy-1", "medium-1", "hard-1", "easy-2", "medium-2", "hard-2"]


def test_filter_tasks_by_repo_kind_allows_non_external_subset():
    tasks = [
        CapabilityTask(id="a", difficulty="medium", task_type="bug", task_desc="a", target_file="a", test_file="a", success_criteria="x", repo_kind="neutral_fixture"),
        CapabilityTask(id="b", difficulty="hard", task_type="bug", task_desc="b", target_file="b", test_file="b", success_criteria="x", repo_kind="external"),
        CapabilityTask(id="c", difficulty="hard", task_type="bug", task_desc="c", target_file="c", test_file="c", success_criteria="x", repo_kind="nexus_internal"),
    ]
    assert [task.id for task in filter_tasks_by_repo_kind(tasks, "neutral_fixture,nexus_internal")] == ["a", "c"]


def test_filter_tasks_by_id_allows_targeted_replay():
    tasks = [
        CapabilityTask(id="a", difficulty="medium", task_type="bug", task_desc="a", target_file="a", test_file="a", success_criteria="x"),
        CapabilityTask(id="b", difficulty="hard", task_type="bug", task_desc="b", target_file="b", test_file="b", success_criteria="x"),
    ]
    assert [task.id for task in filter_tasks_by_id(tasks, "b")] == ["b"]
    assert [task.id for task in filter_tasks_by_id(tasks, "all")] == ["a", "b"]


def test_run_without_nexus_bare_mode_returns_record(tmp_path: Path):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="bare",
    )
    assert out["mode"] == "without_nexus"
    assert out["semantic_status"] is None
    assert out["attempt_count"] == 1
    assert out["model_calls"] == 0
    assert out["total_tokens"] == 0
    assert out["token_capture_status"] == "not_applicable_local_only"


def test_run_without_nexus_bare_mode_hard_task_runs_verify_only(tmp_path: Path):
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix flaky timeout race",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="bare",
    )
    assert out["status"] == "FAILED"


def test_run_with_nexus_enables_llm_mode_for_hard_tasks(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix flaky timeout race",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    captured = {"args": []}

    class _InvokeRes:
        def __init__(self):
            self.output = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'

    def fake_invoke(_self, _cli, args, **_kwargs):
        captured["args"] = list(args)
        return _InvokeRes()

    monkeypatch.setattr("click.testing.CliRunner.invoke", fake_invoke)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="inprocess",
        with_llm_mode="hard",
    )
    assert "--llm-mode" in captured["args"]
    assert out["semantic_status"] == "VERIFIED"


def test_run_with_nexus_subprocess_disables_memory_auto_init(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-001",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner.subprocess.run", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured["env"]["NEXUS_MEMORY_AUTO_INIT"] == "0"
    assert captured["env"]["NEXUS_FORCE_LLM_DESPITE_LEARN_SLO"] == "1"
    assert captured["env"]["NEXUS_GATEWAY_MAX_RETRIES"] == "1"
    assert captured["env"]["NEXUS_GATEWAY_TIMEOUT_SEC"] == "30"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "1"
    assert captured["env"]["NEXUS_DISABLE_DAYSHIFT_OPTIMIZER"] == "1"
    assert "NEXUS_MEMORY_DB_PATH" in captured["env"]
    assert out["semantic_status"] == "VERIFIED"


def test_run_with_nexus_llm_all_forces_hyper_flow(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-001",
        difficulty="medium",
        task_type="public_docs_code_sync",
        task_desc="Fix docs task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner.subprocess.run", fake_run)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert "--force-flow" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "hyper_sprint"


def test_history_policy_defaults_to_per_task_reset():
    assert _history_policy_name(neutralize_history=True, allow_learning_loop=False) == "per_task_reset"
    assert _history_policy_name(neutralize_history=True, allow_learning_loop=True) == "within_mode_learning"
    assert _history_policy_name(neutralize_history=False, allow_learning_loop=True) == "shared_existing_history"


def test_assert_clean_worktree_fails_closed_on_dirty_status(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("scripts.bench.capability_ab_runner._git_status_porcelain", lambda _root: " M file.py")
    try:
        assert_clean_worktree(tmp_path)
    except RuntimeError as exc:
        assert "clean worktree" in str(exc)
        assert "file.py" in str(exc)
    else:
        raise AssertionError("dirty worktree should fail closed")


def test_run_without_nexus_gemini_mode_uses_direct_flash_baseline(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "[CURRENT TESTS]" in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 123,
                "token_capture_status": "measured",
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )
    assert out["status"] == "SUCCESS"
    assert out["semantic_status"] == "VERIFIED"
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 123
    assert out["token_capture_status"] == "measured"
    assert out["artifact_changed"] is True
    assert out["baseline_patch_changed"] is True
    assert out["baseline_patch_len"] > 0


def test_force_learn_slo_ready_writes_pass_summary(tmp_path: Path):
    _force_learn_slo_ready(tmp_path)
    payload = json.loads((tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").read_text(encoding="utf-8"))
    assert payload["phase_slo_pass"] is True
    assert payload["global"]["required_done_ratio"] == 1.0
