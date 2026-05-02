from __future__ import annotations

import argparse
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
    _hidden_verifier_infra_reason,
    _direct_gemini_timeout_sec,
    _emit_progress,
    _effective_total_timeout_sec,
    _extract_record,
    _extract_json_payload,
    _summarize_rlm_trace,
    _summarize_benchmark_rows,
    expand_task_trials,
    _force_learn_slo_ready,
    _history_policy_name,
    _hidden_verifier_mode_enabled,
    _hidden_test_for_visible_test,
    _ask_direct_gemini_flash_patch,
    _ask_direct_codex_patch,
    _parse_direct_patch_json,
    _direct_codex_timeout_sec,
    _extract_codex_stdout_tokens,
    _expected_capability_coverage,
    _prompt_leak_audit_failures,
    _benchmark_gateway_timeout_for_task,
    _benchmark_gateway_timeout_sec,
    _build_parallel_smoke_rows,
    build_public_benchmark_preflight,
    _materialize_fixture,
    _nexus_task_desc,
    _nexus_codex_hidden_verifier_guidance,
    _compact_nexus_route_for_prompt,
    _parse_direct_gemini_json,
    _pytest_verifier_cmd,
    _read_preserved_target,
    _remaining_leg_timeout,
    _remaining_task_timeout,
    _report_model_label,
    _render_partial_markdown_report,
    _restore_preserved_target,
    _resolve_task_files,
    _run_process_group,
    _tail_text,
    _task_uses_materialized_fixture,
    _without_tasks_for_run,
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


def test_hidden_verifier_infra_error_is_not_trust_mismatch():
    row = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "hidden_verifier_passed": False,
        "hidden_verifier_stderr_tail": "error: failed to open file `/Users/example/.cache/uv/sdists-v9/.git`: Operation not permitted",
        "report_trust_mismatch": False,
    }

    assert _hidden_verifier_infra_reason(row) == "hidden_verifier_infra_error"
    annotated = _annotate_benchmark_eligibility(row, provider="local", model_required=False, nexus_required=False)

    assert annotated["run_eligible"] is False
    assert annotated["infra_invalid_reason"] == "hidden_verifier_infra_error"
    assert annotated["report_trust_mismatch"] is False


def test_pytest_verifier_cmd_uses_current_python():
    cmd = _pytest_verifier_cmd("tests/test_demo.py")

    assert cmd[:3] == [sys.executable, "-m", "pytest"]
    assert "uv" not in cmd
    assert cmd[-1] == "tests/test_demo.py"


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
                "expected_capabilities": ["codeintel", "hyper"],
                "capability_activation_contract": "required",
                "hidden_oracle_kind": "pytest_hidden",
                "cost_budget": {"max_wall_sec": 600, "max_model_calls": 2},
                "token_budget": 50000,
                "wall_time_budget_sec": 600,
                "public_claim_allowed_metrics": ["verified_delivery_rate"],
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
    assert tasks[0].expected_capabilities == ("codeintel", "hyper")
    assert tasks[0].capability_activation_contract == "required"
    assert tasks[0].hidden_oracle_kind == "pytest_hidden"
    assert tasks[0].cost_budget == {"max_wall_sec": 600, "max_model_calls": 2}
    assert tasks[0].token_budget == 50000
    assert tasks[0].wall_time_budget_sec == 600.0
    assert tasks[0].public_claim_allowed_metrics == ("verified_delivery_rate",)


def test_expected_capability_coverage_reports_static_gaps():
    tasks = [
        CapabilityTask(
            id="a",
            difficulty="hard",
            task_type="bug",
            task_desc="a",
            target_file="a",
            test_file="a",
            success_criteria="patch_and_tests_pass",
            expected_capabilities=("codeintel", "hyper"),
            capability_activation_contract="required",
        ),
        CapabilityTask(
            id="b",
            difficulty="hard",
            task_type="bug",
            task_desc="b",
            target_file="b",
            test_file="b",
            success_criteria="patch_and_tests_pass",
        ),
    ]

    out = _expected_capability_coverage(tasks)

    assert out["declared"] == ["codeintel", "hyper"]
    assert "swarm" in out["missing_core"]
    assert out["tasks_missing_expected"] == ["b"]
    assert out["required_or_cost_capped"] == ["codeintel", "hyper"]


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


def test_remaining_task_timeout_uses_shared_deadline(monkeypatch):
    monkeypatch.setattr("scripts.bench.capability_ab_runner.time.monotonic", lambda: 100.4)

    assert _remaining_task_timeout(105.9, 300) == 5


def test_remaining_task_timeout_raises_when_deadline_is_spent(monkeypatch):
    monkeypatch.setattr("scripts.bench.capability_ab_runner.time.monotonic", lambda: 106.0)

    try:
        _remaining_task_timeout(105.9, 300)
    except subprocess.TimeoutExpired as exc:
        assert exc.timeout == 300
    else:
        raise AssertionError("expected timeout")


def test_public_benchmark_preflight_passes_without_model_invocation(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    disclosure_manifest = tmp_path / "tasks.public.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                        "rlm_challenge": "hidden_governance",
                        "commercial_lane": "capability_lift",
                        "expected_capabilities": ["codeintel", "hyper", "autoreason"],
                        "capability_activation_contract": "required",
                        "hidden_oracle_kind": "pytest_hidden",
                        "cost_budget": {
                            "max_wall_sec": 600,
                            "max_model_calls": 3,
                            "max_tokens": 60000,
                            "max_capability_stack_size": 6,
                        },
                        "public_claim_allowed_metrics": ["verified_delivery_rate"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    disclosure_manifest.write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_sanitized_manifest_v1",
                "tasks": [
                    {
                        "id": "task-1",
                        "repo": "fixture://sanitized",
                        "task_desc": "Fix the hidden bug.",
                        "expected_capabilities": ["codeintel", "hyper", "autoreason"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest=str(disclosure_manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=2,
        shuffle_seed=7,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    coverage = report["task_manifest"]["expected_capability_coverage"]
    assert coverage["declared"] == ["autoreason", "codeintel", "hyper"]
    assert "swarm" in coverage["missing_core"]
    assert report["capability_readiness"]["status"] == "PASS"
    assert report["model_lock"]["same_model"] is True
    assert report["task_manifest"]["selected_n"] == 1
    assert report["task_manifest"]["expanded_n"] == 2
    assert report["public_claim_requirements"]["hidden_verifier_mode"] is True
    assert report["public_disclosure_manifest"]["status"] == "PASS"
    assert report["public_disclosure_manifest"]["sha256"]


def test_public_benchmark_preflight_rejects_unsanitized_disclosure_manifest(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    disclosure_manifest = tmp_path / "tasks.public.json"
    disclosure_manifest.write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_sanitized_manifest_v1",
                "tasks": [
                    {
                        "id": "task-1",
                        "repo": "/Users/example/private/repo",
                        "allowed_files": ["target.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest=str(disclosure_manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert report["public_disclosure_manifest"]["status"] == "FAIL"
    assert "public_disclosure:disclosure_task_1_contains_file_scope" in report["failures"]
    assert "public_disclosure:disclosure_task_1_repo_not_sanitized" in report["failures"]


def test_public_benchmark_preflight_accepts_codex_model_lock(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-codex-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                        "commercial_lane": "capability_lift",
                        "source_manifest": "scripts/bench/public_benchmark_commercial_lanes_v1.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_GEMINI_MODEL_NAME", raising=False)
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_MODEL", raising=False)
    monkeypatch.setenv("NEXUS_CODEX_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("NEXUS_DIRECT_CODEX_MODEL", "gpt-5.5")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="codex",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="codex",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    assert report["model_lock"]["same_model"] is True
    assert "direct_codex_provider_is_prompt_wearing_only_for_external_model_claims" in str(report["capability_readiness"]["warnings"])


def test_public_benchmark_preflight_fails_for_unlocked_model_and_no_hidden_verifier(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("NEXUS_VALUE_HIDDEN_VERIFIER", raising=False)
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3.1-pro-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=0,
        stop_loss_sec=0,
        per_task_stop_loss_sec=900,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="",
        with_nexus_runner="inprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=False,
        enable_ddtree_executor=False,
        enable_ultra_review_dry_gate=False,
        llm_candidate_cap=1,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert "model_lock_mismatch" in report["failures"]
    assert "hidden_verifier_disabled" in report["failures"]
    assert "per_task_stop_loss_above_600" in report["failures"]
    assert "manifest_tasks_empty" in report["failures"]
    assert "capability_readiness:autoreason_executor_flag_missing" in report["failures"]
    assert "capability_readiness:ddtree_executor_flag_missing" in report["failures"]
    assert "capability_readiness:ultra_review_dry_gate_flag_missing" in report["failures"]


def test_public_benchmark_preflight_blocks_model_run_without_executor_evidence_flags(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-readiness-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix a governance bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=False,
        enable_ddtree_executor=False,
        enable_ultra_review_dry_gate=False,
        llm_candidate_cap=1,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert report["capability_readiness"]["status"] == "FAIL"
    assert "capability_readiness:autoreason_executor_flag_missing" in report["failures"]
    assert "capability_readiness:llm_candidate_cap_below_ddtree_threshold" in report["failures"]


def test_public_benchmark_preflight_allows_nexus_only_without_direct_model(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-nexus-only-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix a governance bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_MODEL", raising=False)
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=True,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    assert "direct_model_env_missing" not in report["failures"]
    assert report["public_claim_requirements"]["single_arm_run"] is True
    assert report["public_claim_requirements"]["public_claim_allowed"] is False


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


def test_parse_direct_patch_json_accepts_fenced_codex_json():
    payload, output = _parse_direct_patch_json('```json\n{"status":"OK","patch":"x = 1\\n"}\n```')
    assert output.startswith("{")
    assert payload["patch"] == "x = 1\n"
    assert payload["token_capture_status"] == "missing_gateway_stats"


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
        difficulty="easy",
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
    hidden_test_source = Path(_hidden_test_for_visible_test(test)).read_text(encoding="utf-8")
    assert "overall_status" in target_source
    assert "compute_backoff" not in target_source
    assert "spec_from_file_location" in test_source
    assert "test_overall_status_passes_when_all_phases_pass" in test_source
    assert "missing_evidence" not in test_source
    assert "missing_evidence" in hidden_test_source


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


def test_public_candidate_fixtures_have_distinct_visible_and_hidden_tests(tmp_path: Path):
    manifest_paths = [
        "scripts/bench/public_benchmark_nexus_value_v1.json",
        "scripts/bench/public_benchmark_rlm_harder_v2.json",
        "scripts/bench/public_benchmark_route_oracles_v1.json",
    ]
    tasks = [
        task
        for manifest_path in manifest_paths
        for task in load_tasks(manifest_path)
        if task.fixture_kind.startswith(("nexus_value_", "rlm_harder_"))
    ]

    not_split: list[str] = []
    for task in tasks:
        _target, visible_test = _materialize_fixture(tmp_path, task)
        hidden_test = _hidden_test_for_visible_test(visible_test)
        if Path(visible_test).read_text(encoding="utf-8") == Path(hidden_test).read_text(encoding="utf-8"):
            not_split.append(task.fixture_kind)

    assert not not_split


def test_route_oracle_fixtures_have_hidden_capability_conditions(tmp_path: Path):
    tasks = load_tasks("scripts/bench/public_benchmark_route_oracles_v1.json")

    by_fixture: dict[str, str] = {}
    for task in tasks:
        _target, visible_test = _materialize_fixture(tmp_path / task.id, task)
        hidden_source = Path(_hidden_test_for_visible_test(visible_test)).read_text(encoding="utf-8")
        by_fixture[task.fixture_kind] = hidden_source

    assert "unsupported" in by_fixture["rlm_harder_v2_autoreason_judge"]
    assert "risky-required" in by_fixture["rlm_harder_v2_ddtree_pruning"]
    assert "negative_exit_code" in by_fixture["rlm_harder_v2_ultra_review_report"]
    assert "wrong-topic" in by_fixture["rlm_harder_v2_research_citation"]
    assert "missing-source" in by_fixture["rlm_harder_v2_lancedb_retrieval"]
    assert "single_role" in by_fixture["rlm_harder_v2_swarm_consensus"]
    assert "count_mismatch" in by_fixture["rlm_harder_v2_drone_artifacts"]
    assert "recommended_without_invocation" in by_fixture["rlm_harder_v2_nightshift_recovery"]


def test_codex_guidance_names_incident_classifier_needs_evidence() -> None:
    task = CapabilityTask(
        id="nexus-value-trust-002",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix an incident classifier that over-trusts a passing smoke test.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_trust_incident_classifier",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(
        task,
        "def classify(smoke_passed, semantic_evidence):\n    return 'resolved' if smoke_passed else 'open'\n",
    )

    assert "returns needs_evidence" in guidance
    assert "smoke_passed=False remains open" in guidance


def test_resolve_task_files_can_fail_closed_without_materializing(tmp_path: Path):
    task = CapabilityTask(
        id="real-001",
        difficulty="easy",
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
    row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 2,
        "status": "SUCCESS",
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
    }
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
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 2,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "gateway_stats_present": True,
    }
    write_jsonl(without_path, [without_row])
    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus_public_benchmark_evidence_bundle_v2"
    assert payload["raw_files"]["with_nexus"]["sha256"]
    assert len(payload["artifact_files"]) == 2
    assert payload["model_lock"]["same_model"] is True
    assert payload["row_counts"]["with_nexus"] == 1
    assert payload["row_counts"]["without_nexus"] == 1
    assert payload["nexus_wearing"]["valid_rate"] == 1.0
    assert payload["public_claim_gate"]["verdict"] == "PASS"
    assert payload["public_claim_gate"]["checks"]["hidden_verifier_mode"] is True
    assert payload["public_claim_gate"]["checks"]["run_eligibility_complete"] is True
    assert payload["public_claim_gate"]["checks"]["trust_mismatch_free"] is True
    assert payload["public_claim_gate"]["checks"]["nexus_wearing_valid_rate"] == 1.0
    assert payload["public_claim_gate"]["checks"]["route_decision_present_rate"] == 1.0
    assert payload["public_claim_gate"]["checks"]["route_cost_ledger_schema"] == "nexus_route_cost_ledger_v1"
    assert payload["public_claim_gate"]["checks"]["product_kpis_schema"] == "nexus_product_kpis_v1"
    assert payload["route_cost_ledger"]["scope"] == "measured_benchmark_telemetry_not_billing_cost"
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["rows"] == 1
    assert payload["route_cost_ledger"]["arms"]["without_nexus"]["rows"] == 1
    assert payload["product_kpis"]["schema"] == "nexus_product_kpis_v1"
    assert payload["product_kpis"]["arms"]["with_nexus"]["avg_time_to_verified_sec"] == 0.0
    assert payload["product_kpis"]["arms"]["without_nexus"]["fail_closed_block_rate"] == 1.0


def test_write_evidence_bundle_fails_gate_when_route_decision_missing(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "runner_command": "run",
            "hidden_verifier_mode": True,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "route_decision_missing" in payload["public_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["route_decision_present_rate"] == 0.0


def test_write_evidence_bundle_v2_fails_gate_for_missing_hidden_verifier_and_trust_mismatch(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "report_trust_mismatch": True,
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "run"},
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "hidden_verifier_disabled" in payload["public_claim_gate"]["failures"]
    assert "with_trust_mismatch_above_zero" in payload["public_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["trust_mismatch_free"] is False


def test_write_evidence_bundle_v2_fails_gate_when_models_differ(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {"mode": "with_nexus", "model_name": "gemini-3-flash-preview"}
    without_row = {"mode": "without_nexus", "model_name": "gemini-3.1-pro-preview"}
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "run"},
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["model_lock"]["same_model"] is False
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "model_mismatch" in payload["public_claim_gate"]["failures"]


def test_write_evidence_bundle_fails_gate_for_parallel_smoke(tmp_path: Path):
    task = CapabilityTask(
        id="smoke-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="smoke",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    with_rows, without_rows = _build_parallel_smoke_rows([task], model_name="gemini-3-flash-preview")
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    write_jsonl(with_path, with_rows)
    write_jsonl(without_path, without_rows)

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[*with_rows, *without_rows],
        config={
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "runner_command": "run --parallel-arms smoke-only",
            "parallel_arms": "smoke-only",
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert with_rows[0]["run_eligible"] is False
    assert with_rows[0]["infra_invalid_reason"] == "parallel_smoke"
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "parallel_smoke" in payload["public_claim_gate"]["failures"]


def test_write_evidence_bundle_fails_gate_for_single_arm_run(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {"mode": "with_nexus", "model_name": "gemini-3-flash-preview", "run_eligible": True}
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row],
        config={"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "run --nexus-only"},
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["row_counts"]["with_nexus"] == 1
    assert payload["row_counts"]["without_nexus"] == 0
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "single_arm_run" in payload["public_claim_gate"]["failures"]


def test_partial_markdown_report_explains_single_arm_run():
    out = _render_partial_markdown_report(
        benchmark_date="2026-04-30",
        with_rows=[{"mode": "with_nexus"}],
        without_rows=[],
        benchmark_summary={"with_nexus": {"total_n": 1}},
    )

    assert "Public claim gate: FAIL" in out
    assert "single-arm run" in out


def test_without_tasks_for_run_skips_bare_arm_for_nexus_only():
    task = CapabilityTask(
        id="route-smoke",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="all_target_tests_pass",
    )

    assert _without_tasks_for_run([task], timed_out=False, nexus_only=False) == [task]
    assert _without_tasks_for_run([task], timed_out=False, nexus_only=True) == []
    assert _without_tasks_for_run([task], timed_out=True, nexus_only=False) == []


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
            "nexus_tier": "full",
            "nexus_tier_reason": "high_risk_or_forced_hyper",
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
            "capabilities": {
                "research_used": True,
                "hyper_used": True,
                "self_heal_used": True,
                "claim_verified": True,
                "nightshift_recommended": False,
                "nightshift_invoked": True,
                "nightshift_recovered": False,
                "nightshift_report_path": ".nexus/reports/nightshift/run.json",
                "nightshift_failure_reason": "report_without_recovery",
                "nightshift_report": {
                    "schema_version": "nexus_nightshift_receipt_v1",
                    "failure_reason": "report_without_recovery",
                },
                "swarm_used": True,
                "swarm_evidence_count": 2,
                "swarm_consensus": "candidate_summary_evidence",
                "swarm_report": {
                    "schema_version": "nexus_swarm_receipt_v1",
                    "consensus": "candidate_summary_evidence",
                },
                "drone_used": True,
                "drone_invoked_count": 1,
                "drone_artifact_path": ".nexus/reports/drones/d1_crystal.json",
                "drone_report": {
                    "schema_version": "nexus_drone_receipt_v1",
                    "artifact_count": 1,
                },
            },
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
                "governance_layers": ["ultra_review"],
                "stop_policy": {"type": "a_streak", "threshold": 2},
            },
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "candidate-2",
                "stop_reason": "a_streak_met",
                "judge_votes": [{"judge": "evidence"}, {"judge": "specificity"}],
                "borda_scores": {"candidate-1": 2, "candidate-2": 4},
            },
            "ddtree": {
                "enabled": True,
                "eligible": True,
                "selected_candidate_ids": ["candidate-2"],
                "estimated_saved_steps": 2,
                "actual_saved_steps": 2,
                "reason": "deterministic_score_pruning",
            },
            "ultra_review": {
                "recommended": True,
                "invoked": True,
                "gate_passed": True,
                "report_path": ".nexus/reports/ultra_review/route_gate_report.json",
                "reason": "dry_gate_passed",
                "failures": [],
            },
            "codeintel": {
                "gate_mode": "scan_impact_required",
                "scan_report_present": True,
                "impact_report_present": True,
                "claim_bundle_present": True,
                "scan_report_path": ".nexus/reports/codeintel/scan.json",
                "impact_report_path": ".nexus/reports/codeintel/impact.json",
                "risk_score": 35,
                "impacted_files_count": 3,
            },
            "jit": {
                "ranking_mode": "static",
                "promotion_verdict": "HOLD",
                "static_default_unchanged": True,
                "miss_rate": 0.0,
                "fallback_run_rate": 0.1,
                "unmatched_path_rate": 0.0,
                "predictive_saved_runtime_sec": 12.5,
            },
            "capability_plan": {
                "schema_version": "nexus_capability_plan_v1",
                "planner_mode": "dry_run",
                "selected_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate", "hyper", "autoreason"],
                "required_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate"],
                "conditional_capabilities": ["hyper", "autoreason"],
                "forbidden_capabilities": [],
                "decision_trace": [{"capability": "hyper", "state": "conditional"}],
                "replan_trace": [{"phase": "P", "active_capabilities": ["hyper"]}, {"phase": "A", "active_capabilities": ["claim_gate"]}],
                "score": 18,
            },
            "route_decision": {
                "schema_version": "nexus_route_decision_v1",
                "selected_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate", "hyper", "autoreason"],
                "required_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate"],
                "conditional_capabilities": ["hyper", "autoreason"],
                "pending_capabilities": ["swarm"],
                "forbidden_capabilities": [],
                "signal_snapshot": {
                    "risk_score_0_100": 87,
                    "risk_score_0_1": 0.87,
                    "risk_band": "high",
                    "risk_band_reason": "high_risk:87",
                    "pillar_signals": {
                        "MemPalace": {"active": True},
                        "Artifact": {"active": True},
                        "Claim": {"active": True},
                    }
                },
                "forecast_gate_shadow": {
                    "schema": "nexus_forecast_gate_shadow_v1",
                    "shadow_mode": True,
                    "suggested_tier": "L3_full_governed",
                    "suggested_tier_reason": "high_risk_or_ultra_review_selected",
                    "early_exit_candidate": False,
                    "early_exit_policy": "never_skip_mempalace_artifact_claim_delivery_gates",
                },
            },
        },
        "timing": {
            "cli_elapsed_sec": 2.4,
            "phase_wall_sec": {"P": 0.1, "X": 0.2, "D": 0.3, "R": 1.1, "A": 0.4, "C": 0.5},
            "breakdown_sec": {"target_io_sec": 0.01, "codeintel_sec": 0.2, "context_pack_sec": 0.03},
        },
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
    assert out["route_risk_score_0_100"] == 87
    assert out["route_risk_score_0_1"] == 0.87
    assert out["route_risk_band"] == "high"
    assert out["route_risk_band_reason"] == "high_risk:87"
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
    assert out["nexus_tier"] == "full"
    assert out["nexus_tier_reason"] == "high_risk_or_forced_hyper"
    assert out["nexus_usage_valid"] is True
    assert out["nexus_rescued"] is True
    assert out["pillar_mempalace_verified"] is True
    assert out["phase_r"] == "hyper_executed"
    assert out["cli_elapsed_sec"] == 2.4
    assert out["phase_wall_total_sec"] == 2.6
    assert out["cli_uninstrumented_sec"] == 0.0
    assert out["runner_overhead_sec"] == 0.1
    assert out["timing_target_io_sec"] == 0.01
    assert out["timing_codeintel_sec"] == 0.2
    assert out["timing_context_pack_sec"] == 0.03
    assert out["phase_wall_r_sec"] == 1.1
    assert out["capability_hyper_used"] is True
    assert out["capability_claim_verified"] is True
    assert out["capability_swarm_used"] is True
    assert out["capability_swarm_evidence_count"] == 2
    assert out["capability_swarm_report_schema_version"] == "nexus_swarm_receipt_v1"
    assert out["capability_swarm_consensus"] == "candidate_summary_evidence"
    assert out["capability_drone_used"] is True
    assert out["capability_drone_invoked_count"] == 1
    assert out["capability_drone_report_schema_version"] == "nexus_drone_receipt_v1"
    assert out["capability_drone_artifact_path"] == ".nexus/reports/drones/d1_crystal.json"
    assert out["capability_nightshift_invoked"] is True
    assert out["capability_nightshift_recovered"] is False
    assert out["capability_nightshift_report_path"] == ".nexus/reports/nightshift/run.json"
    assert out["capability_nightshift_report_schema_version"] == "nexus_nightshift_receipt_v1"
    assert out["capability_nightshift_failure_reason"] == "report_without_recovery"
    assert out["capability_stack_selected"] == ["hyper_sprint", "autoreason"]
    assert out["capability_stack_acceleration_layers"] == ["ddtree"]
    assert out["capability_stack_governance_layers"] == ["ultra_review"]
    assert out["capability_stack_stop_policy_type"] == "a_streak"
    assert out["autoreason_enabled"] is True
    assert out["autoreason_status"] == "SUCCESS"
    assert out["autoreason_winner"] == "candidate-2"
    assert out["autoreason_stop_reason"] == "a_streak_met"
    assert out["autoreason_judge_votes_count"] == 2
    assert out["autoreason_borda_scores"] == {"candidate-1": 2, "candidate-2": 4}
    assert out["ddtree_enabled"] is True
    assert out["ddtree_eligible"] is True
    assert out["ddtree_selected_candidate_ids"] == ["candidate-2"]
    assert out["ddtree_actual_saved_steps"] == 2
    assert out["ddtree_reason"] == "deterministic_score_pruning"
    assert out["ultra_review_recommended"] is True
    assert out["ultra_review_invoked"] is True
    assert out["ultra_review_gate_passed"] is True
    assert out["ultra_review_report_path"] == ".nexus/reports/ultra_review/route_gate_report.json"
    assert out["ultra_review_reason"] == "dry_gate_passed"
    assert out["ultra_review_failures"] == []
    assert out["codeintel_scan_report_present"] is True
    assert out["codeintel_impact_report_present"] is True
    assert out["codeintel_claim_bundle_present"] is True
    assert out["codeintel_scan_report_path"] == ".nexus/reports/codeintel/scan.json"
    assert out["codeintel_impact_report_path"] == ".nexus/reports/codeintel/impact.json"
    assert out["codeintel_risk_score"] == 35
    assert out["codeintel_impacted_files_count"] == 3
    assert out["jit_ranking_mode"] == "static"
    assert out["jit_promotion_verdict"] == "HOLD"
    assert out["jit_predictive_saved_runtime_sec"] == 12.5
    assert out["capability_plan_trace_present"] is True
    assert out["capability_plan_schema_version"] == "nexus_capability_plan_v1"
    assert out["capability_plan_mode"] == "dry_run"
    assert out["capability_plan_score"] == 18
    assert out["capability_plan_node_count"] == 1
    assert out["capability_plan_required"] == ["mempalace_gate", "artifact_gate", "claim_gate"]
    assert out["capability_plan_conditional"] == ["hyper", "autoreason"]
    assert out["capability_plan_phases"] == ["P", "A"]
    assert out["route_decision_schema_version"] == "nexus_route_decision_v1"
    assert out["route_decision_selected_count"] == 5
    assert out["route_decision_required_count"] == 3
    assert out["route_decision_conditional_count"] == 2
    assert out["route_decision_pending"] == ["swarm"]
    assert out["forecast_gate_shadow_schema"] == "nexus_forecast_gate_shadow_v1"
    assert out["forecast_gate_shadow_mode"] is True
    assert out["forecast_gate_suggested_tier"] == "L3_full_governed"
    assert out["forecast_gate_early_exit_candidate"] is False
    assert out["forecast_gate_early_exit_policy"] == "never_skip_mempalace_artifact_claim_delivery_gates"
    assert out["route_decision_pillars_active"] == ["MemPalace", "Artifact", "Claim"]
    assert out["semantic_completed"] is False
    assert out["nexus_pillars_observed"] == ["lancedb", "memory", "mempalace", "belief", "artifact"]
    assert out["nexus_phases_observed"] == ["P", "X", "D", "R", "A", "C"]


def test_extract_record_summarizes_child_and_parent_timing_gaps():
    task = CapabilityTask(
        id="timing-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix timing",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="all_target_tests_pass",
    )
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "timing": {
            "cli_elapsed_sec": 10.0,
            "phase_wall_sec": {"P": 1.0, "X": 2.0, "D": 0.5, "R": 1.5, "A": 2.0, "C": 1.0},
            "breakdown_sec": {"target_io_sec": 0.2, "codeintel_sec": 1.7, "context_pack_sec": 0.1},
        },
        "result": {"elapsed_sec": 10.0, "report": {"model_calls": 0, "total_tokens": 0}},
    }

    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=12.5)

    assert out["phase_wall_total_sec"] == 8.0
    assert out["cli_uninstrumented_sec"] == 2.0
    assert out["runner_overhead_sec"] == 2.5
    assert out["timing_target_io_sec"] == 0.2
    assert out["timing_codeintel_sec"] == 1.7
    assert out["timing_context_pack_sec"] == 0.1


def test_extract_record_summarizes_rlm_trace_quality(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "t",
                        "phase": "R",
                        "iteration_id": "r-1",
                        "action_type": "submit",
                        "stop_reason": "submit",
                        "confidence": 0.75,
                        "allowed_tools": ["read_file", "safe_patch"],
                        "artifact_refs": ["patch.diff"],
                    }
                ),
                json.dumps(
                    {
                        "task_id": "t",
                        "phase": "A",
                        "iteration_id": "a-1",
                        "action_type": "audit",
                        "stop_reason": "verified",
                        "confidence": 1.0,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    task = CapabilityTask(
        id="rlm-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix with RLM",
        target_file="a.py",
        test_file="tests/test_a.py",
        success_criteria="patch_and_tests_pass",
    )
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "rlm_trace_path": str(trace_path),
            "rlm_loop_phase": "X",
            "rlm_x_loop_budget_observed": True,
            "rlm_required_gates": ["rlm_trace_present", "x_loop_budget_observed"],
        },
    }

    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=1.0)

    assert out["rlm_trace_present"] is True
    assert out["rlm_iteration_count"] == 2
    assert out["rlm_submit_count"] == 1
    assert out["rlm_verified_count"] == 1
    assert out["rlm_allowed_tools_count"] == 2
    assert out["rlm_avg_confidence"] == 0.875
    assert out["rlm_evidence_density"] == 0.5
    assert out["rlm_trace_quality_score"] == 100
    assert out["rlm_loop_phase"] == "X"
    assert out["rlm_x_loop_budget_observed"] is True
    assert out["rlm_required_gates"] == ["rlm_trace_present", "x_loop_budget_observed"]


def test_summarize_rlm_trace_marks_missing_trace():
    summary = _summarize_rlm_trace("/tmp/nexus/missing-rlm-trace.jsonl")

    assert summary["rlm_iteration_count"] == 0
    assert summary["rlm_stop_reasons"] == ["trace_missing"]


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
        expected_capabilities=("claim_gate", "delivery_gate"),
        capability_activation_contract="required",
        hidden_oracle_kind="pytest_hidden",
        cost_budget={"max_model_calls": 3},
        token_budget=123,
        wall_time_budget_sec=45.0,
        public_claim_allowed_metrics=("verified_delivery_rate",),
    )

    expanded = expand_task_trials([task], repeat_trials=2, shuffle_seed=None)

    assert [item.trial_index for item in expanded] == [1, 2]
    assert {item.fixture_kind for item in expanded} == {"nexus_value_hidden_state"}
    assert {item.expected_capabilities for item in expanded} == {("claim_gate", "delivery_gate")}
    assert {item.capability_activation_contract for item in expanded} == {"required"}
    assert {item.hidden_oracle_kind for item in expanded} == {"pytest_hidden"}
    assert {item.cost_budget["max_model_calls"] for item in expanded if item.cost_budget} == {3}
    assert {item.token_budget for item in expanded} == {123}
    assert {item.wall_time_budget_sec for item in expanded} == {45.0}
    assert {item.public_claim_allowed_metrics for item in expanded} == {("verified_delivery_rate",)}


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


def test_run_with_nexus_codex_provider_delivers_nexus_context(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="codex-nexus-001",
        difficulty="easy",
        task_type="public_bugfix",
        task_desc="Fix evidence-backed normalization repair.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_codex_patch(*, prompt, timeout_sec):
        assert "You are Codex wearing Nexus" in prompt
        assert "[NEXUS ROUTE SUMMARY]" in prompt
        assert "[NEXUS CODEINTEL SUMMARY]" in prompt
        assert "[NEXUS EXECUTION PROFILE]" in prompt
        assert "[NEXUS HIDDEN-VERIFIER GUIDANCE]" in prompt
        assert "capability_stack" not in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 200,
                "token_capture_status": "measured",
                "model_name": "gpt-5.5",
                "model_patch_generated": True,
                "gateway_stats_present": True,
                "gateway_token_source": "codex_stdout",
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_codex_patch", fake_ask_direct_codex_patch)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="inprocess",
        with_llm_mode="all",
        with_model_provider="codex",
    )

    assert out["status"] == "SUCCESS"
    assert out["provider"] == "codex"
    assert out["model_name"] == "gpt-5.5"
    assert out["gemini_uses_nexus"] is True
    assert out["nexus_context_delivered"] is True
    assert set(out["nexus_pillars_observed"]) == {"lancedb", "memory", "mempalace", "belief", "artifact"}
    assert set(out["nexus_phases_observed"]) == {"P", "X", "D", "R", "A", "C"}
    assert out["nexus_wearing_valid"] is True
    assert out["codeintel_scan_report_present"] is True
    assert any(item["name"] == "codeintel" and item["public_claim_safe"] for item in out["capability_receipts"])
    receipts = {item["name"]: item for item in out["capability_receipts"]}
    assert "autoreason" not in receipts
    assert "ddtree" not in receipts
    assert "ultra_review" not in receipts
    assert receipts["artifact_gate"]["public_claim_safe"] is True
    assert receipts["claim_gate"]["public_claim_safe"] is True
    assert receipts["delivery_gate"]["public_claim_safe"] is True
    assert receipts["mempalace_gate"]["public_claim_safe"] is True
    assert out["ultra_review_invoked"] is False
    assert out["ultra_review_gate_passed"] is False
    assert out["capability_receipts_json"]
    assert out["gateway_stats_present"] is True
    assert out["gateway_token_source"] == "codex_stdout"
    assert out["gateway_prompt_chars"] > 0


def test_compact_nexus_route_for_prompt_excludes_verbose_payload():
    route = {
        "recommended_flow": "hyper_sprint",
        "recommended_reason": "commercial_public_task_prefers_hyper",
        "findings_hits": 2,
        "route_features": {"risk_score": 55, "has_hard_signal": True, "memory_hits": 1},
        "route_decision": {
            "selected_capabilities": ["research", "hyper", "ultra_review"],
            "governance_layers": ["ultra_review"],
            "acceleration_layers": [],
            "decision_trace": [{"node": "verbose"}],
        },
        "capability_stack": {"selected_capabilities": ["legacy-only"]},
        "explain_payload": {"reasoning": "large"},
    }

    compact = _compact_nexus_route_for_prompt(route)

    assert compact["recommended_flow"] == "hyper_sprint"
    assert compact["routing_evidence_status"] == "route_decision_present"
    assert compact["risk_score"] == 55
    assert compact["selected_capabilities"] == ["research", "hyper", "ultra_review"]
    assert compact["governance_layers"] == ["ultra_review"]
    assert "decision_trace" not in compact
    assert "explain_payload" not in compact


def test_compact_nexus_route_for_prompt_does_not_fallback_to_capability_stack():
    route = {
        "recommended_flow": "baseline",
        "capability_stack": {
            "selected_capabilities": ["hyper_sprint", "autoreason"],
            "acceleration_layers": ["ddtree"],
            "governance_layers": ["ultra_review"],
        },
    }

    compact = _compact_nexus_route_for_prompt(route)

    assert compact["routing_evidence_status"] == "missing_route_decision"
    assert compact["selected_capabilities"] == []
    assert compact["governance_layers"] == []
    assert compact["acceleration_layers"] == []


def test_nexus_codex_hidden_verifier_guidance_names_merge_invariant():
    task = CapabilityTask(
        id="repair",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Repair merge helper.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(
        task,
        "def merge_limits(defaults, override):\n    result.update(override or {})\n",
    )

    assert "Visible tests are acceptance hints" in guidance
    assert "preserve caller-owned inputs" in guidance
    assert "ignore override values that are None" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_context_contracts():
    timeout_task = CapabilityTask(
        id="timeout",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Repair a flaky-looking timeout calculation.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    response_task = CapabilityTask(
        id="response",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync code and docs after a renamed public field.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    config_task = CapabilityTask(
        id="config",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync configuration docs and strict parser defaults.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )

    assert "clamp the result" in _nexus_codex_hidden_verifier_guidance(timeout_task, "def remaining_ms(): pass")
    assert "canonical output field is result" in _nexus_codex_hidden_verifier_guidance(response_task, "def build_response(): pass")
    assert "strict=True and retries=3" in _nexus_codex_hidden_verifier_guidance(config_task, "def parse_config(data): pass")


def test_nexus_codex_hidden_verifier_guidance_names_belief_budget_contract():
    task = CapabilityTask(
        id="belief",
        category="bugfix",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix repair budget selection so low confidence and high risk require extra evidence-gathering rounds.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_belief_budget",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def rlm_harder_v2_repair_budget(confidence, risk): pass")

    assert "confidence is low or uncertain" in guidance
    assert "risk is elevated" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_governance_contracts():
    guard_task = CapabilityTask(
        id="guard",
        category="ops_research",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Tighten an action filter so unsafe operations are rejected while ordinary read-only work remains allowed.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_governance_guard",
        success_criteria="patch_and_tests_pass",
    )
    scope_task = CapabilityTask(
        id="scope",
        category="ops_research",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix scope enforcement so unapproved mutating operations are blocked while read-only inspection remains allowed.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_governance_scope",
        success_criteria="patch_and_tests_pass",
    )

    assert "reason governance_block" in _nexus_codex_hidden_verifier_guidance(guard_task, "def rlm_harder_v2_filter_action(action): pass")
    assert "reason scope_block" in _nexus_codex_hidden_verifier_guidance(scope_task, "def rlm_harder_v2_scope_decision(request): pass")


def test_nexus_codex_hidden_verifier_guidance_names_secret_redaction_contract():
    task = CapabilityTask(
        id="nexus-value-gov-001",
        difficulty="hard",
        task_type="public_refactor",
        task_desc="Refactor a credential scrubber while preserving the governance boundary.",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_mempalace_secret_redaction",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def redact(record): pass")

    assert "redact token, password, secret, api_key" in guidance
    assert "'[REDACTED]'" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_replay_contract():
    task = CapabilityTask(
        id="replay",
        category="feature",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix replay evidence receipts.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_evidence_replay",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def rlm_harder_v2_accept_receipt(receipt): pass")

    assert "non-empty replay_command" in guidance
    assert "exit_code == 0" in guidance
    assert "schema aliases" in guidance


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
    scope = CapabilityTask(
        id="scope",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix scope enforcement.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_governance_scope",
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
    replay = CapabilityTask(
        id="replay",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix replay evidence.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_evidence_replay",
    )

    assert "Nexus MemPalace rule" in _nexus_task_desc(governance)
    assert "reason governance_block" in _nexus_task_desc(governance)
    assert "Nexus scope enforcement rule" in _nexus_task_desc(scope)
    assert "reason scope_block" in _nexus_task_desc(scope)
    assert "Nexus Belief/Memory rule" in _nexus_task_desc(memory)
    assert "Nexus Belief budget rule" in _nexus_task_desc(belief)
    assert "{'rounds': 3, 'needs_evidence': True}" not in _nexus_task_desc(belief)
    assert "Nexus replay evidence rule" in _nexus_task_desc(replay)
    assert "non-empty replay_command" in _nexus_task_desc(replay)
    assert "exit_code == 0" in _nexus_task_desc(replay)
    assert "schema aliases" in _nexus_task_desc(replay)


def test_prompt_leak_audit_accepts_current_rlm_harder_v2_guidance():
    tasks = load_tasks("scripts/bench/public_benchmark_rlm_harder_v2.json")

    failures = _prompt_leak_audit_failures(tasks, repo_root=Path.cwd())

    assert failures == []


def test_prompt_leak_audit_blocks_hidden_only_literals(monkeypatch):
    task = next(
        task
        for task in load_tasks("scripts/bench/public_benchmark_rlm_harder_v2.json")
        if task.fixture_kind == "rlm_harder_v2_evidence_replay"
    )
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._nexus_task_desc",
        lambda _task: "Use replay_exit_code to solve the hidden case.",
    )

    failures = _prompt_leak_audit_failures([task], repo_root=Path.cwd())

    assert failures == ["prompt_leak:rlm-harder-v2-evidence-002:replay_exit_code"]


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
    assert captured["env"]["NEXUS_FINDINGS_LANCEDB_SYNC"] == "0"
    assert captured["env"]["NEXUS_LEARN_CLOSURE_WRITEBACK"] == "0"
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


def test_run_with_nexus_can_enable_local_swarm_executor_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="swarm-hard",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Exercise swarm executor",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = _cmd
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setenv("NEXUS_ENABLE_SWARM_BENCH_EXECUTOR", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file="target.py",
        test_file="test_target.py",
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
    )

    assert "--task-id" in captured["cmd"]
    assert "swarm-hard" in captured["cmd"]
    assert "target.py" in captured["cmd"]
    assert "test_target.py" in captured["cmd"]
    assert captured["env"]["NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR"] == "1"
    assert "NEXUS_FORCE_INPLACE_EXECUTOR" not in captured["env"]
    assert out["semantic_status"] == "VERIFIED"


def test_run_with_nexus_can_enable_routing_layer_executors(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
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
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
    )

    assert captured["env"]["NEXUS_AUTOREASON_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "0"
    assert out["run_eligible"] is True


def test_run_with_nexus_can_skip_llm_baseline_for_cost_control(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-cost",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug with direct Hyper",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = _cmd
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        skip_llm_baseline=True,
    )

    assert "--llm-mode" in captured["cmd"]
    assert "--llm-baseline" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "hyper_sprint"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert out["run_eligible"] is True


def test_run_with_nexus_can_opt_into_llm_self_heal(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-self-heal",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug",
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

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_llm_self_heal=True,
    )

    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"


def test_run_with_nexus_can_enable_ultra_dry_gate_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-no-llm",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug without llm",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'
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
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
        enable_ultra_review_dry_gate=True,
    )

    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert "NEXUS_AUTOREASON_EXECUTOR" not in captured["env"]
    assert "NEXUS_DDTREE_EXECUTOR" not in captured["env"]
    assert out["run_eligible"] is True


def test_run_with_nexus_can_enable_routing_layer_executors_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-no-llm-executors",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug without llm",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'
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
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
    )

    assert captured["env"]["NEXUS_AUTOREASON_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert out["run_eligible"] is True


def test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-receipts-no-llm",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix evidence-heavy routing bug without llm",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("autoreason", "ddtree", "ultra_review"),
        capability_activation_contract="required",
        hidden_oracle_kind="trace_receipt",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}
    receipts = [
        {
            "name": "autoreason",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": ["candidate-2", "stop_reason:a_streak_met"],
        },
        {
            "name": "ddtree",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": ["saved_steps:2"],
        },
        {
            "name": "ultra_review",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [".nexus/reports/ultra_review/route_gate_report.json"],
        },
    ]
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "pillars": {
                "lancedb": {"active": True},
                "memory": {"active": True},
                "mempalace": {"active": True},
                "belief": {"active": True},
                "artifact": {"active": True},
            },
            "phase_trace": {
                "P": "route_built",
                "X": "retrieval_checked",
                "D": "guard_decision",
                "R": "hyper_executed",
                "A": "artifact_verified",
                "C": "closure_written",
            },
            "capabilities": {"claim_verified": True},
            "capability_receipts": receipts,
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
        },
    }

    class _Proc:
        stdout = json.dumps(payload)
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
    )

    assert captured["cmd"][:4] == ["uv", "run", "scripts/engine/nexus_cli.py", "nexus"]
    assert "--output-json" in captured["cmd"]
    assert captured["env"]["NEXUS_AUTOREASON_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert out["capability_receipts"] == receipts
    assert json.loads(out["capability_receipts_json"]) == receipts
    assert out["expected_capabilities"] == ["autoreason", "ddtree", "ultra_review"]
    assert out["capability_activation_contract"] == "required"
    assert out["hidden_oracle_kind"] == "trace_receipt"
    assert out["expected_capability_receipt_coverage"] == {
        "expected": ["autoreason", "ddtree", "ultra_review"],
        "public_safe": ["autoreason", "ddtree", "ultra_review"],
        "missing": [],
        "failure_reasons": {},
        "all_public_safe": True,
    }
    receipt_by_name = {item["name"]: item for item in out["capability_receipts"]}
    assert receipt_by_name["autoreason"]["public_claim_safe"] is True
    assert receipt_by_name["ddtree"]["public_claim_safe"] is True
    assert receipt_by_name["ultra_review"]["public_claim_safe"] is True


def test_run_with_nexus_llm_all_keeps_auto_route_when_force_flow_is_unset(tmp_path: Path, monkeypatch):
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

    assert "--llm-mode" in captured["cmd"]
    assert "--llm-baseline" in captured["cmd"]
    assert "--force-flow" not in captured["cmd"]


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


def test_run_without_nexus_codex_mode_uses_direct_codex_baseline(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-codex-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_codex_patch(*, prompt, timeout_sec):
        assert "Codex running without Nexus orchestration" in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 0,
                "token_capture_status": "missing_gateway_stats",
                "model_name": "gpt-5.5",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_codex_patch", fake_ask_direct_codex_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="codex",
    )
    assert out["status"] == "SUCCESS"
    assert out["provider"] == "codex"
    assert out["model_name"] == "gpt-5.5"
    assert out["run_eligible"] is True
    assert out["model_response_received"] is True
    assert out["token_reliable"] is False
    assert out["token_unreliable_reason"] == "estimated_tokens"
    assert out["runtime_classification"] == "direct_codex"


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
        assert "test_applies_unique_happy_path_events" in prompt
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
        assert "test_accepts_supported_passing_claim" in prompt
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


def test_rlm_harder_fixture_materializes_visible_and_hidden_tests(tmp_path: Path):
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

    _target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    hidden_test_file = _hidden_test_for_visible_test(visible_test_file)

    visible = Path(visible_test_file).read_text(encoding="utf-8")
    hidden = Path(hidden_test_file).read_text(encoding="utf-8")
    assert Path(visible_test_file).name == "test_visible.py"
    assert Path(hidden_test_file).name == "test_hidden.py"
    assert "test_requires_artifact_reference" in visible
    assert "test_rejects_empty_and_non_string_artifacts" in hidden
    assert "test_rejects_empty_and_non_string_artifacts" not in visible


def test_hidden_verifier_uses_hidden_test_for_final_bare_gate(tmp_path: Path, monkeypatch):
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
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_cmds: list[list[str]] = []

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "test_requires_artifact_reference" in prompt
        assert "test_rejects_empty_and_non_string_artifacts" not in prompt
        patch = (
            "def rlm_harder_v2_verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass' and claim.get('artifact')]\n"
        )
        return (
            {
                "patch": patch,
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            "",
        )

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured_cmds.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert captured_cmds
    assert captured_cmds[-1][-1].endswith("test_hidden.py")


def test_hidden_verifier_overrides_successful_nexus_row(tmp_path: Path, monkeypatch):
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
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_cmds: list[list[str]] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured_cmds.append(list(cmd))
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            payload = {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "result": {"elapsed_sec": 0.1},
                "report": {"model_calls": 0, "total_tokens": 0},
            }
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="hidden failed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
    )

    assert captured_cmds
    assert captured_cmds[-1][-1].endswith("test_hidden.py")
    assert out["status"] == "FAILED"
    assert out["semantic_status"] == "UNVERIFIED"
    assert out["semantic_completed"] is False
    assert out["hidden_verifier_passed"] is False
    assert out["report_trust_mismatch"] is True


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


def test_direct_gemini_timeout_cap_defaults_to_180(monkeypatch):
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_TIMEOUT_SEC", raising=False)
    assert _direct_gemini_timeout_sec(420) == 180
    assert _direct_gemini_timeout_sec(60) == 60


def test_direct_codex_timeout_cap_defaults_to_180(monkeypatch):
    monkeypatch.delenv("NEXUS_DIRECT_CODEX_TIMEOUT_SEC", raising=False)
    assert _direct_codex_timeout_sec(420) == 180
    assert _direct_codex_timeout_sec(60) == 60


def test_extract_codex_stdout_tokens_reads_cli_footer():
    assert _extract_codex_stdout_tokens("done\ntokens used\n17,263\n") == 17263
    assert _extract_codex_stdout_tokens("no token footer") == 0


def test_direct_codex_patch_uses_read_only_exec(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["cmd"] = cmd
        last_path = Path(cmd[cmd.index("--output-last-message") + 1])
        last_path.write_text('{"status":"OK","patch":"x = 1\\n"}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n17,263\n", stderr="")

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/codex")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)
    monkeypatch.setenv("NEXUS_CODEX_EXEC_CWD", str(tmp_path))

    out, _ = _ask_direct_codex_patch(prompt="fix", timeout_sec=7)

    cmd = captured["cmd"]
    assert "--sandbox" in cmd
    assert "read-only" in cmd
    assert out["patch"] == "x = 1\n"
    assert out["model_patch_generated"] is True
    assert out["tokens_used"] == 17263
    assert out["token_capture_status"] == "measured"


def test_direct_gemini_returned_timeout_is_infra_invalid(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="timeout-return-001",
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
        return (
            {
                "status": "FAIL",
                "error_category": "timeout",
                "tokens_used": 0,
                "model_name": "gemini-3-flash-preview",
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

    assert out["baseline_gateway_error_category"] == "timeout"
    assert out["model_calls"] == 0
    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "timeout_before_model_call"


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
        {
            "mode": "with_nexus",
            "run_eligible": True,
            "status": "FAILED",
            "semantic_completed": False,
            "report_trust_mismatch": True,
            "wall_duration_sec": 4.0,
            "phase_wall_total_sec": 1.5,
            "cli_uninstrumented_sec": 2.0,
            "runner_overhead_sec": 0.5,
            "total_tokens": 200,
            "model_calls": 2,
        },
    ]

    summary = _summarize_benchmark_rows(rows)

    assert summary["without_nexus"]["total_n"] == 2
    assert summary["without_nexus"]["eligible_n"] == 1
    assert summary["without_nexus"]["infra_invalid_n"] == 1
    assert summary["without_nexus"]["solve_rate"] == 1.0
    assert summary["with_nexus"]["solve_rate"] == 0.0
    assert summary["with_nexus"]["avg_phase_wall_total_sec"] == 1.5
    assert summary["with_nexus"]["avg_cli_uninstrumented_sec"] == 2.0
    assert summary["with_nexus"]["avg_runner_overhead_sec"] == 0.5


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
