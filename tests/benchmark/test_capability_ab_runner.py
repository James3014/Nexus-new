from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _annotate_benchmark_eligibility,
    _apply_per_task_stop_loss,
    _benchmark_memory_db_path,
    _budget_exceeded,
    _classify_timeout_stage,
    _emit_progress,
    _effective_total_timeout_sec,
    _extract_record,
    _extract_json_payload,
    _summarize_benchmark_rows,
    expand_task_trials,
    _force_learn_slo_ready,
    _history_policy_name,
    _hidden_verifier_mode_enabled,
    _ask_direct_gemini_flash_patch,
    _benchmark_gateway_timeout_for_task,
    _benchmark_gateway_timeout_sec,
    _materialize_fixture,
    _nexus_task_desc,
    _parse_direct_gemini_json,
    _read_preserved_target,
    _remaining_leg_timeout,
    _report_model_label,
    _render_partial_markdown_report,
    _restore_preserved_target,
    _resolve_task_files,
    _run_process_group,
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


def test_report_model_label_uses_configured_gemini_model(monkeypatch):
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    assert _report_model_label() == "gemini-3-flash-preview"


def test_benchmark_gateway_timeout_has_short_default_and_override(monkeypatch):
    monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", raising=False)
    assert _benchmark_gateway_timeout_sec() == "30"
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "12")
    assert _benchmark_gateway_timeout_sec() == "12"
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "bad")
    assert _benchmark_gateway_timeout_sec() == "30"


def test_benchmark_gateway_timeout_scales_with_task_budget():
    assert _benchmark_gateway_timeout_for_task(10) == 30
    assert _benchmark_gateway_timeout_for_task(120) == 90
    assert _benchmark_gateway_timeout_for_task(180) == 150
    assert _benchmark_gateway_timeout_for_task(300) == 220


def test_parse_direct_gemini_json_marks_stats_tokens_measured():
    raw = json.dumps(
        {
            "output": json.dumps({"status": "OK", "patch": "x = 1\n"}),
            "stats": {"models": {"gemini-3-flash-preview": {"tokens": {"total": 321}}}},
        }
    )
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 321
    assert payload["token_capture_status"] == "measured"
    assert payload["gateway_stats_present"] is True
    assert payload["gateway_usage_metadata_present"] is False
    assert payload["gateway_token_source"] == "stats"


def test_parse_direct_gemini_json_reads_usage_metadata_tokens():
    raw = json.dumps(
        {
            "response": json.dumps({"status": "OK", "patch": "x = 1\n"}),
            "usageMetadata": {"totalTokenCount": 456},
        }
    )
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 456
    assert payload["token_capture_status"] == "measured"
    assert payload["gateway_stats_present"] is False
    assert payload["gateway_usage_metadata_present"] is True
    assert payload["gateway_token_source"] == "usage_metadata"


def test_parse_direct_gemini_json_marks_missing_gateway_stats():
    raw = json.dumps({"output": json.dumps({"status": "OK", "patch": "x = 1\n"})})
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 0
    assert payload["token_capture_status"] == "missing_gateway_stats"
    assert payload["gateway_stats_present"] is False
    assert payload["gateway_usage_metadata_present"] is False
    assert payload["gateway_token_source"] == "missing"


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


def test_materialize_nexus_value_fixture_uses_fixture_kind(tmp_path: Path):
    task = CapabilityTask(
        id="nexus-value-trust-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix trust mismatch",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_trust_phase_aggregator",
    )

    target, test = _materialize_fixture(tmp_path, task)

    target_source = Path(target).read_text(encoding="utf-8")
    test_source = Path(test).read_text(encoding="utf-8")
    assert "overall_status" in target_source
    assert "compute_backoff" not in target_source
    assert "spec_from_file_location" in test_source
    assert "missing_evidence" in test_source


def test_materialize_all_nexus_value_manifest_fixtures_are_distinct(tmp_path: Path):
    tasks = [
        task
        for task in load_tasks("scripts/bench/public_benchmark_nexus_value_v1.json")
        if task.fixture_kind.startswith("nexus_value_")
    ]

    signatures = set()
    for task in tasks:
        target, test = _materialize_fixture(tmp_path, task)
        signatures.add((Path(target).read_text(encoding="utf-8"), Path(test).read_text(encoding="utf-8")))

    assert len(signatures) == len(tasks)


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
    assert _effective_total_timeout_sec(7200, 600) == 600
    assert _effective_total_timeout_sec(0, 600) == 600
    assert _effective_total_timeout_sec(300, 600) == 300
    assert _effective_total_timeout_sec(7200, 0) == 7200


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
    assert out["nexus_pillars_observed"] == ["lancedb", "memory", "mempalace", "belief", "artifact"]
    assert out["nexus_phases_observed"] == ["P", "X", "D", "R", "A", "C"]


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


def test_expand_task_trials_preserves_fixture_kind():
    task = CapabilityTask(
        id="nexus-value-hidden-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix hidden state",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
    )

    expanded = expand_task_trials([task], repeat_trials=2, shuffle_seed=None)

    assert [item.trial_index for item in expanded] == [1, 2]
    assert {item.fixture_kind for item in expanded} == {"nexus_value_hidden_state"}


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


def test_run_with_nexus_augments_rlm_evidence_task_desc(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-harder-v2-evidence-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix claim verification so only fully supported successful claims are accepted.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {"args": []}

    class _InvokeRes:
        output = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"measured"}}}'

    def fake_invoke(_self, _cli, args, **_kwargs):
        captured["args"] = list(args)
        return _InvokeRes()

    monkeypatch.setattr("click.testing.CliRunner.invoke", fake_invoke)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="inprocess",
        with_llm_mode="all",
    )

    task_desc = captured["args"][captured["args"].index("--task-desc") + 1]
    assert "Nexus wearing contract" in task_desc
    assert "MemPalace: keep the solution inside the task scope" in task_desc
    assert "Belief: when evidence is incomplete" in task_desc
    assert "Nexus Artifact/Claim rule" in task_desc
    assert "artifact" in task_desc


def test_nexus_task_desc_adds_pillar_specific_rules():
    governance = CapabilityTask(
        id="gov",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix scope enforcement.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_governance_guard",
    )
    memory = CapabilityTask(
        id="memory",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix memory relevance.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_memory_contract",
    )
    belief = CapabilityTask(
        id="belief",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix belief budget.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_belief_budget",
    )

    assert "Nexus MemPalace rule" in _nexus_task_desc(governance)
    assert "Nexus Belief/Memory rule" in _nexus_task_desc(memory)
    assert "Nexus Belief/Memory rule" in _nexus_task_desc(belief)


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
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

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
    assert captured["env"]["NEXUS_GEMINI_MODEL_NAME"] == "gemini-3.1-pro-preview"
    assert captured["env"]["NEXUS_FORCE_LLM_DESPITE_LEARN_SLO"] == "1"
    assert captured["env"]["NEXUS_GATEWAY_MAX_RETRIES"] == "1"
    assert captured["env"]["NEXUS_GATEWAY_TIMEOUT_SEC"] == "30"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "1"
    assert captured["env"]["NEXUS_DISABLE_DAYSHIFT_OPTIMIZER"] == "1"
    assert captured["env"]["NEXUS_FORCE_INPLACE_EXECUTOR"] == "1"
    assert "NEXUS_MEMORY_DB_PATH" in captured["env"]
    assert out["semantic_status"] == "VERIFIED"
    assert out["model_name"] == "gemini-3.1-pro-preview"
    assert out["token_capture_status"] == "measured"
    assert out["model_patch_generated"] is True
    assert out["fallback_used"] is False


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

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

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


def test_hidden_verifier_mode_reads_environment(monkeypatch):
    monkeypatch.delenv("NEXUS_VALUE_HIDDEN_VERIFIER", raising=False)
    assert _hidden_verifier_mode_enabled() is False
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    assert _hidden_verifier_mode_enabled() is True


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
                "model_name": "gemini-3.1-pro-preview",
                "model_patch_generated": True,
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
    assert out["model_name"] == "gemini-3.1-pro-preview"
    assert out["provider"] == "gemini"
    assert out["run_eligible"] is True
    assert out["infra_invalid_reason"] is None
    assert out["invocation_started"] is True
    assert out["model_response_received"] is True
    assert out["nexus_bootstrap_completed"] is False
    assert out["model_patch_generated"] is True
    assert out["artifact_changed"] is True
    assert out["baseline_patch_changed"] is True
    assert out["baseline_patch_len"] > 0


def test_run_without_nexus_hidden_verifier_omits_tests_from_prompt(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-value-hidden-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix hidden verifier task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "test_duplicate_events_are_idempotent" not in prompt
        original = Path(target_file).read_text(encoding="utf-8")
        return (
            {
                "patch": original,
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
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

    assert out["baseline_patch_changed"] is False


def test_run_without_nexus_hidden_verifier_omits_rlm_harder_tests(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-v2-hidden-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden RLM task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "test_requires_artifact_reference" not in prompt
        original = Path(target_file).read_text(encoding="utf-8")
        return (
            {
                "patch": original,
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
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

    assert out["baseline_patch_changed"] is False


def test_run_without_nexus_gemini_quota_is_infra_invalid(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-quota",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        return (
            {
                "status": "FAIL",
                "error_category": "cli_error",
                "tokens_used": 0,
                "model_name": "gemini-3-flash-preview",
            },
            "Resource exhausted: quota exceeded",
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

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "quota_exhausted"
    assert out["model_calls"] == 1
    assert out["invocation_started"] is True
    assert out["model_response_received"] is False


def test_run_without_nexus_gemini_timeout_before_response_is_recorded(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="timeout-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix timeout",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        raise subprocess.TimeoutExpired(["gemini"], timeout_sec)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)

    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=1,
        force_flow=None,
        mode="gemini",
    )

    assert out["status"] == "FAILED"
    assert out["baseline_gateway_error_category"] == "timeout"
    assert out["infra_invalid_reason"] == "timeout_before_model_call"


def test_direct_gemini_patch_uses_process_group_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["timeout_sec"] = timeout_sec
        raise subprocess.TimeoutExpired(cmd, timeout_sec)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/gemini")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)

    out, raw = _ask_direct_gemini_flash_patch(prompt="fix", timeout_sec=7)

    assert captured["timeout_sec"] == 7
    assert out["error_category"] == "timeout"
    assert raw == ""


def test_authorization_task_text_is_not_auth_infra_invalid():
    row = {
        "baseline_raw_tail": "Refactor authorization helper while preserving deny-by-default behavior.",
        "baseline_gateway_error_category": "",
        "model_calls": 1,
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=False,
    )

    assert out["run_eligible"] is True
    assert out["infra_invalid_reason"] is None


def test_run_process_group_raises_timeout(tmp_path: Path):
    try:
        _run_process_group(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_sec=1,
        )
    except Exception as exc:
        assert exc.__class__.__name__ == "TimeoutExpired"
    else:
        raise AssertionError("process group timeout should fail closed")


def test_run_with_nexus_llm_requires_model_and_nexus_evidence(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-invalid",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"unknown"}}}'
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.bench.capability_ab_runner.subprocess.run", lambda *_args, **_kwargs: _Proc())

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

    assert out["provider"] == "gemini"
    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "nexus_delivery_invalid"
    assert out["gemini_uses_nexus"] is False
    assert out["nexus_context_delivered"] is False


def test_summarize_benchmark_rows_excludes_infra_invalid_from_solve_rate():
    rows = [
        {"mode": "without_nexus", "run_eligible": True, "status": "SUCCESS", "semantic_completed": True, "report_trust_mismatch": False, "wall_duration_sec": 2.0, "total_tokens": 100, "model_calls": 1},
        {"mode": "without_nexus", "run_eligible": False, "infra_invalid_reason": "quota_exhausted", "status": "FAILED", "semantic_completed": False, "report_trust_mismatch": True, "wall_duration_sec": 3.0, "total_tokens": 0, "model_calls": 1},
        {"mode": "with_nexus", "run_eligible": True, "status": "FAILED", "semantic_completed": False, "report_trust_mismatch": True, "wall_duration_sec": 4.0, "total_tokens": 200, "model_calls": 2},
    ]

    summary = _summarize_benchmark_rows(rows)

    assert summary["without_nexus"]["total_n"] == 2
    assert summary["without_nexus"]["eligible_n"] == 1
    assert summary["without_nexus"]["infra_invalid_n"] == 1
    assert summary["without_nexus"]["solve_rate"] == 1.0
    assert summary["with_nexus"]["solve_rate"] == 0.0


def test_per_task_stop_loss_marks_row_infra_invalid():
    row = {
        "mode": "with_nexus",
        "status": "SUCCESS",
        "wall_duration_sec": 601.0,
        "run_eligible": True,
        "infra_invalid_reason": None,
        "token_reliable": True,
    }

    assert _apply_per_task_stop_loss(row, 600) is True

    assert row["run_eligible"] is False
    assert row["infra_invalid_reason"] == "task_stop_loss_exceeded"
    assert row["runtime_classification"] == "task_stop_loss_exceeded"
    assert row["timeout_scope"] == "benchmark_per_task_stop_loss"
    assert row["timeout_stage"] == "wall_clock_exceeded"
    assert row["timeout_sec"] == 600
    assert row["token_reliable"] is False


def test_per_task_stop_loss_allows_rows_within_budget():
    row = {"wall_duration_sec": 600.0, "run_eligible": True}

    assert _apply_per_task_stop_loss(row, 600) is False

    assert row["run_eligible"] is True
    assert "infra_invalid_reason" not in row


def test_partial_markdown_report_marks_public_gate_fail():
    text = _render_partial_markdown_report(
        benchmark_date="2026-04-28",
        with_rows=[{"mode": "with_nexus"}],
        without_rows=[],
        benchmark_summary={"with_nexus": {"eligible_n": 0}},
    )

    assert "Public claim gate: FAIL" in text
    assert "With Nexus rows: 1" in text
    assert "Without Nexus rows: 0" in text
    assert '"eligible_n": 0' in text


def test_benchmark_rows_mark_zero_token_model_calls_unreliable():
    rows = [
        {
            "mode": "with_nexus",
            "run_eligible": True,
            "status": "SUCCESS",
            "semantic_completed": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 2.0,
            "total_tokens": 0,
            "model_calls": 1,
            "token_capture_status": "unknown",
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
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
        },
        {
            "mode": "without_nexus",
            "run_eligible": True,
            "status": "SUCCESS",
            "semantic_completed": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 2.0,
            "total_tokens": 123,
            "model_calls": 1,
            "token_capture_status": "estimated",
        },
    ]

    for row in rows:
        from scripts.bench.capability_ab_runner import _annotate_benchmark_eligibility

        _annotate_benchmark_eligibility(
            row,
            provider="gemini",
            model_required=True,
            nexus_required=row["mode"] == "with_nexus",
        )

    summary = _summarize_benchmark_rows(rows)

    assert rows[0]["token_reliable"] is False
    assert rows[0]["token_unreliable_reason"] == "model_call_without_tokens"
    assert rows[1]["token_reliable"] is False
    assert rows[1]["token_unreliable_reason"] == "estimated_tokens"
    assert summary["with_nexus"]["token_reliable_rate"] == 0.0
    assert summary["without_nexus"]["token_reliable_rate"] == 0.0


def test_benchmark_rows_mark_unhelpful_local_fallback():
    row = {
        "mode": "with_nexus",
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 108,
        "model_calls": 1,
        "token_capture_status": "estimated",
        "gateway_error_category": "timeout",
        "fallback_used": True,
        "nexus_winner_source": "local",
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_unverified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)
    summary = _summarize_benchmark_rows([row])

    assert row["local_fallback_unhelpful"] is True
    assert summary["with_nexus"]["local_fallback_unhelpful_rate"] == 1.0


def test_benchmark_row_splits_model_tokens_from_local_rescue():
    from scripts.bench.capability_ab_runner import _annotate_benchmark_eligibility

    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 112,
        "model_calls": 1,
        "token_capture_status": "not_applicable_local_only",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "stats",
        "gateway_prompt_chars": 10,
        "gateway_payload_chars": 20,
        "gateway_total_chars": 30,
        "gateway_timeout_sec": 60,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
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
    }

    _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert row["model_total_tokens"] == 112
    assert row["model_token_capture_status"] == "estimated"
    assert row["local_rescue_tokens"] == 0
    assert row["rescue_cost_status"] == "local_only"
    assert row["gateway_stats_present"] is True
    assert row["gateway_usage_metadata_present"] is False
    assert row["gateway_token_source"] == "stats"
    assert row["gateway_total_chars"] == 30
    assert row["gateway_timeout_sec"] == 60
    assert row["token_reliable"] is False
    assert row["token_unreliable_reason"] == "local_only_rescue_not_model_comparable"


def test_force_learn_slo_ready_writes_pass_summary(tmp_path: Path):
    _force_learn_slo_ready(tmp_path)
    payload = json.loads((tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").read_text(encoding="utf-8"))
    assert payload["phase_slo_pass"] is True
    assert payload["global"]["required_done_ratio"] == 1.0
