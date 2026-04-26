from pathlib import Path

from scripts.bench.real_world_eval import compare
from scripts.bench import real_world_task_runner
from scripts.bench.real_world_task_runner import load_tasks, run_task


def test_real_world_task_loader_reads_default_schema():
    tasks = load_tasks("scripts/bench/real_world_tasks_v1.json")

    assert len(tasks) >= 5
    assert {task.category for task in tasks} >= {
        "ambiguous_bug_report",
        "multi_file_refactor",
        "missing_test_bugfix",
        "dirty_worktree_guard",
        "flaky_or_timeout_diagnosis",
        "nightshift_needed_cross_module",
    }


def test_real_world_task_type_mapping_matches_benchmark_intent():
    tasks = {task.fixture_kind: task for task in load_tasks("scripts/bench/real_world_tasks_v1.json")}

    assert real_world_task_runner._task_type_for_task(tasks["pricing_refactor"]) == "refactor"
    assert real_world_task_runner._task_type_for_task(tasks["nightshift_escalation"]) == "cross_module_refactor_nightshift"
    assert real_world_task_runner._task_type_for_task(tasks["flag_normalization"]) == "bug"


def test_real_world_runner_preserves_dirty_user_file_with_nexus(tmp_path: Path):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "dirty_slug")

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0)

    assert row["verified_solve"] is True
    assert row["semantic_verified"] is True
    assert row["unrelated_change"] is False
    assert row["rollback_safe"] is True


def test_real_world_prompt_does_not_leak_oracle_root_cause_or_hidden_tests(tmp_path: Path):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "missing_test_retry")
    case_dir, _, _ = real_world_task_runner.materialize_fixture(tmp_path, task)

    prompt = real_world_task_runner._build_gemini_prompt(task, case_dir, mode="with_nexus", nexus_profile="five_pillar")

    assert task.expected_root_cause not in prompt
    assert "test_retry_hidden.py" not in prompt
    assert "test_exponential_regression" not in prompt


def test_real_world_five_pillar_profile_exposes_capability_coverage(tmp_path: Path):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "dirty_slug")

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, nexus_profile="five_pillar")

    assert row["nexus_profile"] == "five_pillar"
    assert set(row["nexus_capability_coverage"]) >= {
        "memory_prior",
        "lancedb_tactical_case",
        "mempalace_gate",
        "belief_hypothesis",
        "artifact_validation",
    }
    assert row["phase_trace"] == [
        "S:spec_bind",
        "P:memory_prior",
        "X:tactical_retrieve",
        "D:policy_gate",
        "R:belief_repair",
        "A:artifact_verify",
        "C:lesson_crystal",
    ]


def test_real_world_core_profile_does_not_overclaim_full_nexus(tmp_path: Path):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "dirty_slug")

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, nexus_profile="core")

    assert row["nexus_profile"] == "core"
    assert "lancedb_tactical_case" not in row["nexus_capability_coverage"]
    assert row["phase_trace"] == ["A:artifact_verify", "C:semantic_closeout"]


def test_real_world_full_nexus_executor_records_cli_report_fields(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "flag_normalization")

    def fake_full_nexus_patch(case_dir, task, *, timeout_sec, model, force_flow=None, candidate_count=1):
        real_world_task_runner._write(
            case_dir / "app" / "flags.py",
            "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n",
        )
        return {
            "regression_test_added": False,
            "unrelated_change": False,
            "root_cause": "flag normalization misses strip lower conversion",
            "written_files": ["app/flags.py"],
            "model_calls": 1,
            "total_tokens": 456,
            "token_capture_status": "measured",
            "gemini_returncode": 0,
            "nexus_report": str(case_dir / ".nexus/reports/research/real_world_auto_flow.json"),
            "nexus_payload": {
                "semantic_status": "VERIFIED",
                "chosen_flow": "hyper_sprint",
                "strategy": {"path": "forced_hyper_direct"},
            },
            "error": "",
        }

    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_patch", fake_full_nexus_patch)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="full_nexus")

    assert row["verified_solve"] is True
    assert row["semantic_verified"] is True
    assert row["nexus_semantic_status"] == "VERIFIED"
    assert row["nexus_chosen_flow"] == "hyper_sprint"
    assert row["nexus_strategy_path"] == "forced_hyper_direct"


def test_real_world_full_nexus_defaults_to_auto_route_not_forced_hyper(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "flag_normalization")
    captured = {}

    def fake_full_nexus_patch(case_dir, task, *, timeout_sec, model, force_flow=None, candidate_count=1):
        captured["force_flow"] = force_flow
        captured["candidate_count"] = candidate_count
        real_world_task_runner._write(
            case_dir / "app" / "flags.py",
            "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n",
        )
        return {
            "regression_test_added": False,
            "unrelated_change": False,
            "root_cause": "flag normalization misses strip lower conversion",
            "written_files": ["app/flags.py"],
            "model_calls": 0,
            "total_tokens": 0,
            "token_capture_status": "not_applicable_local_only",
            "gemini_returncode": 0,
            "nexus_report": str(case_dir / ".nexus/reports/research/real_world_auto_flow.json"),
            "nexus_payload": {
                "semantic_status": "VERIFIED",
                "chosen_flow": "baseline",
                "strategy": {"path": "baseline_only"},
            },
            "error": "",
        }

    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_patch", fake_full_nexus_patch)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="full_nexus")

    assert captured == {"force_flow": None, "candidate_count": 1}
    assert row["nexus_chosen_flow"] == "baseline"


def test_real_world_full_nexus_records_learn_and_nightshift_chain(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "flag_normalization")

    def fake_learn_chain(case_dir, task, *, timeout_sec):
        return {
            "topic": f"real-world::{task.id}",
            "semantic_status": "VERIFIED",
            "converged": True,
            "claims_count": 4,
        }

    def fake_auto_flow(case_dir, task, *, timeout_sec, model, force_flow=None, candidate_count=1):
        real_world_task_runner._write(
            case_dir / "app" / "flags.py",
            "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n",
        )
        return (
            {
                "semantic_status": "VERIFIED",
                "chosen_flow": "hyper_sprint",
                "guard": {"nightshift_recommended": True},
                "result": {
                    "status": "FAILED",
                    "error": "stage1_no_passing_candidate",
                    "report": {"model_calls": 1, "total_tokens": 222, "token_capture_status": "measured"},
                },
                "strategy": {"path": "probe_then_hyper"},
                "_runner_returncode": 0,
            },
            case_dir / ".nexus/reports/research/real_world_auto_flow.json",
        )

    def fake_nightshift(case_dir, task, *, timeout_sec, model):
        real_world_task_runner._write(
            case_dir / "app" / "flags.py",
            "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n",
        )
        return {
            "invoked": True,
            "status": "SUCCESS",
            "report_file": str(case_dir / ".nexus/reports/nightshift.json"),
        }

    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_learn_chain", fake_learn_chain)
    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_auto_flow_patch", fake_auto_flow)
    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_nightshift_patch", fake_nightshift)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="full_nexus")

    assert row["nexus_runtime_chain"] == ["learn:ingest", "learn:converge", "research:auto-flow", "nightshift"]
    assert row["nexus_learn_semantic_status"] == "VERIFIED"
    assert row["nexus_learn_converged"] is True
    assert row["nexus_stage1_failed_reason"] == ""
    assert row["nexus_rejection_summary"] == {}
    assert row["nexus_nightshift_entry_reason"] == "stage1_no_passing_candidate"
    assert row["nexus_nightshift_invoked"] is True
    assert row["nexus_nightshift_status"] == "SUCCESS"
    assert row["nexus_compare_status"] == "VERIFIED"


def test_real_world_full_nexus_timeout_still_emits_compareable_chain(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "nightshift_escalation")

    def fake_learn_chain(case_dir, task, *, timeout_sec):
        return {
            "topic": f"real-world::{task.id}",
            "semantic_status": "VERIFIED",
            "converged": False,
            "claims_count": 1,
        }

    def fake_auto_flow(case_dir, task, *, timeout_sec, model, force_flow=None, candidate_count=1):
        return (
            {
                "_runner_timeout": True,
                "_runner_error": "research_auto_flow_timeout:simulated",
                "_runner_returncode": None,
                "chosen_flow": "hyper_sprint",
            },
            case_dir / ".nexus/reports/research/real_world_auto_flow.json",
        )

    def fake_nightshift(case_dir, task, *, timeout_sec, model):
        return {
            "invoked": True,
            "status": "TIMEOUT",
            "report_file": str(case_dir / ".nexus/reports/nightshift_timeout.json"),
            "error": "nightshift_timeout:simulated",
        }

    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_learn_chain", fake_learn_chain)
    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_auto_flow_patch", fake_auto_flow)
    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_nightshift_patch", fake_nightshift)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="full_nexus")

    assert row["nexus_runtime_chain"] == ["learn:ingest", "learn:converge", "research:auto-flow", "nightshift"]
    assert row["nexus_learn_topic"] == "real-world::rw-nightshift-001"
    assert row["nexus_compare_status"] == "VERIFIED"
    assert row["nexus_compare_failures"] == []


def test_real_world_full_nexus_hyper_success_counts_as_heavy_path_observation(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "nightshift_escalation")

    def fake_full_nexus_patch(case_dir, task, *, timeout_sec, model, force_flow=None, candidate_count=1):
        real_world_task_runner._write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'nightshift' if stage1_signal or stage1_failures >= 2 else 'hyper_sprint'\n"
            "    return persist_state({'mode': mode, 'stage1_signal': stage1_signal, 'trigger_reason': 'stage1_no_passing_candidate' if stage1_signal else ''})\n",
        )
        real_world_task_runner._write(
            case_dir / "state" / "store.py",
            "def persist_state(state: dict) -> dict:\n"
            "    return {'mode': state['mode'], 'trigger_reason': state.get('trigger_reason', '')}\n",
        )
        return {
            "regression_test_added": False,
            "unrelated_change": False,
            "root_cause": task.expected_root_cause,
            "written_files": ["orchestrator/runner.py", "state/store.py"],
            "model_calls": 0,
            "total_tokens": 0,
            "token_capture_status": "not_applicable_local_only",
            "gemini_returncode": 0,
            "nexus_report": str(case_dir / ".nexus/reports/research/real_world_auto_flow.json"),
            "nexus_payload": {
                "semantic_status": "VERIFIED",
                "chosen_flow": "hyper_sprint",
                "result": {
                    "status": "SUCCESS",
                    "report": {"reason": "dayshift_skipped_due_learn_slo_guard"},
                },
                "strategy": {"path": "hyper_direct_hard_skip_probe"},
            },
            "learn_info": {
                "topic": f"real-world::{task.id}",
                "semantic_status": "VERIFIED",
                "converged": False,
                "claims_count": 5,
            },
            "nightshift_info": {"invoked": False},
            "runtime_chain": ["learn:ingest", "learn:converge", "research:auto-flow"],
            "error": "",
        }

    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_patch", fake_full_nexus_patch)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="full_nexus")

    assert row["verified_solve"] is True
    assert row["nexus_compare_status"] == "VERIFIED"
    assert row["nexus_compare_failures"] == []
    assert row["nexus_stage1_failed_reason"] == ""


def test_real_world_task_schema_includes_nightshift_only_fixture():
    tasks = load_tasks("scripts/bench/real_world_tasks_v1.json")
    task = next(task for task in tasks if task.id == "rw-nightshift-002")
    assert task.fixture_kind == "nightshift_audit_bridge"


def test_real_world_full_nexus_exposes_nightshift_report_contract(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "nightshift_audit_bridge")

    def fake_full_nexus_patch(case_dir, task, *, timeout_sec, model, force_flow=None, candidate_count=1):
        real_world_task_runner._write(
            case_dir / "orchestrator" / "runner.py",
            "from state.store import persist_state\n"
            "from state.audit_bridge import build_audit_payload\n\n"
            "def execute(stage1_failures: int, stage1_signal: bool) -> dict:\n"
            "    mode = 'nightshift' if stage1_signal or stage1_failures >= 2 else 'hyper_sprint'\n"
            "    return persist_state({'mode': mode, **build_audit_payload(stage1_signal)})\n",
        )
        real_world_task_runner._write(
            case_dir / "state" / "store.py",
            "def persist_state(state: dict) -> dict:\n"
            "    return {'mode': state['mode'], 'trigger_reason': state.get('trigger_reason', ''), 'audit_tag': state.get('audit_tag', '')}\n",
        )
        real_world_task_runner._write(
            case_dir / "state" / "audit_bridge.py",
            "def build_audit_payload(stage1_signal: bool) -> dict:\n"
            "    return {'trigger_reason': 'stage1_no_passing_candidate' if stage1_signal else '', 'audit_tag': 'nightshift_repair' if stage1_signal else ''}\n",
        )
        return {
            "regression_test_added": False,
            "unrelated_change": False,
            "root_cause": task.expected_root_cause,
            "written_files": ["orchestrator/runner.py", "state/store.py", "state/audit_bridge.py"],
            "model_calls": 0,
            "total_tokens": 0,
            "token_capture_status": "not_applicable_local_only",
            "gemini_returncode": 0,
            "nexus_report": str(case_dir / ".nexus/reports/research/real_world_auto_flow.json"),
            "nexus_payload": {
                "semantic_status": "VERIFIED",
                "chosen_flow": "hyper_sprint",
                "result": {"status": "FAILED", "error": "stage1_no_passing_candidate", "report": {"rejection_summary": {"stage1_failed": 1}}},
                "strategy": {"path": "hyper_then_nightshift"},
            },
            "learn_info": {"topic": f"real-world::{task.id}", "semantic_status": "VERIFIED", "converged": False, "claims_count": 4},
            "nightshift_info": {
                "invoked": True,
                "status": "SUCCESS",
                "report_file": str(case_dir / ".nexus/reports/nightshift_test.json"),
                "payload": {"terminal_state": "SUCCESS"},
                "rounds_attempted": 2,
                "best_score": 1.0,
                "artifact_paths": ["trace.jsonl", "lesson.json"],
            },
            "runtime_chain": ["learn:ingest", "learn:converge", "research:auto-flow", "nightshift"],
            "error": "",
        }

    monkeypatch.setattr(real_world_task_runner, "_run_full_nexus_patch", fake_full_nexus_patch)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="full_nexus")

    assert row["nexus_nightshift_invoked"] is True
    assert row["nexus_nightshift_rounds"] == 2
    assert row["nexus_nightshift_best_score"] == 1.0
    assert row["nexus_nightshift_artifact_paths"] == ["trace.jsonl", "lesson.json"]
    assert row["semantic_verified"] is True
    assert row["root_cause_accurate"] is True


def test_real_world_eval_quantifies_nexus_advantage():
    with_rows = [
        {
            "verified_solve": True,
            "semantic_verified": True,
            "root_cause_accurate": True,
            "regression_test_added": True,
            "unrelated_change": False,
            "trust_mismatch": False,
            "rollback_safe": True,
            "learning_reused": True,
            "duration_sec": 1.0,
            "total_tokens": 0,
        }
        for _ in range(5)
    ]
    without_rows = [
        {
            "verified_solve": idx < 3,
            "semantic_verified": False,
            "root_cause_accurate": idx < 2,
            "regression_test_added": False,
            "unrelated_change": idx == 3,
            "trust_mismatch": True,
            "rollback_safe": idx != 3,
            "learning_reused": False,
            "duration_sec": 1.0,
            "total_tokens": 0,
        }
        for idx in range(5)
    ]

    out = compare(with_rows, without_rows)

    assert out["delta"]["verified_solve_rate_delta"] == 0.4
    assert out["delta"]["semantic_verified_rate_delta"] == 1.0
    assert out["delta"]["trust_mismatch_rate_delta"] == 1.0
    assert out["nexus_realism_grade"] == "REALISM_S10"
    assert out["with_nexus"]["compare_verified_rate"] == 0.0


def test_real_world_gemini_executor_uses_artifacts_not_claims(tmp_path: Path, monkeypatch):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "flag_normalization")

    def fake_gemini_patch(case_dir, task, *, mode, timeout_sec, model, nexus_profile="core"):
        real_world_task_runner._write(
            case_dir / "app" / "flags.py",
            "def normalize_flag(value: str) -> str:\n    return value.strip().lower()\n",
        )
        return {
            "regression_test_added": False,
            "unrelated_change": False,
            "root_cause": "flag normalization misses strip lower conversion",
            "written_files": ["app/flags.py"],
            "model_calls": 1,
            "total_tokens": 123,
            "token_capture_status": "measured",
            "gemini_returncode": 0,
            "error": "",
        }

    monkeypatch.setattr(real_world_task_runner, "_run_gemini_patch", fake_gemini_patch)

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0, executor="gemini")

    assert row["verified_solve"] is True
    assert row["semantic_verified"] is True
    assert row["model_calls"] == 1
    assert row["total_tokens"] == 123


def test_real_world_gemini_edit_parser_blocks_outside_paths(tmp_path: Path):
    payload = {
        "files": [
            {"path": "app/flags.py", "content": "def normalize_flag(value):\n    return value\n"},
            {"path": "../escape.py", "content": "bad = True"},
        ]
    }

    written = real_world_task_runner._apply_gemini_file_edits(tmp_path, payload)

    assert written == ["app/flags.py"]
    assert (tmp_path / "app" / "flags.py").exists()
    assert not (tmp_path.parent / "escape.py").exists()


def test_real_world_root_cause_matcher_accepts_semantic_equivalents():
    assert real_world_task_runner._root_cause_matches(
        "The limit parameter was ignored, leading to an infinite loop if the condition never met.",
        "polling helper uses unbounded sleep loop",
        fixture_kind="timeout_polling",
    )
    assert real_world_task_runner._root_cause_matches(
        "The function was hardcoded to return 1 instead of exponential growth.",
        "retry backoff lacks exponential cap regression coverage",
        fixture_kind="missing_test_retry",
    )


def test_real_world_nightshift_fixture_requires_cross_module_persistence(tmp_path: Path):
    task = next(task for task in load_tasks("scripts/bench/real_world_tasks_v1.json") if task.fixture_kind == "nightshift_escalation")

    row = run_task(task, mode="with_nexus", root=tmp_path, timeout_sec=30, index=0)

    assert row["verified_solve"] is True
    assert row["semantic_verified"] is True
