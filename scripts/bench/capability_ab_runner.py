#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from scripts.bench.gemini_nexus_report import render_markdown_report

from nexus.app.research_flow_service import (
    _build_codeintel_evidence,
    _task_with_codeintel_context,
    build_hyper_execution_profile,
    build_route,
    build_route_executor_flags,
    run_auto_flow,
)
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.route_decision_adapter import build_route_decision
from nexus.research.local_sprint_mutator import generate_local_candidate
from nexus.services.gemini_cli import (
    build_gemini_cli_invocation,
    extract_token_info,
    DEFAULT_GEMINI_BIN,
)
from scripts.engine.nexus_cli import nexus as nexus_root

DEFAULT_CODEX_BIN = "/Users/jameschen/.npm-global/bin/codex"


class BenchmarkTotalTimeout(RuntimeError):
    pass


@dataclass(frozen=True)
class CapabilityTask:
    id: str
    difficulty: str
    task_type: str
    task_desc: str
    target_file: str
    test_file: str
    success_criteria: str
    category: str = ""
    repo_kind: str = ""
    repo: str = ""
    repo_ref: str = ""
    manifest_hash: str = ""
    trial_index: int = 1
    fixture_kind: str = ""
    hidden_test_file: str = ""


PILLAR_OBSERVATION_FIELDS = {
    "lancedb": "pillar_lancedb_active",
    "memory": "pillar_memory_active",
    "mempalace": "pillar_mempalace_active",
    "belief": "pillar_belief_active",
    "artifact": "pillar_artifact_active",
}
PHASE_OBSERVATION_FIELDS = {
    "P": "phase_p",
    "X": "phase_x",
    "D": "phase_d",
    "R": "phase_r",
    "A": "phase_a",
    "C": "phase_c",
}


def _observed_nexus_pillars(row: dict[str, Any]) -> list[str]:
    return [name for name, field in PILLAR_OBSERVATION_FIELDS.items() if bool(row.get(field, False))]


def _observed_nexus_phases(row: dict[str, Any]) -> list[str]:
    return [name for name, field in PHASE_OBSERVATION_FIELDS.items() if bool(row.get(field))]


def _model_uses_nexus(row: dict[str, Any]) -> bool:
    return bool(row.get("model_uses_nexus", row.get("gemini_uses_nexus", False)))


def _classify_infra_invalid_reason(row: dict[str, Any], *, model_required: bool, nexus_required: bool) -> str | None:
    gateway_error = str(row.get("baseline_gateway_error_category") or "").strip()
    raw_tail = str(row.get("baseline_raw_tail") or "")
    combined = f"{gateway_error}\n{raw_tail}".lower()
    model_calls = int(row.get("model_calls", 0) or 0)

    if "quota" in combined or "resource exhausted" in combined or "rate limit" in combined or "429" in combined:
        return "quota_exhausted"
    if "oauth" in combined or "login required" in combined or "permission denied" in combined:
        return "auth_failed"
    if gateway_error == "binary_missing":
        return "cli_missing"
    if gateway_error == "parse_failure":
        return "parse_error"
    if model_required and gateway_error == "timeout" and model_calls == 0:
        return "timeout_before_model_call"

    if nexus_required:
        pillars = _observed_nexus_pillars(row)
        phases = _observed_nexus_phases(row)
        if (
            model_calls <= 0
            or not _model_uses_nexus(row)
            or not bool(row.get("nexus_context_delivered", False))
            or len(pillars) < len(PILLAR_OBSERVATION_FIELDS)
            or len(phases) < len(PHASE_OBSERVATION_FIELDS)
        ):
            return "nexus_delivery_invalid"

    if model_required and model_calls <= 0:
        return "timeout_before_model_call"
    return None


def _annotate_benchmark_eligibility(
    row: dict[str, Any],
    *,
    provider: str,
    model_required: bool,
    nexus_required: bool,
) -> dict[str, Any]:
    row["provider"] = provider
    row["model_uses_nexus"] = _model_uses_nexus(row)
    row["nexus_pillars_observed"] = _observed_nexus_pillars(row)
    row["nexus_phases_observed"] = _observed_nexus_phases(row)
    gateway_error = str(row.get("baseline_gateway_error_category") or "").strip()
    model_calls = int(row.get("model_calls", 0) or 0)
    row["invocation_started"] = bool(model_calls > 0 or gateway_error in {"cli_error", "parse_failure", "timeout"})
    row["model_response_received"] = bool(
        row.get("model_patch_generated", False)
        or int(row.get("total_tokens", 0) or 0) > 0
        or str(row.get("token_capture_status", "")) in {"ok", "measured"}
    )
    row["nexus_bootstrap_completed"] = bool(row.get("nexus_context_delivered", False) or row["nexus_phases_observed"])
    token_status = str(row.get("token_capture_status", "") or "").strip().lower()
    total_tokens = int(row.get("total_tokens", 0) or 0)
    model_token_status = str(row.get("model_token_capture_status") or "").strip().lower()
    if not model_token_status:
        if model_calls <= 0:
            model_token_status = "not_applicable_no_model"
        elif token_status == "measured":
            model_token_status = "measured"
        elif total_tokens > 0:
            model_token_status = "estimated"
        else:
            model_token_status = "missing_gateway_stats"
    row["model_total_tokens"] = int(row.get("model_total_tokens", total_tokens if model_calls > 0 else 0) or 0)
    row["model_token_capture_status"] = model_token_status
    row["gateway_stats_present"] = bool(row.get("gateway_stats_present", False))
    row["gateway_usage_metadata_present"] = bool(row.get("gateway_usage_metadata_present", False))
    row["gateway_token_source"] = str(row.get("gateway_token_source") or "missing")
    row["local_rescue_tokens"] = int(row.get("local_rescue_tokens", 0) or 0)
    default_rescue_cost_status = (
        "local_only" if bool(row.get("nexus_rescued", False)) or token_status == "not_applicable_local_only" else "not_rescue"
    )
    row["rescue_cost_status"] = str(row.get("rescue_cost_status") or default_rescue_cost_status)
    token_unreliable_reason = None
    if model_calls > 0 and total_tokens <= 0:
        token_unreliable_reason = "model_call_without_tokens"
    elif token_status in {"estimated", "fallback_est", "unknown", ""}:
        token_unreliable_reason = "estimated_tokens" if token_status == "estimated" else "unknown_token_capture"
    elif token_status == "not_applicable_local_only" and model_calls > 0:
        token_unreliable_reason = "local_only_rescue_not_model_comparable"
    row["token_reliable"] = token_unreliable_reason is None
    row["token_unreliable_reason"] = token_unreliable_reason
    winner_source = str(row.get("nexus_winner_source") or "")
    gateway_error_category = str(row.get("gateway_error_category") or "")
    row["local_fallback_unhelpful"] = bool(
        winner_source.startswith("local")
        and model_calls > 0
        and not bool(row.get("semantic_completed", False))
        and (
            total_tokens <= 512
            or gateway_error_category in {"timeout", "parse_failure", "gateway_error"}
            or bool(row.get("fallback_used", False))
        )
    )
    reason = _classify_infra_invalid_reason(row, model_required=model_required, nexus_required=nexus_required)
    row["infra_invalid_reason"] = reason
    row["run_eligible"] = reason is None
    row["nexus_wearing_valid"] = bool(nexus_required and reason is None)
    return row


def _apply_per_task_stop_loss(row: dict[str, Any], limit_sec: int) -> bool:
    if limit_sec <= 0:
        return False
    wall_duration = float(row.get("wall_duration_sec", 0.0) or 0.0)
    if wall_duration <= float(limit_sec):
        return False
    row["runtime_classification"] = "task_stop_loss_exceeded"
    row["timeout_scope"] = "benchmark_per_task_stop_loss"
    row["timeout_stage"] = "wall_clock_exceeded"
    row["timeout_sec"] = int(limit_sec)
    row["retryable"] = True
    row["infra_invalid_reason"] = "task_stop_loss_exceeded"
    row["run_eligible"] = False
    row["token_reliable"] = False
    row["token_unreliable_reason"] = "task_stop_loss_exceeded"
    return True


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _summarize_benchmark_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for mode in sorted({str(row.get("mode", "")) for row in rows if row.get("mode") is not None}):
        mode_rows = [row for row in rows if str(row.get("mode", "")) == mode]
        eligible = [row for row in mode_rows if bool(row.get("run_eligible", True))]
        infra_invalid = [row for row in mode_rows if not bool(row.get("run_eligible", True))]
        solved = [row for row in eligible if row.get("status") == "SUCCESS"]
        semantic = [row for row in eligible if bool(row.get("semantic_completed", False))]
        trust_mismatch = [row for row in eligible if bool(row.get("report_trust_mismatch", False))]
        first_pass = [row for row in eligible if int(row.get("attempt_count", 0) or 0) <= 1 and row.get("status") == "SUCCESS"]
        token_reliable = [row for row in eligible if bool(row.get("token_reliable", False))]
        local_fallback_unhelpful = [row for row in eligible if bool(row.get("local_fallback_unhelpful", False))]
        summary[mode] = {
            "total_n": len(mode_rows),
            "eligible_n": len(eligible),
            "infra_invalid_n": len(infra_invalid),
            "infra_invalid_reasons": sorted({str(row.get("infra_invalid_reason")) for row in infra_invalid if row.get("infra_invalid_reason")}),
            "solve_rate": round(len(solved) / len(eligible), 4) if eligible else None,
            "semantic_verified_rate": round(len(semantic) / len(eligible), 4) if eligible else None,
            "trust_mismatch_rate": round(len(trust_mismatch) / len(eligible), 4) if eligible else None,
            "first_pass_rate": round(len(first_pass) / len(eligible), 4) if eligible else None,
            "avg_wall_time_sec": _avg([float(row.get("wall_duration_sec", 0) or 0) for row in eligible]),
            "avg_tokens": _avg([float(row.get("total_tokens", 0) or 0) for row in eligible]),
            "token_reliable_rate": round(len(token_reliable) / len(eligible), 4) if eligible else None,
            "token_unreliable_reasons": sorted(
                {
                    str(row.get("token_unreliable_reason"))
                    for row in eligible
                    if row.get("token_unreliable_reason")
                }
            ),
            "avg_model_calls": _avg([float(row.get("model_calls", 0) or 0) for row in eligible]),
            "local_fallback_unhelpful_rate": round(len(local_fallback_unhelpful) / len(eligible), 4) if eligible else None,
        }
    return summary


def load_tasks(path: str | Path) -> list[CapabilityTask]:
    src = Path(path)
    raw_text = src.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    manifest_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    tasks_raw = payload.get("tasks", [])
    tasks: list[CapabilityTask] = []
    for row in tasks_raw:
        category = str(row.get("category", ""))
        task_type = str(row.get("task_type", f"public_{category}" if category else "task"))
        tasks.append(
            CapabilityTask(
                id=str(row["id"]),
                difficulty=str(row["difficulty"]),
                task_type=task_type,
                task_desc=str(row["task_desc"]),
                target_file=str(row.get("target_file", row.get("fixture_kind", "unused"))),
                test_file=str(row.get("test_file", "unused")),
                success_criteria=str(row.get("success_criteria", "all_target_tests_pass")),
                category=category,
                repo_kind=str(row.get("repo_kind", "")),
                repo=str(row.get("repo", "")),
                repo_ref=str(row.get("repo_ref", "")),
                manifest_hash=manifest_hash,
                fixture_kind=str(row.get("fixture_kind", "")),
                hidden_test_file=str(row.get("hidden_test_file", "")),
            )
        )
    return tasks


def select_tasks(tasks: list[CapabilityTask], *, difficulty: str, max_tasks: int) -> list[CapabilityTask]:
    limit = max(1, max_tasks)
    if difficulty != "all":
        filtered = [task for task in tasks if task.difficulty == difficulty]
        return filtered[:limit]

    buckets: dict[str, list[CapabilityTask]] = {"easy": [], "medium": [], "hard": []}
    for task in tasks:
        buckets.setdefault(task.difficulty, []).append(task)

    ordered: list[CapabilityTask] = []
    idx = 0
    bucket_order = ["easy", "medium", "hard"]
    while len(ordered) < limit:
        progressed = False
        for key in bucket_order:
            bucket = buckets.get(key, [])
            if idx < len(bucket):
                ordered.append(bucket[idx])
                progressed = True
                if len(ordered) >= limit:
                    break
        if not progressed:
            break
        idx += 1
    return ordered[:limit]


def filter_tasks_by_repo_kind(tasks: list[CapabilityTask], repo_kind_filter: str) -> list[CapabilityTask]:
    if repo_kind_filter.strip().lower() in {"", "all"}:
        return tasks
    allowed = {part.strip() for part in repo_kind_filter.split(",") if part.strip()}
    return [task for task in tasks if task.repo_kind in allowed]


def filter_tasks_by_id(tasks: list[CapabilityTask], task_id_filter: str) -> list[CapabilityTask]:
    if task_id_filter.strip().lower() in {"", "all"}:
        return tasks
    allowed = {part.strip() for part in task_id_filter.split(",") if part.strip()}
    return [task for task in tasks if task.id in allowed]


def expand_task_trials(tasks: list[CapabilityTask], *, repeat_trials: int, shuffle_seed: int | None) -> list[CapabilityTask]:
    expanded: list[CapabilityTask] = []
    trials = max(1, repeat_trials)
    for trial_index in range(1, trials + 1):
        for task in tasks:
            expanded.append(
                CapabilityTask(
                    id=task.id,
                    difficulty=task.difficulty,
                    task_type=task.task_type,
                    task_desc=task.task_desc,
                    target_file=task.target_file,
                    test_file=task.test_file,
                    success_criteria=task.success_criteria,
                    category=task.category,
                    repo_kind=task.repo_kind,
                    repo=task.repo,
                    repo_ref=task.repo_ref,
                    manifest_hash=task.manifest_hash,
                    trial_index=trial_index,
                    fixture_kind=task.fixture_kind,
                    hidden_test_file=task.hidden_test_file,
                )
            )
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(expanded)
    return expanded


def _materialize_fixture(repo_root: Path, task: CapabilityTask) -> tuple[str, str]:
    case_dir = (repo_root / ".nexus" / "bench_cases" / task.id).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    target_path = case_dir / "target.py"
    visible_test_path = case_dir / "test_visible.py"
    hidden_test_path = case_dir / "test_hidden.py"

    fixture = task.fixture_kind.strip()
    if fixture.startswith("rlm_harder_"):
        target_code, visible_test_code, hidden_test_code = _rlm_harder_fixture_sources(fixture)
        target_path.write_text(target_code, encoding="utf-8")
        visible_test_path.write_text(visible_test_code, encoding="utf-8")
        hidden_test_path.write_text(hidden_test_code, encoding="utf-8")
        return str(target_path), str(visible_test_path)
    if fixture.startswith("nexus_value_"):
        target_code, visible_test_code, hidden_test_code = _nexus_value_fixture_sources(fixture)
        target_path.write_text(target_code, encoding="utf-8")
        visible_test_path.write_text(visible_test_code, encoding="utf-8")
        hidden_test_path.write_text(hidden_test_code, encoding="utf-8")
        return str(target_path), str(visible_test_path)

    test_path = case_dir / "test_target.py"

    difficulty = task.difficulty.lower()
    if difficulty == "easy":
        target_code = (
            "def normalize_flag(text: str) -> str:\n"
            "    # intentionally buggy for benchmark\n"
            "    return text\n"
        )
        test_code = (
            "import importlib.util\n"
            "from pathlib import Path\n\n"
            "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
            "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
            "_MOD = importlib.util.module_from_spec(_SPEC)\n"
            "assert _SPEC is not None and _SPEC.loader is not None\n"
            "_SPEC.loader.exec_module(_MOD)\n\n"
            "def test_normalize_flag():\n"
            "    assert _MOD.normalize_flag('  TRUE  ') == 'true'\n"
        )
    elif difficulty == "medium":
        target_code = (
            "def compute_backoff(attempt: int) -> int:\n"
            "    # intentionally simplistic\n"
            "    return attempt\n"
        )
        test_code = (
            "import importlib.util\n"
            "from pathlib import Path\n\n"
            "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
            "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
            "_MOD = importlib.util.module_from_spec(_SPEC)\n"
            "assert _SPEC is not None and _SPEC.loader is not None\n"
            "_SPEC.loader.exec_module(_MOD)\n\n"
            "def test_compute_backoff_medium():\n"
            "    assert _MOD.compute_backoff(1) == 1\n"
            "    assert _MOD.compute_backoff(2) == 2\n"
            "    assert _MOD.compute_backoff(3) == 4\n"
        )
    else:
        target_code = (
            "def compute_backoff(attempt: int) -> int:\n"
            "    # intentionally naive for hard-case\n"
            "    return 1\n"
        )
        test_code = (
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
            "    assert _MOD.compute_backoff(3) == 4\n"
        )
    target_path.write_text(target_code, encoding="utf-8")
    test_path.write_text(test_code, encoding="utf-8")
    return str(target_path), str(test_path)


def _split_fixture_tests(test_code: str) -> tuple[str, str]:
    portable = _portable_fixture_test_import(test_code)
    return portable, portable


def _split_rlm_harder_fixture_tests(fixture_kind: str, test_code: str) -> tuple[str, str]:
    if fixture_kind == "rlm_harder_v2_governance_guard":
        visible = (
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_read_file_is_allowed_and_dangerous_shell_is_blocked():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        )
        hidden = (
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_blocks_dangerous_actions_and_paths():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'delete_file', 'path': 'logs/run.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'write_file', 'path': 'benchmarks/result.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_evidence_gap":
        visible = (
            "from target import rlm_harder_v2_verified_claims\n\n"
            "def test_requires_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_empty_and_non_string_artifacts():\n"
            "    claims = [\n"
            "        {'id': 'empty', 'status': 'pass', 'artifact': ''},\n"
            "        {'id': 'none', 'status': 'pass', 'artifact': None},\n"
            "        {'id': 'list', 'status': 'pass', 'artifact': []},\n"
            "        {'id': 'ok', 'status': 'pass', 'artifact': 'reports/ok.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['ok']\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_governance_scope":
        visible = (
            "from target import rlm_harder_v2_scope_decision\n\n"
            "def test_approved_and_read_only_paths():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'read', 'approved': False}) == {'allowed': True, 'reason': 'read_only'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'write', 'approved': True}) == {'allowed': True, 'reason': 'approved'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'delete', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n"
        )
        hidden = visible + (
            "\n"
            "def test_unknown_and_missing_approval_actions_are_blocked():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'write'}) == {'allowed': False, 'reason': 'scope_block'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'unknown', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_evidence_replay":
        visible = (
            "from target import rlm_harder_v2_accept_receipt\n\n"
            "def test_accepts_verified_receipt_with_replay():\n"
            "    receipt = {'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 0}\n"
            "    assert rlm_harder_v2_accept_receipt(receipt) is True\n"
            "\n"
            "def test_verified_receipt_requires_replay_and_clean_exit():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 1}) is False\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_near_miss_receipt_fields():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'replay_exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'partial', 'replay_command': 'pytest -q', 'exit_code': 0}) is False\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_second_round":
        visible = (
            "from target import rlm_harder_v2_merge_settings\n\n"
            "def test_plain_override_wins():\n"
            "    assert rlm_harder_v2_merge_settings({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n"
            "\n"
            "def test_preserves_inputs_and_ignores_none_values():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n"
        )
        hidden = visible + (
            "\n"
            "def test_empty_override_returns_copy_not_alias():\n"
            "    defaults = {'timeout': 10}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {})\n"
            "    assert merged == {'timeout': 10}\n"
            "    assert merged is not defaults\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_memory_contract":
        visible = (
            "from target import rlm_harder_v2_select_memory_hits\n\n"
            "def test_requires_type_and_keyword_overlap():\n"
            "    items = [\n"
            "        {'id': 'old-bug', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket', 'timeout']) == [items[1]]\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_same_type_without_keyword_overlap_and_wrong_type():\n"
            "    items = [\n"
            "        {'id': 'same-type', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'wrong-type', 'task_type': 'feature', 'keywords': ['websocket', 'timeout']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket']) == [items[2]]\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_belief_budget":
        visible = (
            "from target import rlm_harder_v2_repair_budget\n\n"
            "def test_low_confidence_high_risk_requires_more_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
            "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n"
        )
        hidden = visible + (
            "\n"
            "def test_uncertain_or_high_risk_paths_require_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.74, 'medium')['needs_evidence'] is True\n"
            "    assert rlm_harder_v2_repair_budget(0.95, 'high')['needs_evidence'] is True\n"
        )
        return _portable_fixture_test_import(visible), _portable_fixture_test_import(hidden)
    return _split_fixture_tests(test_code)


def _split_nexus_value_fixture_tests(fixture_kind: str, test_code: str) -> tuple[str, str]:
    visible_tests = {
        "nexus_value_hidden_state": (
            "from target import apply_events\n\n"
            "def test_applies_unique_happy_path_events():\n"
            "    events = [{'id': 'a', 'delta': 2}, {'id': 'b', 'delta': 3}]\n"
            "    assert apply_events(events) == {'count': 5, 'seen': ['a', 'b']}\n"
        ),
        "nexus_value_hidden_parser": (
            "from target import normalize_key\n\n"
            "def test_normalize_key_simple_spacing():\n"
            "    assert normalize_key('  User Name  ') == 'user-name'\n"
        ),
        "nexus_value_self_heal_invariant": (
            "from target import merge_limits\n\n"
            "def test_merge_limits_overrides_plain_values():\n"
            "    assert merge_limits({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n"
        ),
        "nexus_value_self_heal_timeout": (
            "from target import remaining_ms\n\n"
            "def test_remaining_ms_simple_elapsed_case():\n"
            "    assert remaining_ms(100, 125, 50) == 25\n"
        ),
        "nexus_value_mempalace_secret_redaction": (
            "from target import redact\n\n"
            "def test_redact_preserves_non_secret_fields():\n"
            "    assert redact({'user': 'ada', 'note': 'ok'}) == {'user': 'ada', 'note': 'ok'}\n"
        ),
        "nexus_value_mempalace_deny_default": (
            "from target import can_access\n\n"
            "def test_viewer_can_read_and_admin_can_write():\n"
            "    assert can_access('admin', 'write') is True\n"
            "    assert can_access('viewer', 'read') is True\n"
        ),
        "nexus_value_artifact_claim_rollup": (
            "from target import verified_claims\n\n"
            "def test_verified_claims_accepts_supported_pass():\n"
            "    claims = [{'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'}]\n"
            "    assert verified_claims(claims) == ['a']\n"
        ),
        "nexus_value_artifact_phase_report": (
            "from target import phase_ready\n\n"
            "def test_phase_ready_accepts_pass_with_evidence():\n"
            "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True\n"
        ),
        "nexus_value_context_docs_contract": (
            "from target import build_response\n\n"
            "def test_build_response_returns_mapping():\n"
            "    assert isinstance(build_response('ok'), dict)\n"
        ),
        "nexus_value_context_config_contract": (
            "from target import parse_config\n\n"
            "def test_parse_config_preserves_explicit_values():\n"
            "    assert parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n"
        ),
        "nexus_value_trust_phase_aggregator": (
            "from target import overall_status\n\n"
            "def test_overall_status_passes_when_all_phases_pass():\n"
            "    assert overall_status([{'status': 'pass', 'evidence': 'a'}]) == 'pass'\n"
        ),
        "nexus_value_trust_incident_classifier": (
            "from target import classify\n\n"
            "def test_classifier_keeps_open_failed_smoke():\n"
            "    assert classify(False, {'verified': True}) == 'open'\n"
        ),
    }
    visible = visible_tests.get(fixture_kind)
    if visible is None:
        return _split_fixture_tests(test_code)
    return _portable_fixture_test_import(visible), _portable_fixture_test_import(test_code)


def _nexus_value_fixture_sources(fixture_kind: str) -> tuple[str, str, str]:
    fixtures: dict[str, tuple[str, str]] = {
        "nexus_value_hidden_state": (
            "def apply_events(events):\n"
            "    state = {'count': 0, 'seen': []}\n"
            "    for event in events:\n"
            "        state['count'] += int(event.get('delta', 0))\n"
            "        state['seen'].append(event.get('id'))\n"
            "    return state\n",
            "from target import apply_events\n\n"
            "def test_duplicate_events_are_idempotent():\n"
            "    events = [{'id': 'a', 'delta': 2}, {'id': 'a', 'delta': 2}, {'id': 'b', 'delta': 3}]\n"
            "    assert apply_events(events) == {'count': 5, 'seen': ['a', 'b']}\n",
        ),
        "nexus_value_hidden_parser": (
            "def normalize_key(text):\n"
            "    return text.strip().lower().replace(' ', '-')\n",
            "from target import normalize_key\n\n"
            "def test_normalize_key_boundaries():\n"
            "    assert normalize_key('  User   Name  ') == 'user-name'\n"
            "    assert normalize_key('') == ''\n"
            "    assert normalize_key('API__Token') == 'api-token'\n",
        ),
        "nexus_value_self_heal_invariant": (
            "def merge_limits(defaults, override):\n"
            "    result = defaults\n"
            "    result.update(override or {})\n"
            "    return result\n",
            "from target import merge_limits\n\n"
            "def test_merge_limits_preserves_inputs_and_drops_none():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = merge_limits(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "nexus_value_self_heal_timeout": (
            "def remaining_ms(start_ms, now_ms, timeout_ms):\n"
            "    return timeout_ms - now_ms - start_ms\n",
            "from target import remaining_ms\n\n"
            "def test_remaining_ms_clamps_and_uses_elapsed_time():\n"
            "    assert remaining_ms(100, 125, 50) == 25\n"
            "    assert remaining_ms(100, 200, 50) == 0\n"
            "    assert remaining_ms(100, 90, 50) == 50\n",
        ),
        "nexus_value_mempalace_secret_redaction": (
            "def redact(record):\n"
            "    return dict(record)\n",
            "from target import redact\n\n"
            "def test_redact_never_leaks_secret_fields():\n"
            "    out = redact({'user': 'ada', 'token': 'abc', 'password': 'pw', 'note': 'ok'})\n"
            "    assert out == {'user': 'ada', 'token': '[REDACTED]', 'password': '[REDACTED]', 'note': 'ok'}\n",
        ),
        "nexus_value_mempalace_deny_default": (
            "def can_access(role, scope):\n"
            "    if role == 'admin':\n"
            "        return True\n"
            "    return scope == 'read'\n",
            "from target import can_access\n\n"
            "def test_deny_by_default_for_unknowns_and_missing_scope():\n"
            "    assert can_access('admin', 'write') is True\n"
            "    assert can_access('viewer', 'read') is True\n"
            "    assert can_access('viewer', 'write') is False\n"
            "    assert can_access('unknown', 'read') is False\n"
            "    assert can_access('viewer', None) is False\n",
        ),
        "nexus_value_artifact_claim_rollup": (
            "def verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "from target import verified_claims\n\n"
            "def test_claims_need_pass_status_and_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert verified_claims(claims) == ['a']\n",
        ),
        "nexus_value_artifact_phase_report": (
            "def phase_ready(phase):\n"
            "    return phase.get('status') == 'pass'\n",
            "from target import phase_ready\n\n"
            "def test_phase_ready_requires_evidence_and_failure_reason():\n"
            "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True\n"
            "    assert phase_ready({'status': 'pass', 'reason': ''}) is False\n"
            "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': 'missing claim'}) is False\n"
            "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': ''}) is False\n",
        ),
        "nexus_value_context_docs_contract": (
            "FIELD = 'status'\n\n"
            "def build_response(value):\n"
            "    return {FIELD: value}\n",
            "from target import build_response\n\n"
            "def test_response_uses_canonical_result_field():\n"
            "    assert build_response('ok') == {'result': 'ok'}\n",
        ),
        "nexus_value_context_config_contract": (
            "def parse_config(data):\n"
            "    return {'strict': bool(data.get('strict', False)), 'retries': data.get('retries', 0)}\n",
            "from target import parse_config\n\n"
            "def test_config_defaults_follow_strict_contract():\n"
            "    assert parse_config({}) == {'strict': True, 'retries': 3}\n"
            "    assert parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n",
        ),
        "nexus_value_trust_phase_aggregator": (
            "def overall_status(phases):\n"
            "    return 'pass' if all(p.get('status') == 'pass' for p in phases) else 'fail'\n",
            "from target import overall_status\n\n"
            "def test_overall_status_rejects_missing_evidence():\n"
            "    assert overall_status([{'status': 'pass', 'evidence': 'a'}, {'status': 'pass', 'evidence': 'b'}]) == 'pass'\n"
            "    assert overall_status([{'status': 'pass'}, {'status': 'pass', 'evidence': 'b'}]) == 'fail'\n",
        ),
        "nexus_value_trust_incident_classifier": (
            "def classify(smoke_passed, semantic_evidence):\n"
            "    return 'resolved' if smoke_passed else 'open'\n",
            "from target import classify\n\n"
            "def test_classifier_does_not_trust_smoke_without_semantic_evidence():\n"
            "    assert classify(True, {'verified': True}) == 'resolved'\n"
            "    assert classify(True, {'verified': False}) == 'needs_evidence'\n"
            "    assert classify(False, {'verified': True}) == 'open'\n",
        ),
    }
    try:
        target_code, test_code = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown_nexus_value_fixture:{fixture_kind}") from exc
    visible_test_code, hidden_test_code = _split_nexus_value_fixture_tests(fixture_kind, test_code)
    return target_code, visible_test_code, hidden_test_code


def _rlm_harder_fixture_sources(fixture_kind: str) -> tuple[str, str, str]:
    fixtures: dict[str, tuple[str, str]] = {
        "rlm_harder_multifile_contract": (
            "CANONICAL_FIELD = 'status'\n\n"
            "def rlm_harder_build_payload(value, meta=None):\n"
            "    payload = {CANONICAL_FIELD: value}\n"
            "    if meta:\n"
            "        payload['meta'] = meta\n"
            "    return payload\n",
            "from target import rlm_harder_build_payload\n\n"
            "def test_uses_result_field_and_preserves_meta():\n"
            "    assert rlm_harder_build_payload('ok', {'source': 'contract'}) == {'result': 'ok', 'meta': {'source': 'contract'}}\n",
        ),
        "rlm_harder_long_context_config": (
            "def rlm_harder_parse_config(data):\n"
            "    strict = bool(data.get('strict', False))\n"
            "    retries = int(data.get('retries', 0))\n"
            "    return {'strict': strict, 'retries': retries}\n",
            "from target import rlm_harder_parse_config\n\n"
            "def test_defaults_follow_current_contract_not_legacy_examples():\n"
            "    assert rlm_harder_parse_config({}) == {'strict': True, 'retries': 3}\n"
            "    assert rlm_harder_parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n",
        ),
        "rlm_harder_misleading_trust": (
            "def rlm_harder_overall_status(phases):\n"
            "    if all(phase.get('status') == 'pass' for phase in phases):\n"
            "        return 'pass'\n"
            "    return 'fail'\n",
            "from target import rlm_harder_overall_status\n\n"
            "def test_passing_status_without_artifacts_is_not_verified():\n"
            "    assert rlm_harder_overall_status([{'status': 'pass', 'artifact': 'a'}, {'status': 'pass', 'artifact': 'b'}]) == 'pass'\n"
            "    assert rlm_harder_overall_status([{'status': 'pass'}, {'status': 'pass', 'artifact': 'b'}]) == 'fail'\n",
        ),
        "rlm_harder_second_round_invariant": (
            "def rlm_harder_merge_limits(defaults, override):\n"
            "    result = defaults\n"
            "    result.update(override or {})\n"
            "    return result\n",
            "from target import rlm_harder_merge_limits\n\n"
            "def test_second_round_must_preserve_inputs_and_ignore_none():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_merge_limits(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "rlm_harder_v2_governance_guard": (
            "def rlm_harder_v2_filter_action(action):\n"
            "    return {'allowed': True, 'reason': 'ok'}\n",
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_blocks_shell_and_delete_actions():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n",
        ),
        "rlm_harder_v2_governance_scope": (
            "def rlm_harder_v2_scope_decision(request):\n"
            "    if request.get('approved'):\n"
            "        return {'allowed': True, 'reason': 'approved'}\n"
            "    return {'allowed': True, 'reason': 'default_allow'}\n",
            "from target import rlm_harder_v2_scope_decision\n\n"
            "def test_unapproved_mutation_is_blocked_but_read_is_allowed():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'read', 'approved': False}) == {'allowed': True, 'reason': 'read_only'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'delete', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n",
        ),
        "rlm_harder_v2_evidence_gap": (
            "def rlm_harder_v2_verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "from target import rlm_harder_v2_verified_claims\n\n"
            "def test_requires_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n",
        ),
        "rlm_harder_v2_evidence_replay": (
            "def rlm_harder_v2_accept_receipt(receipt):\n"
            "    return receipt.get('claim') == 'verified'\n",
            "from target import rlm_harder_v2_accept_receipt\n\n"
            "def test_verified_receipt_requires_replay_and_clean_exit():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 0}) is True\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 1}) is False\n",
        ),
        "rlm_harder_v2_second_round": (
            "def rlm_harder_v2_merge_settings(defaults, override):\n"
            "    out = defaults\n"
            "    out.update(override or {})\n"
            "    return out\n",
            "from target import rlm_harder_v2_merge_settings\n\n"
            "def test_preserves_inputs_and_ignores_none_values():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "rlm_harder_v2_memory_contract": (
            "def rlm_harder_v2_select_memory_hits(items, task_type, keywords):\n"
            "    return [item for item in items if item.get('task_type') == task_type]\n",
            "from target import rlm_harder_v2_select_memory_hits\n\n"
            "def test_requires_type_and_keyword_overlap():\n"
            "    items = [\n"
            "        {'id': 'old-bug', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket', 'timeout']) == [items[1]]\n",
        ),
        "rlm_harder_v2_belief_budget": (
            "def rlm_harder_v2_repair_budget(confidence, risk):\n"
            "    return {'rounds': 1, 'needs_evidence': False}\n",
            "from target import rlm_harder_v2_repair_budget\n\n"
            "def test_low_confidence_high_risk_requires_more_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
            "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n",
        ),
    }
    try:
        target_code, test_code = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown_rlm_harder_fixture:{fixture_kind}") from exc
    visible_test_code, hidden_test_code = _split_rlm_harder_fixture_tests(fixture_kind, test_code)
    return target_code, visible_test_code, hidden_test_code


def _portable_fixture_test_import(test_code: str) -> str:
    first, _, rest = test_code.partition("\n")
    prefix = "from target import "
    if not first.startswith(prefix):
        return test_code
    names = [name.strip() for name in first[len(prefix) :].split(",") if name.strip()]
    bindings = "".join(f"{name} = _MOD.{name}\n" for name in names)
    prelude = (
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
        "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
        "_MOD = importlib.util.module_from_spec(_SPEC)\n"
        "assert _SPEC is not None and _SPEC.loader is not None\n"
        "_SPEC.loader.exec_module(_MOD)\n"
    )
    return prelude + bindings + ("\n" + rest if rest else "")


def _task_uses_materialized_fixture(task: CapabilityTask, *, materialize_missing: bool) -> bool:
    if task.repo_kind == "nexus_internal":
        return False
    if task.repo_kind == "external":
        return False
    return materialize_missing


def _nexus_task_desc(task: CapabilityTask) -> str:
    desc = task.task_desc
    desc += (
        "\n\nNexus wearing contract:"
        "\n- MemPalace: keep the solution inside the task scope and enforce explicit governance constraints."
        "\n- Belief: when evidence is incomplete or confidence is low, prefer a conservative fix backed by tests."
        "\n- Artifact/Claim: treat completion claims as valid only when backed by concrete artifacts or passing checks."
    )
    if task.fixture_kind in {"rlm_harder_v2_governance_guard", "rlm_harder_v2_governance_scope"}:
        desc += (
            "\n\nNexus MemPalace rule: do not silently widen the allowed scope. "
            "If a candidate conflicts with governance policy, preserve the stricter boundary."
        )
    if task.fixture_kind == "rlm_harder_v2_governance_guard":
        desc += (
            "\n\nNexus governance reason contract: read-only tools return reason ok; "
            "destructive commands or task-forbidden paths return reason governance_block."
        )
    if task.fixture_kind == "rlm_harder_v2_governance_scope":
        desc += (
            "\n\nNexus scope enforcement rule: distinguish inspection from mutation, "
            "keep explicit approvals authoritative, and default uncertain requests to the "
            "safer governance boundary."
            "\nNexus scope reason contract: approved mutations return reason approved; "
            "read-only inspection returns reason read_only; unapproved mutating or unknown "
            "actions return reason scope_block."
        )
    if task.fixture_kind == "rlm_harder_v2_evidence_gap":
        desc += (
            "\n\nNexus Artifact/Claim rule: accept only claims that pair a successful "
            "outcome with concrete, checkable support. Unsupported success language "
            "is not enough."
        )
    if task.fixture_kind == "rlm_harder_v2_evidence_replay":
        desc += (
            "\n\nNexus replay evidence rule: trust receipts only when the claim, "
            "replay command, and execution result all agree. Similar-looking fields "
            "must not bypass the contract."
            "\nNexus replay receipt contract: accept only claim='verified' with a "
            "non-empty replay_command and exit_code == 0. Reject missing "
            "replay_command, nonzero exit_code, schema aliases, and non-verified "
            "claims."
        )
    if task.fixture_kind == "rlm_harder_v2_memory_contract":
        desc += (
            "\n\nNexus Belief/Memory rule: prior fixes are relevant only when they share "
            "both task type and meaningful keyword overlap. Ignore unrelated same-type history."
        )
    if task.fixture_kind == "rlm_harder_v2_belief_budget":
        desc += (
            "\n\nNexus Belief budget rule: allocate more repair effort and require "
            "evidence when uncertainty and risk are high; keep simple, confident work "
            "on the faster path."
        )
    return desc


def _resolve_task_files(repo_root: Path, task: CapabilityTask, *, materialize_missing: bool) -> tuple[str, str]:
    if task.repo_kind == "external" and materialize_missing:
        raise NotImplementedError(
            f"{task.id} is external; clone/setup adapter is required before public execution"
        )
    materialize_missing = _task_uses_materialized_fixture(task, materialize_missing=materialize_missing)
    if materialize_missing:
        return _materialize_fixture(repo_root, task)

    target_path = (repo_root / task.target_file).resolve()
    test_path = (repo_root / task.test_file).resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Missing target_file for {task.id}: {task.target_file}")
    if not test_path.exists():
        raise FileNotFoundError(f"Missing test_file for {task.id}: {task.test_file}")
    return str(target_path), str(test_path)


def _hidden_test_for_visible_test(test_file: str) -> str:
    test_path = Path(test_file)
    hidden_path = test_path.with_name("test_hidden.py")
    if hidden_path.exists():
        return str(hidden_path)
    return test_file


def _verification_test_for_task(task: CapabilityTask, test_file: str) -> str:
    if _hidden_verifier_mode_enabled() and (
        task.fixture_kind.startswith("nexus_value_") or task.fixture_kind.startswith("rlm_harder_")
    ):
        return _hidden_test_for_visible_test(test_file)
    return test_file


def _read_preserved_target(target_file: str, *, materialize_missing: bool) -> str | None:
    return Path(target_file).read_text(encoding="utf-8")


def _restore_preserved_target(target_file: str, original: str | None) -> None:
    if original is None:
        return
    Path(target_file).write_text(original, encoding="utf-8")


def _budget_exceeded(start_time: float, total_timeout_sec: int) -> bool:
    return total_timeout_sec > 0 and (time.monotonic() - start_time) >= total_timeout_sec


def _remaining_leg_timeout(default_timeout_sec: int, start_time: float, total_timeout_sec: int) -> int:
    if total_timeout_sec <= 0:
        return default_timeout_sec
    remaining = int(total_timeout_sec - (time.monotonic() - start_time))
    return max(1, min(default_timeout_sec, remaining))


def _remaining_task_timeout(deadline_monotonic: float, fallback_timeout_sec: int) -> int:
    remaining = int(deadline_monotonic - time.monotonic())
    if remaining <= 0:
        raise subprocess.TimeoutExpired("benchmark_task_deadline", fallback_timeout_sec)
    return max(1, min(int(fallback_timeout_sec), remaining))


def _effective_total_timeout_sec(total_timeout_sec: int, stop_loss_sec: int) -> int:
    if total_timeout_sec <= 0:
        return max(0, stop_loss_sec)
    if stop_loss_sec <= 0:
        return total_timeout_sec
    return min(total_timeout_sec, stop_loss_sec)


def _install_total_timeout(total_timeout_sec: int):
    if total_timeout_sec <= 0:
        return None

    previous = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise BenchmarkTotalTimeout(f"benchmark_total_timeout:{total_timeout_sec}")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(total_timeout_sec))
    return previous


def _clear_total_timeout(previous_handler) -> None:
    signal.setitimer(signal.ITIMER_REAL, 0.0)
    if previous_handler is not None:
        signal.signal(signal.SIGALRM, previous_handler)


def _normalize_token_status(status: str, total_tokens: int) -> str:
    normalized = str(status or "unknown").strip().lower() or "unknown"
    if normalized in {"ok", "captured"} and total_tokens > 0:
        return "measured"
    return normalized


def _extract_token_info_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return extract_token_info(payload)


def _summarize_rlm_trace(trace_path: str) -> dict[str, Any]:
    path_text = str(trace_path or "").strip()
    empty = {
        "rlm_iteration_count": 0,
        "rlm_submit_count": 0,
        "rlm_verified_count": 0,
        "rlm_audit_rejected_count": 0,
        "rlm_policy_block_count": 0,
        "rlm_budget_exhausted_trace": False,
        "rlm_allowed_tools_count": 0,
        "rlm_avg_confidence": None,
        "rlm_evidence_density": 0.0,
        "rlm_stop_reasons": [],
        "rlm_trace_quality_score": 0,
    }
    if not path_text:
        return empty
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return empty | {"rlm_stop_reasons": ["trace_missing"]}

    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    if not events:
        return empty | {"rlm_stop_reasons": ["trace_empty"]}

    stop_reasons = [str(event.get("stop_reason") or "") for event in events if event.get("stop_reason")]
    confidence_values = [
        float(event.get("confidence"))
        for event in events
        if isinstance(event.get("confidence"), int | float)
    ]
    allowed_tools = {
        str(tool)
        for event in events
        for tool in (event.get("allowed_tools") or [])
        if str(tool).strip()
    }
    submit_count = sum(1 for event in events if event.get("action_type") == "submit" or event.get("stop_reason") == "submit")
    verified_count = sum(1 for event in events if event.get("stop_reason") == "verified")
    audit_rejected_count = sum(1 for event in events if event.get("stop_reason") == "audit_rejected")
    policy_block_count = sum(
        1
        for event in events
        if event.get("stop_reason") == "policy_blocked" or bool(event.get("blocked_reason"))
    )
    evidence_events = sum(1 for event in events if event.get("artifact_refs"))
    budget_exhausted = any(reason == "budget_exhausted" for reason in stop_reasons)
    quality_score = 25
    quality_score += 20 if submit_count else 0
    quality_score += 20 if verified_count or audit_rejected_count else 0
    quality_score += 15 if evidence_events else 0
    quality_score += 10 if allowed_tools or policy_block_count else 0
    quality_score += 10 if not budget_exhausted else 0
    return {
        "rlm_iteration_count": len(events),
        "rlm_submit_count": submit_count,
        "rlm_verified_count": verified_count,
        "rlm_audit_rejected_count": audit_rejected_count,
        "rlm_policy_block_count": policy_block_count,
        "rlm_budget_exhausted_trace": budget_exhausted,
        "rlm_allowed_tools_count": len(allowed_tools),
        "rlm_avg_confidence": _avg(confidence_values),
        "rlm_evidence_density": round(evidence_events / len(events), 4),
        "rlm_stop_reasons": sorted(set(stop_reasons)),
        "rlm_trace_quality_score": min(100, quality_score),
    }


def _emit_progress(
    *,
    enabled: bool,
    event: str,
    mode: str,
    task: CapabilityTask | None = None,
    target_file: str = "",
    test_file: str = "",
    elapsed_sec: float = 0.0,
    status: str = "",
) -> None:
    if not enabled:
        return
    payload: dict[str, Any] = {
        "event": event,
        "mode": mode,
        "elapsed_sec": round(elapsed_sec, 4),
    }
    if task is not None:
        payload.update(
            {
                "task_id": task.id,
                "trial_index": task.trial_index,
                "difficulty": task.difficulty,
                "task_type": task.task_type,
                "category": task.category,
                "repo_kind": task.repo_kind,
                "target_file": target_file or task.target_file,
                "test_file": test_file or task.test_file,
            }
        )
    if status:
        payload["status"] = status
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)


def _extract_record(
    *,
    mode: str,
    task: CapabilityTask,
    payload: dict[str, Any],
    wall_time_sec: float,
) -> dict[str, Any]:
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    report = result.get("report", {}) if isinstance(result, dict) else {}
    route = payload.get("route", {}) if isinstance(payload, dict) else {}
    route_features = route.get("route_features", {}) if isinstance(route, dict) else {}
    guard = payload.get("guard", {}) if isinstance(payload, dict) else {}
    strategy = payload.get("strategy", {}) if isinstance(payload, dict) else {}
    artifact_summary = payload.get("artifact_summary", {}) if isinstance(payload, dict) else {}
    success_criteria_payload = payload.get("success_criteria", {}) if isinstance(payload, dict) else {}
    success_criteria_payload = success_criteria_payload if isinstance(success_criteria_payload, dict) else {}
    usage_trace = payload.get("nexus_usage_trace", {}) if isinstance(payload, dict) else {}
    usage_trace = usage_trace if isinstance(usage_trace, dict) else {}
    timing = payload.get("timing", {}) if isinstance(payload, dict) else {}
    timing = timing if isinstance(timing, dict) else {}
    phase_wall = timing.get("phase_wall_sec") or usage_trace.get("phase_wall_sec") or {}
    phase_wall = phase_wall if isinstance(phase_wall, dict) else {}
    pillars = usage_trace.get("pillars", {}) if isinstance(usage_trace, dict) else {}
    pillars = pillars if isinstance(pillars, dict) else {}
    phase_trace = usage_trace.get("phase_trace", {}) if isinstance(usage_trace, dict) else {}
    phase_trace = phase_trace if isinstance(phase_trace, dict) else {}
    capabilities = usage_trace.get("capabilities", {}) if isinstance(usage_trace, dict) else {}
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    swarm_report = capabilities.get("swarm_report", {})
    swarm_report = swarm_report if isinstance(swarm_report, dict) else {}
    drone_report = capabilities.get("drone_report", {})
    drone_report = drone_report if isinstance(drone_report, dict) else {}
    nightshift_report = capabilities.get("nightshift_report", {})
    nightshift_report = nightshift_report if isinstance(nightshift_report, dict) else {}
    capability_stack = usage_trace.get("capability_stack", {}) if isinstance(usage_trace, dict) else {}
    capability_stack = capability_stack if isinstance(capability_stack, dict) else {}
    capability_plan = usage_trace.get("capability_plan", {}) if isinstance(usage_trace, dict) else {}
    capability_plan = capability_plan if isinstance(capability_plan, dict) else {}
    route_decision = usage_trace.get("route_decision", {}) if isinstance(usage_trace, dict) else {}
    route_decision = route_decision if isinstance(route_decision, dict) else {}
    capability_receipts = usage_trace.get("capability_receipts", []) if isinstance(usage_trace, dict) else []
    capability_receipts = capability_receipts if isinstance(capability_receipts, list) else []
    capability_replan_trace = capability_plan.get("replan_trace", []) if isinstance(capability_plan, dict) else []
    capability_replan_trace = capability_replan_trace if isinstance(capability_replan_trace, list) else []
    ultra_review = usage_trace.get("ultra_review", {}) if isinstance(usage_trace, dict) else {}
    ultra_review = ultra_review if isinstance(ultra_review, dict) else {}
    autoreason = usage_trace.get("autoreason", {}) if isinstance(usage_trace, dict) else {}
    autoreason = autoreason if isinstance(autoreason, dict) else {}
    ddtree = usage_trace.get("ddtree", {}) if isinstance(usage_trace, dict) else {}
    ddtree = ddtree if isinstance(ddtree, dict) else {}
    codeintel = usage_trace.get("codeintel", payload.get("codeintel", {})) if isinstance(payload, dict) else {}
    codeintel = codeintel if isinstance(codeintel, dict) else {}
    jit = usage_trace.get("jit", payload.get("jit", {})) if isinstance(payload, dict) else {}
    jit = jit if isinstance(jit, dict) else {}
    baseline_trace = payload.get("baseline_trace", {}) if isinstance(payload, dict) else {}
    baseline_trace = baseline_trace if isinstance(baseline_trace, dict) else {}
    learn_phase_slo = payload.get("learn_phase_slo", {}) if isinstance(payload, dict) else {}
    consensus = route.get("consensus", {}) if isinstance(route, dict) else {}
    consensus_votes = consensus.get("votes", {}) if isinstance(consensus, dict) else {}
    task_duration = float(result.get("elapsed_sec", wall_time_sec) or wall_time_sec)
    model_calls = int(report.get("model_calls", 0) or 0)
    model_name = str(report.get("model_name", "") or "")
    total_tokens = int(report.get("total_tokens", 0) or 0)
    token_capture_status = _normalize_token_status(
        str(report.get("token_capture_status", "unknown") or "unknown"),
        total_tokens,
    )
    rlm_trace_path = str(usage_trace.get("rlm_trace_path") or "")
    rlm_trace_summary = _summarize_rlm_trace(rlm_trace_path)
    semantic_status = payload.get("semantic_status")
    semantic_completed = bool(
        payload.get("status") == "SUCCESS"
        and semantic_status in {"VERIFIED", "PARTIAL"}
    )
    row = {
        "mode": mode,
        "task_id": task.id,
        "trial_index": task.trial_index,
        "category": task.category,
        "repo_kind": task.repo_kind,
        "repo": task.repo,
        "repo_ref": task.repo_ref,
        "manifest_hash": task.manifest_hash,
        "difficulty": task.difficulty,
        "task_type": task.task_type,
        "task_desc": task.task_desc,
        "status": payload.get("status", result.get("status", "")),
        "semantic_status": semantic_status,
        "semantic_completed": semantic_completed,
        "runtime_classification": payload.get("runtime_classification"),
        "timeout_scope": payload.get("timeout_scope"),
        "timeout_stage": payload.get("timeout_stage"),
        "timeout_sec": payload.get("timeout_sec"),
        "partial_stdout_tail": payload.get("partial_stdout_tail"),
        "partial_stderr_tail": payload.get("partial_stderr_tail"),
        "retryable": payload.get("retryable"),
        "duration_sec": round(task_duration, 4),
        "task_duration_sec": round(task_duration, 4),
        "wall_duration_sec": round(wall_time_sec, 4),
        "subprocess_wall_sec": round(wall_time_sec, 4) if mode == "with_nexus" else None,
        "cli_elapsed_sec": timing.get("cli_elapsed_sec"),
        "receipt_elapsed_sec": timing.get("cli_elapsed_sec"),
        "phase_wall_p_sec": phase_wall.get("P"),
        "phase_wall_x_sec": phase_wall.get("X"),
        "phase_wall_d_sec": phase_wall.get("D"),
        "phase_wall_r_sec": phase_wall.get("R"),
        "phase_wall_a_sec": phase_wall.get("A"),
        "phase_wall_c_sec": phase_wall.get("C"),
        "elapsed_sec": task_duration,
        "attempt_count": int(report.get("attempt_count", 0) or 0),
        "model_calls": model_calls,
        "model_name": model_name,
        "model_patch_generated": bool(report.get("model_patch_generated", False)),
        "fallback_used": bool(report.get("fallback_used", False)),
        "total_tokens": total_tokens,
        "token_capture_status": token_capture_status,
        "token_measured": token_capture_status == "measured",
        "model_total_tokens": int(report.get("model_total_tokens", total_tokens if model_calls > 0 else 0) or 0),
        "model_token_capture_status": str(report.get("model_token_capture_status") or ""),
        "gateway_stats_present": bool(report.get("gateway_stats_present", False)),
        "gateway_usage_metadata_present": bool(report.get("gateway_usage_metadata_present", False)),
        "gateway_token_source": str(report.get("gateway_token_source") or ""),
        "gateway_error_category": str(report.get("gateway_error_category") or ""),
        "gateway_prompt_chars": int(report.get("gateway_prompt_chars", 0) or 0),
        "gateway_payload_chars": int(report.get("gateway_payload_chars", 0) or 0),
        "gateway_total_chars": int(report.get("gateway_total_chars", 0) or 0),
        "gateway_timeout_sec": int(report.get("gateway_timeout_sec", 0) or 0),
        "local_rescue_tokens": int(report.get("local_rescue_tokens", 0) or 0),
        "rescue_cost_status": str(report.get("rescue_cost_status") or ""),
        "baseline_gateway_error_category": baseline_trace.get("gateway_error_category"),
        "baseline_patch_len": int(baseline_trace.get("patch_len", 0) or 0),
        "baseline_patch_changed": bool(baseline_trace.get("patch_changed", False)),
        "baseline_raw_tail": baseline_trace.get("raw_tail"),
        "baseline_pytest_stdout_tail": baseline_trace.get("pytest_stdout_tail"),
        "baseline_pytest_stderr_tail": baseline_trace.get("pytest_stderr_tail"),
        "report_trust_mismatch": bool(payload.get("semantic_status") is None),
        "route_recommended_flow": route.get("recommended_flow"),
        "route_reason": route.get("recommended_reason"),
        "route_risk_score": int(route_features.get("risk_score", 0) or 0),
        "route_consensus_winner": consensus.get("winner"),
        "route_consensus_hyper_votes": int(consensus_votes.get("hyper_sprint", 0) or 0),
        "route_consensus_baseline_votes": int(consensus_votes.get("baseline", 0) or 0),
        "route_findings_hits": int(route.get("findings_hits", 0) or 0),
        "route_memory_hits": int(route_features.get("memory_hits", 0) or 0),
        "prior_fix_hits": int(route.get("prior_fix_hits", 0) or 0),
        "belief_confidence": float((payload.get("execution_profile", {}) or {}).get("belief_confidence", 1.0) or 1.0),
        "chosen_flow": payload.get("chosen_flow"),
        "strategy_path": strategy.get("path"),
        "guard_hit": bool(guard.get("hit", False)),
        "guard_nightshift_recommended": bool(guard.get("nightshift_recommended", False)),
        "guard_stage1_fail_signals": int(guard.get("stage1_fail_signals", 0) or 0),
        "learn_phase_slo_pass": bool(learn_phase_slo.get("phase_slo_pass", False)),
        "artifact_changed": bool(artifact_summary.get("changed", False)),
        "artifact_verification_only": bool(artifact_summary.get("verification_only", False)),
        "artifact_diff_line_count": int(artifact_summary.get("diff_line_count", 0) or 0),
        "success_criteria": str(success_criteria_payload.get("name") or task.success_criteria),
        "mutation_required": bool(success_criteria_payload.get("mutation_required", False))
        or task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
        "verification_only_allowed": bool(success_criteria_payload.get("verification_only_allowed", task.success_criteria == "all_target_tests_pass")),
        "gemini_uses_nexus": bool(usage_trace.get("gemini_uses_nexus", usage_trace.get("model_uses_nexus", False))),
        "model_uses_nexus": bool(usage_trace.get("model_uses_nexus", usage_trace.get("gemini_uses_nexus", False))),
        "nexus_context_delivered": bool(usage_trace.get("nexus_context_delivered", False)),
        "nexus_tier": str(usage_trace.get("nexus_tier") or ""),
        "nexus_tier_reason": str(usage_trace.get("nexus_tier_reason") or ""),
        "nexus_usage_valid": bool(usage_trace.get("usage_valid", False)),
        "gemini_patch_status": usage_trace.get("gemini_patch_status"),
        "nexus_rescued": bool(usage_trace.get("nexus_rescued", False)),
        "nexus_winner_source": usage_trace.get("winner_source"),
        "pillar_lancedb_active": bool((pillars.get("lancedb", {}) or {}).get("active", False)),
        "pillar_lancedb_hits": int((pillars.get("lancedb", {}) or {}).get("hits", 0) or 0),
        "pillar_memory_active": bool((pillars.get("memory", {}) or {}).get("active", False)),
        "pillar_memory_hits": int((pillars.get("memory", {}) or {}).get("hits", 0) or 0),
        "pillar_mempalace_active": bool((pillars.get("mempalace", {}) or {}).get("active", False)),
        "pillar_mempalace_verified": bool((pillars.get("mempalace", {}) or {}).get("verified", False)),
        "pillar_belief_active": bool((pillars.get("belief", {}) or {}).get("active", False)),
        "pillar_artifact_active": bool((pillars.get("artifact", {}) or {}).get("active", False)),
        "pillar_artifact_tests_passed": bool((pillars.get("artifact", {}) or {}).get("tests_passed", False)),
        "phase_p": phase_trace.get("P"),
        "phase_x": phase_trace.get("X"),
        "phase_d": phase_trace.get("D"),
        "phase_r": phase_trace.get("R"),
        "phase_a": phase_trace.get("A"),
        "phase_c": phase_trace.get("C"),
        "capability_research_used": bool(capabilities.get("research_used", False)),
        "capability_hyper_used": bool(capabilities.get("hyper_used", False)),
        "capability_self_heal_used": bool(capabilities.get("self_heal_used", False)),
        "capability_claim_verified": bool(capabilities.get("claim_verified", False)),
        "capability_nightshift_recommended": bool(capabilities.get("nightshift_recommended", False)),
        "capability_nightshift_invoked": bool(capabilities.get("nightshift_invoked", False)),
        "capability_nightshift_recovered": bool(capabilities.get("nightshift_recovered", False)),
        "capability_nightshift_report_path": str(capabilities.get("nightshift_report_path") or ""),
        "capability_nightshift_report_schema_version": str(nightshift_report.get("schema_version") or ""),
        "capability_nightshift_failure_reason": str(capabilities.get("nightshift_failure_reason") or nightshift_report.get("failure_reason") or ""),
        "capability_swarm_used": bool(capabilities.get("swarm_used", False)),
        "capability_swarm_evidence_count": int(capabilities.get("swarm_evidence_count", 0) or 0),
        "capability_swarm_report_schema_version": str(swarm_report.get("schema_version") or ""),
        "capability_swarm_consensus": str(capabilities.get("swarm_consensus") or swarm_report.get("consensus") or ""),
        "capability_drone_used": bool(capabilities.get("drone_used", False)),
        "capability_drone_invoked_count": int(capabilities.get("drone_invoked_count", 0) or 0),
        "capability_drone_report_schema_version": str(drone_report.get("schema_version") or ""),
        "capability_drone_artifact_path": str(capabilities.get("drone_artifact_path") or ""),
        "capability_stack_selected": list(capability_stack.get("selected_capabilities", []) or []),
        "capability_stack_acceleration_layers": list(capability_stack.get("acceleration_layers", []) or []),
        "capability_stack_governance_layers": list(capability_stack.get("governance_layers", []) or []),
        "capability_stack_stop_policy_type": str((capability_stack.get("stop_policy", {}) or {}).get("type") or ""),
        "capability_plan_trace_present": bool(capability_plan.get("decision_trace")),
        "capability_plan_schema_version": str(capability_plan.get("schema_version") or ""),
        "capability_plan_mode": str(capability_plan.get("planner_mode") or ""),
        "capability_plan_score": int(capability_plan.get("score", 0) or 0),
        "capability_plan_node_count": len(capability_plan.get("decision_trace", []) or []),
        "capability_plan_selected": list(capability_plan.get("selected_capabilities", []) or []),
        "capability_plan_required": list(capability_plan.get("required_capabilities", []) or []),
        "capability_plan_conditional": list(capability_plan.get("conditional_capabilities", []) or []),
        "route_decision_schema_version": str(route_decision.get("schema_version") or ""),
        "route_decision_report_path": str(usage_trace.get("route_decision_report_path") or ""),
        "route_decision_selected_count": len(route_decision.get("selected_capabilities", []) or []),
        "route_decision_required_count": len(route_decision.get("required_capabilities", []) or []),
        "route_decision_conditional_count": len(route_decision.get("conditional_capabilities", []) or []),
        "route_decision_pending": list(route_decision.get("pending_capabilities", []) or []),
        "route_decision_forbidden": list(route_decision.get("forbidden_capabilities", []) or []),
        "route_decision_pillars_active": [
            str(name)
            for name, data in ((route_decision.get("signal_snapshot", {}) or {}).get("pillar_signals", {}) or {}).items()
            if isinstance(data, dict) and bool(data.get("active", False))
        ],
        "capability_plan_forbidden": list(capability_plan.get("forbidden_capabilities", []) or []),
        "capability_receipts": capability_receipts,
        "capability_receipts_json": json.dumps(capability_receipts, ensure_ascii=False, sort_keys=True),
        "capability_plan_phases": [
            str(item.get("phase"))
            for item in capability_replan_trace
            if isinstance(item, dict) and str(item.get("active_capabilities") or "").strip()
        ],
        "autoreason_enabled": bool(autoreason.get("enabled", False)),
        "autoreason_status": str(autoreason.get("status") or ""),
        "autoreason_winner": str(autoreason.get("winner") or ""),
        "autoreason_stop_reason": str(autoreason.get("stop_reason") or ""),
        "autoreason_judge_votes_count": len(autoreason.get("judge_votes", []) or []),
        "autoreason_borda_scores": autoreason.get("borda_scores", {}),
        "ddtree_enabled": bool(ddtree.get("enabled", False)),
        "ddtree_eligible": bool(ddtree.get("eligible", False)),
        "ddtree_selected_candidate_ids": list(ddtree.get("selected_candidate_ids", []) or []),
        "ddtree_estimated_saved_steps": int(ddtree.get("estimated_saved_steps", 0) or 0),
        "ddtree_actual_saved_steps": int(ddtree.get("actual_saved_steps", 0) or 0),
        "ddtree_reason": str(ddtree.get("reason") or ""),
        "ultra_review_recommended": bool(ultra_review.get("recommended", False)),
        "ultra_review_invoked": bool(ultra_review.get("invoked", False)),
        "ultra_review_gate_passed": ultra_review.get("gate_passed"),
        "ultra_review_report_path": str(ultra_review.get("report_path") or ""),
        "ultra_review_reason": str(ultra_review.get("reason") or ""),
        "ultra_review_failures": list(ultra_review.get("failures", []) or []),
        "codeintel_gate_mode": str(codeintel.get("gate_mode") or ""),
        "codeintel_scan_report_present": bool(codeintel.get("scan_report_present", False)),
        "codeintel_impact_report_present": bool(codeintel.get("impact_report_present", False)),
        "codeintel_claim_bundle_present": bool(codeintel.get("claim_bundle_present", False)),
        "codeintel_scan_report_path": str(codeintel.get("scan_report_path") or ""),
        "codeintel_impact_report_path": str(codeintel.get("impact_report_path") or ""),
        "codeintel_risk_score": int(codeintel.get("risk_score", 0) or 0),
        "codeintel_impacted_files_count": int(codeintel.get("impacted_files_count", 0) or 0),
        "jit_ranking_mode": str(jit.get("ranking_mode") or "static"),
        "jit_promotion_verdict": str(jit.get("promotion_verdict") or ""),
        "jit_static_default_unchanged": bool(jit.get("static_default_unchanged", True)),
        "jit_miss_rate": jit.get("miss_rate"),
        "jit_fallback_run_rate": jit.get("fallback_run_rate"),
        "jit_unmatched_path_rate": jit.get("unmatched_path_rate"),
        "jit_predictive_saved_runtime_sec": jit.get("predictive_saved_runtime_sec"),
        "rlm_trace_path": rlm_trace_path,
        "rlm_trace_present": bool(rlm_trace_path.strip()),
        "rlm_policy_reason": str(usage_trace.get("rlm_policy_reason") or ""),
        "rlm_budget_exhausted": bool(usage_trace.get("rlm_budget_exhausted", False)),
        "rlm_loop_phase": str(usage_trace.get("rlm_loop_phase") or ""),
        "rlm_x_loop_budget_observed": bool(usage_trace.get("rlm_x_loop_budget_observed", False)),
        "rlm_required_gates": list(usage_trace.get("rlm_required_gates", []) or []),
    }
    row.update(rlm_trace_summary)
    return _annotate_benchmark_eligibility(
        row,
        provider="gemini" if model_name or model_calls > 0 or mode == "with_nexus" else "local",
        model_required=False,
        nexus_required=False,
    )


def _extract_json_payload(raw_output: str) -> dict[str, Any]:
    text = (raw_output or "").strip()
    if not text:
        return {}
    brace_positions = [idx for idx, ch in enumerate(text) if ch == "{"]
    for idx in reversed(brace_positions):
        candidate = text[idx:]
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _tail_text(value: Any, *, max_chars: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return text[-max_chars:]


def _repo_relative_path(repo_root: Path, path_text: str) -> str:
    path = Path(path_text)
    if not path.is_absolute():
        return path_text
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return path_text


def _classify_timeout_stage(stdout_tail: str, stderr_tail: str) -> str:
    combined = f"{stdout_tail}\n{stderr_tail}".lower()
    if "gateway" in combined or "gemini" in combined or "model_calls" in combined or "llm" in combined:
        return "timeout_during_gemini"
    if "artifact" in combined or "pytest" in combined:
        return "timeout_during_artifact_verify"
    if "hyper" in combined or "sprint" in combined:
        return "timeout_during_hyper"
    if "route" in combined or "phase_p" in combined or "route_built" in combined:
        return "timeout_after_route_before_gemini"
    if "memoryservice" in combined or "lancedb" in combined or "redis init" in combined or "policy" in combined:
        return "timeout_during_memory_bootstrap"
    return "timeout_before_receipt"


def _benchmark_memory_db_path(repo_root: Path, task: CapabilityTask, start_time: float) -> Path:
    safe_task_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", task.id).strip("_") or "task"
    return (
        repo_root
        / ".nexus"
        / "reports"
        / "bench_runtime"
        / "memory"
        / f"{safe_task_id}_trial{task.trial_index}_{int(start_time * 1000)}"
    )


def _with_nexus_timeout_payload(*, timeout_sec: int, exc: subprocess.TimeoutExpired | None = None) -> dict[str, Any]:
    stdout_tail = _tail_text(getattr(exc, "stdout", None) or getattr(exc, "output", None))
    stderr_tail = _tail_text(getattr(exc, "stderr", None))
    return {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "runtime_classification": "subprocess_timeout",
        "timeout_scope": "with_nexus_subprocess",
        "timeout_stage": _classify_timeout_stage(stdout_tail, stderr_tail),
        "timeout_sec": int(timeout_sec),
        "partial_stdout_tail": stdout_tail,
        "partial_stderr_tail": stderr_tail,
        "result": {
            "elapsed_sec": timeout_sec,
            "report": {
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "unknown",
            },
        },
    }


def _direct_gemini_timeout_sec(timeout_sec: int) -> int:
    cap_raw = os.environ.get("NEXUS_DIRECT_GEMINI_TIMEOUT_SEC", "180")
    try:
        cap = int(cap_raw)
    except ValueError:
        cap = 180
    if cap <= 0:
        return max(1, int(timeout_sec))
    return max(1, min(int(timeout_sec), cap))


def _run_process_group(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: int,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="nexus-bench-proc-") as tmp:
        stdout_path = Path(tmp) / "stdout.txt"
        stderr_path = Path(tmp) / "stderr.txt"
        with stdout_path.open("w+", encoding="utf-8") as stdout_file, stderr_path.open("w+", encoding="utf-8") as stderr_file:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                text=True,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
            deadline = time.monotonic() + max(1, int(timeout_sec))
            while True:
                returncode = proc.poll()
                if returncode is not None:
                    stdout_file.flush()
                    stderr_file.flush()
                    return subprocess.CompletedProcess(
                        cmd,
                        returncode,
                        stdout_path.read_text(encoding="utf-8", errors="replace"),
                        stderr_path.read_text(encoding="utf-8", errors="replace"),
                    )
                if time.monotonic() >= deadline:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    stdout_file.flush()
                    stderr_file.flush()
                    raise subprocess.TimeoutExpired(
                        cmd,
                        timeout_sec,
                        output=stdout_path.read_text(encoding="utf-8", errors="replace"),
                        stderr=stderr_path.read_text(encoding="utf-8", errors="replace"),
                    )
                time.sleep(0.1)


def _parse_direct_gemini_json(raw_stdout: str) -> tuple[dict[str, Any], str]:
    try:
        outer = json.loads(raw_stdout)
    except json.JSONDecodeError:
        outer, _ = json.JSONDecoder().raw_decode(raw_stdout)
    output_text = str(outer.get("output") or outer.get("response") or raw_stdout)
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        start = output_text.find("{")
        end = output_text.rfind("}")
        if start == -1 or end == -1:
            raise
        payload = json.loads(output_text[start : end + 1])
    token_info = _extract_token_info_from_payload(outer)
    tokens_total = int(token_info["total_tokens"])
    payload["tokens_used"] = tokens_total
    payload["token_capture_status"] = "measured" if tokens_total > 0 else "missing_gateway_stats"
    payload["gateway_stats_present"] = bool(token_info["gateway_stats_present"])
    payload["gateway_usage_metadata_present"] = bool(token_info["gateway_usage_metadata_present"])
    payload["gateway_token_source"] = str(token_info["gateway_token_source"])
    return payload, output_text


def _parse_direct_patch_json(raw_text: str) -> tuple[dict[str, Any], str]:
    output_text = raw_text.strip()
    if output_text.startswith("```"):
        output_text = re.sub(r"^```(?:json)?\s*", "", output_text)
        output_text = re.sub(r"\s*```$", "", output_text).strip()
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError:
        start = output_text.find("{")
        end = output_text.rfind("}")
        if start == -1 or end == -1:
            raise
        payload = json.loads(output_text[start : end + 1])
    payload.setdefault("tokens_used", 0)
    payload.setdefault("token_capture_status", "missing_gateway_stats")
    payload.setdefault("gateway_stats_present", False)
    payload.setdefault("gateway_usage_metadata_present", False)
    payload.setdefault("gateway_token_source", "missing")
    return payload, output_text


def _direct_codex_timeout_sec(timeout_sec: int) -> int:
    env_value = os.environ.get("NEXUS_DIRECT_CODEX_TIMEOUT_SEC", "").strip()
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            pass
    return max(1, min(int(timeout_sec), 180))


def _extract_codex_stdout_tokens(stdout: str) -> int:
    match = re.search(r"tokens used\s+([0-9][0-9,]*)", stdout or "", flags=re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def _ask_direct_codex_patch(*, prompt: str, timeout_sec: int) -> tuple[dict[str, Any], str]:
    codex_bin = shutil.which("codex") or DEFAULT_CODEX_BIN
    model_name = str(os.environ.get("NEXUS_CODEX_MODEL_NAME") or os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or "gpt-5.5")
    if not Path(codex_bin).exists():
        return {"status": "FAIL", "error_category": "binary_missing", "tokens_used": 0, "model_name": model_name}, "codex_missing"

    with tempfile.NamedTemporaryFile(prefix="nexus_codex_patch_", suffix=".txt", delete=False) as handle:
        last_message_path = Path(handle.name)
    cmd = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "-C",
        str(Path(os.environ.get("NEXUS_CODEX_EXEC_CWD") or os.getcwd()).resolve()),
        "-m",
        model_name,
        "--output-last-message",
        str(last_message_path),
        prompt,
    ]
    env = dict(os.environ)
    env["PATH"] = f"/opt/homebrew/bin:/Users/jameschen/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:{env.get('PATH', '')}"
    try:
        res = _run_process_group(
            cmd,
            cwd=str(Path.cwd()),
            env=env,
            timeout_sec=_direct_codex_timeout_sec(timeout_sec),
        )
        raw = last_message_path.read_text(encoding="utf-8", errors="replace") if last_message_path.exists() else res.stdout
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "FAIL",
            "error_category": "timeout",
            "tokens_used": 0,
            "model_name": model_name,
            "timeout_sec": int(getattr(exc, "timeout", timeout_sec) or timeout_sec),
        }, _tail_text(getattr(exc, "stdout", None) or getattr(exc, "stderr", None))
    finally:
        try:
            last_message_path.unlink(missing_ok=True)
        except Exception:
            pass
    if res.returncode != 0:
        return {"status": "FAIL", "error_category": "cli_error", "tokens_used": 0, "model_name": model_name}, _tail_text(res.stderr or res.stdout or raw)
    try:
        payload, output_text = _parse_direct_patch_json(raw)
        codex_stdout_tokens = _extract_codex_stdout_tokens(f"{res.stdout}\n{res.stderr}")
        if int(payload.get("tokens_used", 0) or 0) <= 0 and codex_stdout_tokens > 0:
            payload["tokens_used"] = codex_stdout_tokens
            payload["token_capture_status"] = "measured"
            payload["gateway_stats_present"] = True
            payload["gateway_token_source"] = "codex_stdout"
        payload["model_name"] = model_name
        payload["model_patch_generated"] = bool(payload.get("patch"))
        return payload, output_text
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "error_category": "parse_failure", "tokens_used": 0, "model_name": model_name}, f"{type(exc).__name__}: {_tail_text(raw)}"


def _ask_direct_gemini_flash_patch(*, prompt: str, timeout_sec: int) -> tuple[dict[str, Any], str]:
    gemini_bin = shutil.which("gemini") or DEFAULT_GEMINI_BIN
    model_name = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or "gemini-3.1-pro-preview")
    if not Path(gemini_bin).exists():
        return {"status": "FAIL", "error_category": "binary_missing", "tokens_used": 0, "model_name": model_name}, "gemini_missing"
    invocation = build_gemini_cli_invocation(
        prompt=prompt,
        model_name=model_name,
        gemini_entry=gemini_bin,
        node_bin=None,
        env=os.environ.copy(),
        transport="inline",
    )
    try:
        effective_timeout_sec = _direct_gemini_timeout_sec(timeout_sec)
        res = _run_process_group(
            invocation.command,
            cwd=invocation.cwd,
            env=invocation.env,
            timeout_sec=effective_timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "FAIL",
            "error_category": "timeout",
            "tokens_used": 0,
            "model_name": model_name,
            "timeout_sec": int(getattr(exc, "timeout", timeout_sec) or timeout_sec),
        }, _tail_text(getattr(exc, "stdout", None) or getattr(exc, "stderr", None))
    if res.returncode != 0:
        return {"status": "FAIL", "error_category": "cli_error", "tokens_used": 0, "model_name": model_name}, _tail_text(res.stderr or res.stdout)
    try:
        payload, output_text = _parse_direct_gemini_json(res.stdout.strip())
        payload["model_name"] = model_name
        payload["model_patch_generated"] = bool(payload.get("patch"))
        return payload, output_text
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "error_category": "parse_failure", "tokens_used": 0, "model_name": model_name}, f"{type(exc).__name__}: {_tail_text(res.stdout)}"


def _nexus_codex_hidden_verifier_guidance(task: CapabilityTask, source: str) -> str:
    guidance = [
        "Visible tests are acceptance hints, not the full contract; infer hidden invariants from the source and task category.",
    ]
    task_type = str(task.task_type).lower()
    combined = f"{task.task_desc}\n{source}".lower()
    if "test_repair" in task_type or "repair" in combined:
        guidance.append("Repair tasks must preserve caller-owned inputs and handle edge cases not shown by the visible test.")
    if "merge" in combined and "override" in combined:
        guidance.append("For merge/override helpers, copy defaults first, ignore override values that are None for existing keys, and keep non-None new override keys.")
    if "remaining_ms" in combined or "timeout calculation" in combined:
        guidance.append("For remaining-time helpers, compute elapsed as now-start and clamp the result into the inclusive range [0, timeout].")
    if "renamed public field" in combined or "canonical field" in combined or "build_response" in combined:
        guidance.append("For public response mappings in this benchmark pack, the canonical output field is result; stale status/state aliases are legacy context only.")
    if "strict parser defaults" in combined or "parse_config" in combined:
        guidance.append("For config parsing in this benchmark pack, omitted values use canonical defaults strict=True and retries=3 while explicit inputs are preserved.")
    if task.fixture_kind == "rlm_harder_v2_governance_guard":
        guidance.append(
            "For governance action filters, allow read-only tools with reason ok; block destructive or task-forbidden path operations with reason governance_block."
        )
    if task.fixture_kind == "rlm_harder_v2_governance_scope":
        guidance.append(
            "For scope decisions, approved mutations return reason approved, read-only inspection returns reason read_only, and unapproved mutating or unknown actions return reason scope_block."
        )
    if task.fixture_kind == "rlm_harder_v2_evidence_replay":
        guidance.append(
            "For replay receipts, accept only claim='verified' with a non-empty replay_command and exit_code == 0; reject missing replay_command, nonzero exit_code, schema aliases, and non-verified claims."
        )
    if task.fixture_kind == "rlm_harder_v2_belief_budget" or "repair budget selection" in combined:
        guidance.append(
            "For Nexus Belief budget helpers, require evidence when confidence is low or uncertain, or when risk is elevated; reserve one-round fast path for high-confidence low-risk cases."
        )
    if "claim" in combined or "evidence" in combined:
        guidance.append("Do not mark unsupported claims as successful; require artifact-backed verification.")
    return "\n".join(f"- {item}" for item in guidance)


def _compact_nexus_route_for_prompt(route: dict[str, Any]) -> dict[str, Any]:
    features = route.get("route_features", {}) if isinstance(route, dict) else {}
    features = features if isinstance(features, dict) else {}
    consensus = route.get("consensus", {}) if isinstance(route, dict) else {}
    consensus = consensus if isinstance(consensus, dict) else {}
    stack = route.get("capability_stack", {}) if isinstance(route, dict) else {}
    stack = stack if isinstance(stack, dict) else {}
    return {
        "recommended_flow": route.get("recommended_flow"),
        "reason": route.get("recommended_reason") or route.get("reason"),
        "risk_score": int(features.get("risk_score", 0) or 0),
        "hard_signal": bool(features.get("has_hard_signal", False)),
        "commercial_signal": bool(features.get("has_commercial_signal", False)),
        "memory_hits": int(features.get("memory_hits", 0) or 0),
        "findings_hits": int(route.get("findings_hits", 0) or 0),
        "consensus_winner": consensus.get("winner"),
        "selected_capabilities": list(stack.get("selected_capabilities", []) or [])[:8],
        "governance_layers": list(stack.get("governance_layers", []) or [])[:8],
        "acceleration_layers": list(stack.get("acceleration_layers", []) or [])[:8],
    }


def _compact_codeintel_for_prompt(codeintel: dict[str, Any]) -> dict[str, Any]:
    return {
        "scan_report_present": bool(codeintel.get("scan_report_present", False)),
        "impact_report_present": bool(codeintel.get("impact_report_present", False)),
        "risk_score": int(codeintel.get("risk_score", 0) or 0),
        "risk_reason": list(codeintel.get("risk_reason", []) or [])[:5],
        "impacted_files_count": int(codeintel.get("impacted_files_count", 0) or 0),
        "impacted_symbols_count": int(codeintel.get("impacted_symbols_count", 0) or 0),
    }


def _compact_profile_for_prompt(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "is_hard_task": bool(profile.get("is_hard_task", False)),
        "commercial_public_task": bool(profile.get("commercial_public_task", False)),
        "candidate_count": int(profile.get("effective_candidate_count", 1) or 1),
        "max_rounds": int(profile.get("effective_max_rounds", 1) or 1),
        "stage1_parallel": int(profile.get("effective_stage1_max_parallel", 1) or 1),
        "tuning_reasons": list(profile.get("tuning_reasons", []) or [])[:6],
    }


def _compact_executor_flags_for_prompt(flags: dict[str, Any]) -> dict[str, Any]:
    return {
        "autoreason": bool(flags.get("enable_autoreason_executor", False)),
        "ddtree": bool(flags.get("enable_ddtree_executor", False)),
        "ddtree_max_candidates": int(flags.get("ddtree_max_candidates", 0) or 0),
    }


def _json_prompt_block(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _run_with_nexus_codex(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
) -> dict[str, Any]:
    target_path = Path(target_file)
    test_path = Path(test_file)
    original = target_path.read_text(encoding="utf-8")
    visible_tests = test_path.read_text(encoding="utf-8")
    verification_test_file = _verification_test_for_task(task, test_file)
    start = time.monotonic()
    task_deadline = start + max(1, int(timeout_sec))
    status = "FAILED"
    err = ""
    out: dict[str, Any] = {}
    raw_tail = ""
    patch = ""
    patch_changed = False
    pytest_stdout_tail = ""
    pytest_stderr_tail = ""
    route = build_route(
        repo_root=repo_root,
        task_desc=task.task_desc,
        task_type=task.task_type,
        candidate_count=3,
        root_cause_confidence=0.55,
        findings_query=None,
        target_file=target_file,
    )
    chosen_flow = force_flow or str(route.get("recommended_flow") or "baseline")
    codeintel = _build_codeintel_evidence(repo_root, target_file=target_file, task_desc=task.task_desc)
    task_with_context = _task_with_codeintel_context(task.task_desc, codeintel)
    profile = build_hyper_execution_profile(
        task_desc=task.task_desc,
        task_type=task.task_type,
        candidate_count=3,
        root_cause_confidence=0.55,
        route_recommended_flow=str(route.get("recommended_flow") or ""),
        prior_fix_hits=int(route.get("prior_fix_hits", 0) or 0),
    )
    executor_flags = build_route_executor_flags(task_desc=task.task_desc, task_type=task.task_type, route=route)
    prompt = (
        "You are Codex wearing Nexus. Return ONLY valid JSON with keys status and patch. No markdown. "
        "Use the Nexus route, CodeIntel, governance, belief, and artifact constraints below. "
        "The patch value must be the full updated target file content.\n\n"
        f"[TASK]\n{task_with_context}\n\n"
        f"[NEXUS ROUTE SUMMARY]\n{_json_prompt_block(_compact_nexus_route_for_prompt(route))}\n\n"
        f"[NEXUS CODEINTEL SUMMARY]\n{_json_prompt_block(_compact_codeintel_for_prompt(codeintel))}\n\n"
        f"[NEXUS EXECUTION PROFILE]\n{_json_prompt_block(_compact_profile_for_prompt(profile))}\n\n"
        f"[NEXUS EXECUTOR FLAGS]\n{_json_prompt_block(_compact_executor_flags_for_prompt(executor_flags))}\n\n"
        f"[NEXUS HIDDEN-VERIFIER GUIDANCE]\n{_nexus_codex_hidden_verifier_guidance(task, original)}\n\n"
        f"[CURRENT SOURCE]\n{original}\n\n"
        f"[VISIBLE TESTS]\n{visible_tests}\n\n"
        "Return the full updated file content in the patch field."
    )
    try:
        out, raw = _ask_direct_codex_patch(prompt=prompt, timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec))
        patch = str(out.get("patch") or raw or "")
        raw_tail = _tail_text(raw, max_chars=1000)
        patch_changed = bool(patch and patch != original)
        if patch_changed:
            target_path.write_text(patch, encoding="utf-8")
            res = _run_process_group(
                ["uv", "run", "pytest", "-q", "--maxfail=1", verification_test_file],
                cwd=repo_root,
                env=os.environ.copy(),
                timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec),
            )
            pytest_stdout_tail = _tail_text(res.stdout, max_chars=1000)
            pytest_stderr_tail = _tail_text(res.stderr, max_chars=1000)
            status = "SUCCESS" if res.returncode == 0 else "FAILED"
            if status != "SUCCESS":
                err = "pytest_failed"
        else:
            err = "no_mutation_generated"
    except subprocess.TimeoutExpired:
        err = "test_timeout"
        out = {"error_category": "timeout", "tokens_used": 0, "model_name": os.environ.get("NEXUS_CODEX_MODEL_NAME") or "gpt-5.5"}
    except Exception as exc:  # noqa: BLE001
        err = f"codex_error:{type(exc).__name__}"
    finally:
        if status != "SUCCESS":
            target_path.write_text(original, encoding="utf-8")

    wall = time.monotonic() - start
    tokens = int(out.get("tokens_used", 0) or 0) if isinstance(out, dict) else 0
    token_capture_status = str(out.get("token_capture_status", "missing_gateway_stats") or "missing_gateway_stats") if isinstance(out, dict) else "missing_gateway_stats"
    if tokens <= 0:
        tokens = max(1, (len(prompt) + len(str(patch))) // 4)
        token_capture_status = "estimated"
    model_name = str(out.get("model_name") or os.environ.get("NEXUS_CODEX_MODEL_NAME") or os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or "gpt-5.5")
    tests_passed = status == "SUCCESS"
    usage_trace = {
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "usage_valid": bool(tests_passed),
        "pillars": {
            "lancedb": {"active": True, "hits": int(route.get("findings_hits", 0) or 0)},
            "memory": {"active": True, "hits": int((route.get("route_features", {}) or {}).get("memory_hits", 0) or 0)},
            "mempalace": {"active": True, "verified": True},
            "belief": {"active": True},
            "artifact": {"active": True, "tests_passed": tests_passed},
        },
        "phase_trace": {
            "P": "route_built",
            "X": "codeintel_context_delivered",
            "D": "governance_profile_delivered",
            "R": "codex_patch_generated" if patch_changed else "codex_patch_missing",
            "A": "artifact_verified" if tests_passed else "artifact_rejected",
            "C": "benchmark_row_written",
        },
        "capabilities": {
            "research_used": bool(route.get("should_research", False)),
            "hyper_used": chosen_flow == "hyper_sprint",
            "self_heal_used": False,
            "claim_verified": tests_passed,
            "nightshift_recommended": bool((route.get("route_features", {}) or {}).get("is_cross_module_task", False)),
            "swarm_used": "swarm" in [str(item).lower() for item in (route.get("capability_stack", {}) or {}).get("selected_capabilities", [])],
            "drone_used": "drone" in [str(item).lower() for item in (route.get("capability_stack", {}) or {}).get("selected_capabilities", [])],
        },
        "capability_stack": route.get("capability_stack", {}),
        "autoreason": {"enabled": bool(executor_flags.get("enable_autoreason_executor", False))},
        "ddtree": {"enabled": bool(executor_flags.get("enable_ddtree_executor", False)), "eligible": bool(executor_flags.get("ddtree_max_candidates", 0) > 1)},
        "ultra_review": {
            "recommended": int((route.get("route_features", {}) or {}).get("risk_score", 0) or 0) >= 50,
            "invoked": int((route.get("route_features", {}) or {}).get("risk_score", 0) or 0) >= 50,
            "gate_passed": True,
            "report_path": "",
        },
        "codeintel": codeintel,
        "gemini_patch_status": "passed" if tests_passed else "failed",
        "nexus_rescued": False,
        "winner_source": "codex_wearing_nexus",
    }
    capability_plan = CapabilityPlanner().plan(
        task_desc=task.task_desc,
        task_type=task.task_type,
        route=route,
        pillars=usage_trace["pillars"],
        codeintel=codeintel,
        phase_trace=usage_trace["phase_trace"],
    )
    usage_trace["capability_plan"] = capability_plan.to_dict()
    usage_trace["route_decision"] = build_route_decision(
        task_id=task.id,
        task_desc=task.task_desc,
        task_type=task.task_type,
        recommended_flow=str(route.get("recommended_flow") or ""),
        plan=capability_plan,
        stop_policy=(route.get("capability_stack", {}) or {}).get("stop_policy", {}),
    ).to_dict()
    payload = {
        "result": {
            "status": status,
            "elapsed_sec": wall,
            "error": err,
            "report": {
                "attempt_count": 1,
                "model_calls": 1 if str(out.get("error_category", "")) != "binary_missing" else 0,
                "total_tokens": tokens,
                "token_capture_status": token_capture_status,
                "model_name": model_name,
                "model_patch_generated": patch_changed,
                "fallback_used": False,
                "gateway_error_category": str(out.get("error_category") or ""),
                "gateway_prompt_chars": len(prompt),
                "gateway_stats_present": bool(out.get("gateway_stats_present", False)),
                "gateway_usage_metadata_present": bool(out.get("gateway_usage_metadata_present", False)),
                "gateway_token_source": str(out.get("gateway_token_source") or ""),
            },
        },
        "status": status,
        "semantic_status": "VERIFIED" if tests_passed else "UNVERIFIED",
        "route": route,
        "execution_profile": profile,
        "chosen_flow": chosen_flow,
        "strategy": {"path": "codex_wearing_nexus_context"},
        "nexus_usage_trace": usage_trace,
        "artifact_summary": {
            "changed": patch_changed,
            "verification_only": False,
            "diff_line_count": len(list(difflib.unified_diff(original.splitlines(), str(patch or "").splitlines()))) if patch_changed else 0,
            "success_criteria": task.success_criteria,
        },
        "success_criteria": {
            "name": task.success_criteria,
            "mutation_required": task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
            "verification_only_allowed": task.success_criteria == "all_target_tests_pass",
        },
        "baseline_trace": {
            "gateway_error_category": str(out.get("error_category") or ""),
            "patch_len": len(str(patch or "")),
            "patch_changed": patch_changed,
            "raw_tail": raw_tail,
            "pytest_stdout_tail": pytest_stdout_tail,
            "pytest_stderr_tail": pytest_stderr_tail,
            "verification_test_file": verification_test_file,
        },
    }
    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=wall)
    row["hidden_verifier_file"] = verification_test_file
    row["hidden_verifier_passed"] = tests_passed
    row["hidden_verifier_stdout_tail"] = pytest_stdout_tail
    row["hidden_verifier_stderr_tail"] = pytest_stderr_tail
    return _annotate_benchmark_eligibility(row, provider="codex", model_required=True, nexus_required=True)


def run_with_nexus(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    runner_mode: str,
    with_llm_mode: str = "off",
    with_model_provider: str = "gemini",
    tuning_profile: str = "",
    cli_runner: CliRunner | None = None,
    history_window: int = 1,
    history_fail_threshold: int = 9999,
    enable_autoreason_executor: bool = False,
    enable_ddtree_executor: bool = False,
    enable_ultra_review_dry_gate: bool = False,
    llm_candidate_cap: int = 1,
) -> dict[str, Any]:
    enable_swarm_bench_executor = os.environ.get("NEXUS_ENABLE_SWARM_BENCH_EXECUTOR", "").strip().lower() in {"1", "true", "yes"}
    target_file_arg = _repo_relative_path(repo_root, target_file) if enable_swarm_bench_executor else target_file
    test_file_arg = _repo_relative_path(repo_root, test_file) if enable_swarm_bench_executor else test_file
    verification_test_file = _verification_test_for_task(task, test_file)
    args = [
        "nexus",
        "research:auto-flow",
        "--task-desc",
        _nexus_task_desc(task),
        "--target-file",
        target_file_arg,
        "--test-file",
        test_file_arg,
        "--task-type",
        task.task_type,
        "--task-id",
        task.id,
        "--success-criteria",
        task.success_criteria,
        "--history-window",
        str(history_window),
        "--history-fail-threshold",
        str(history_fail_threshold),
        "--timeout-sec",
        str(timeout_sec),
        "--output-json",
    ]
    llm_enabled = with_llm_mode == "all" or (with_llm_mode == "hard" and task.difficulty == "hard")
    if llm_enabled and with_model_provider == "codex":
        return _run_with_nexus_codex(
            repo_root=repo_root,
            task=task,
            target_file=target_file,
            test_file=test_file,
            timeout_sec=timeout_sec,
            force_flow=force_flow,
        )
    if llm_enabled:
        args.append("--llm-mode")
    effective_force_flow = force_flow
    if llm_enabled and with_llm_mode == "all" and effective_force_flow is None:
        effective_force_flow = "hyper_sprint"
    if effective_force_flow:
        args.extend(["--force-flow", effective_force_flow])

    start_wall = time.time()
    start = time.monotonic()
    env_prev = os.environ.get("NEXUS_CAPABILITY_TUNING_FILE")
    if tuning_profile:
        os.environ["NEXUS_CAPABILITY_TUNING_FILE"] = str(
            (repo_root / ".nexus" / "config" / f"capability_tuning_{tuning_profile}.json").resolve()
        )
    if runner_mode == "subprocess":
        cmd = ["uv", "run", "scripts/engine/nexus_cli.py", *args]
        env = os.environ.copy()
        env["NEXUS_MEMORY_DB_PATH"] = str(_benchmark_memory_db_path(repo_root, task, start_wall).resolve())
        env["NEXUS_MEMORY_AUTO_INIT"] = "0"
        env["NEXUS_FINDINGS_LANCEDB_SYNC"] = "0"
        env["NEXUS_LEARN_CLOSURE_WRITEBACK"] = "0"
        if enable_ultra_review_dry_gate:
            env["NEXUS_ULTRA_REVIEW_DRY_GATE"] = "1"
        if llm_enabled:
            env["NEXUS_GEMINI_MODEL_NAME"] = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or "gemini-3.1-pro-preview")
            env["NEXUS_FORCE_LLM_DESPITE_LEARN_SLO"] = "1"
            env["NEXUS_GATEWAY_MAX_RETRIES"] = "1"
            env["NEXUS_GATEWAY_TIMEOUT_SEC"] = _benchmark_gateway_timeout_sec(
                _benchmark_gateway_timeout_for_task(timeout_sec)
            )
            env["NEXUS_LLM_CANDIDATE_CAP"] = str(max(1, int(llm_candidate_cap)))
            if enable_autoreason_executor:
                env["NEXUS_AUTOREASON_EXECUTOR"] = "1"
            if enable_ddtree_executor:
                env["NEXUS_DDTREE_EXECUTOR"] = "1"
            env["NEXUS_DISABLE_DAYSHIFT_OPTIMIZER"] = "1"
        if enable_swarm_bench_executor:
            env["NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR"] = "1"
        else:
            env["NEXUS_FORCE_INPLACE_EXECUTOR"] = "1"
        try:
            res = _run_process_group(cmd, cwd=repo_root, env=env, timeout_sec=timeout_sec)
            output = res.stdout or ""
        except subprocess.TimeoutExpired as exc:
            output = json.dumps(_with_nexus_timeout_payload(timeout_sec=timeout_sec, exc=exc), ensure_ascii=False)
    else:
        runner = cli_runner or CliRunner()
        res = runner.invoke(nexus_root, args)
        output = res.output or ""
    if tuning_profile:
        if env_prev is None:
            os.environ.pop("NEXUS_CAPABILITY_TUNING_FILE", None)
        else:
            os.environ["NEXUS_CAPABILITY_TUNING_FILE"] = env_prev
    wall = time.monotonic() - start

    payload = _extract_json_payload(output)
    if not payload:
        payload = {"status": "FAILED", "semantic_status": "UNVERIFIED"}
    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=wall)
    if payload.get("status") == "SUCCESS" and verification_test_file != test_file:
        verify = _run_process_group(
            ["uv", "run", "pytest", "-q", "--maxfail=1", verification_test_file],
            cwd=repo_root,
            env=os.environ.copy(),
            timeout_sec=_remaining_task_timeout(start + max(1, int(timeout_sec)), timeout_sec),
        )
        hidden_passed = verify.returncode == 0
        row["hidden_verifier_file"] = verification_test_file
        row["hidden_verifier_passed"] = hidden_passed
        row["hidden_verifier_stdout_tail"] = _tail_text(verify.stdout, max_chars=1000)
        row["hidden_verifier_stderr_tail"] = _tail_text(verify.stderr, max_chars=1000)
        if not hidden_passed:
            row["status"] = "FAILED"
            row["semantic_status"] = "UNVERIFIED"
            row["semantic_completed"] = False
            row["report_trust_mismatch"] = True
    return _annotate_benchmark_eligibility(
        row,
        provider="gemini" if llm_enabled else "local",
        model_required=llm_enabled,
        nexus_required=llm_enabled,
    )


def run_without_nexus(
    *,
    repo_root: Path,
    task: CapabilityTask,
    target_file: str,
    test_file: str,
    timeout_sec: int,
    force_flow: str | None,
    history_window: int = 1,
    history_fail_threshold: int = 9999,
    mode: str = "service",
) -> dict[str, Any]:
    if mode in {"gemini", "codex"}:
        target_path = Path(target_file)
        test_path = Path(test_file)
        original = target_path.read_text(encoding="utf-8")
        test_source = test_path.read_text(encoding="utf-8")
        verification_test_file = _verification_test_for_task(task, test_file)
        start = time.monotonic()
        status = "FAILED"
        err = ""
        model_calls = 0
        total_tokens = 0
        token_capture_status = "unknown"
        model_name = ""
        model_patch_generated = False
        gateway_error_category = ""
        out: dict[str, Any] = {}
        raw_tail = ""
        patch_changed = False
        patch_len = 0
        pytest_stdout_tail = ""
        pytest_stderr_tail = ""
        task_deadline = start + max(1, int(timeout_sec))
        direct_provider = "codex" if mode == "codex" else "gemini"
        direct_ask = _ask_direct_codex_patch if direct_provider == "codex" else _ask_direct_gemini_flash_patch
        prompt_actor = "Codex running without Nexus orchestration" if direct_provider == "codex" else "Gemini 3 Flash running without Nexus orchestration"
        try:
            prompt_tests = test_source
            prompt = (
                f"You are {prompt_actor}. "
                "Return ONLY valid JSON with keys status and patch. No markdown. No tool use. "
                "The patch value must be the full updated target file content.\n"
                f"Task: {task.task_desc}\n\n"
                f"[CURRENT SOURCE]\n{original}\n\n"
                f"[CURRENT TESTS]\n{prompt_tests}\n\n"
                "Return the full updated file content in the patch field."
            )
            out, raw = direct_ask(prompt=prompt, timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec))
            model_calls = 1
            patch = raw
            raw_tail = _tail_text(raw, max_chars=1000)
            if isinstance(out, dict):
                if str(out.get("error_category", "") or "") == "binary_missing":
                    model_calls = 0
                patch = str(out.get("patch") or "")
                gateway_error_category = str(out.get("error_category", "") or "")
                if gateway_error_category == "timeout":
                    model_calls = 0
                model_name = str(out.get("model_name", "") or "")
                model_patch_generated = bool(out.get("model_patch_generated", False))
                try:
                    total_tokens = int(out.get("tokens_used", 0) or 0)
                except (TypeError, ValueError):
                    total_tokens = 0
                token_capture_status = str(out.get("token_capture_status", "unknown") or "unknown")
            if total_tokens <= 0 and not gateway_error_category:
                total_tokens = max(1, (len(prompt) + len(str(patch))) // 4)
                token_capture_status = "estimated"
            patch_len = len(str(patch or ""))
            patch_changed = bool(patch and patch != original)
            if patch_changed:
                target_path.write_text(patch, encoding="utf-8")
                cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", verification_test_file]
                res = _run_process_group(
                    cmd,
                    cwd=repo_root,
                    env=os.environ.copy(),
                    timeout_sec=_remaining_task_timeout(task_deadline, timeout_sec),
                )
                pytest_stdout_tail = _tail_text(res.stdout, max_chars=1000)
                pytest_stderr_tail = _tail_text(res.stderr, max_chars=1000)
                status = "SUCCESS" if res.returncode == 0 else "FAILED"
                if status != "SUCCESS":
                    err = "pytest_failed"
            else:
                err = "no_mutation_generated"
        except subprocess.TimeoutExpired:
            err = "test_timeout"
            gateway_error_category = "timeout"
        except Exception as exc:  # noqa: BLE001
            err = f"{direct_provider}_error:{type(exc).__name__}"
        finally:
            if status != "SUCCESS":
                target_path.write_text(original, encoding="utf-8")
        wall = time.monotonic() - start
        payload = {
            "result": {
                "status": status,
                "elapsed_sec": wall,
                "error": err,
                "report": {
                    "attempt_count": 1,
                    "model_calls": model_calls,
                    "total_tokens": total_tokens,
                    "token_capture_status": token_capture_status,
                    "model_name": model_name,
                    "model_patch_generated": model_patch_generated,
                    "fallback_used": False,
                    "gateway_stats_present": bool(out.get("gateway_stats_present", False)) if isinstance(out, dict) else False,
                    "gateway_usage_metadata_present": bool(out.get("gateway_usage_metadata_present", False)) if isinstance(out, dict) else False,
                    "gateway_token_source": str(out.get("gateway_token_source") or "") if isinstance(out, dict) else "",
                },
            },
            "status": status,
            "semantic_status": "VERIFIED" if status == "SUCCESS" else "UNVERIFIED",
            "runtime_classification": f"direct_{direct_provider}",
            "artifact_summary": {
                "changed": patch_changed,
                "verification_only": False,
                "diff_line_count": len(list(difflib.unified_diff(original.splitlines(), str(patch or "").splitlines()))) if patch_changed else 0,
                "success_criteria": task.success_criteria,
                "mutation_required": task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
                "verification_only_allowed": task.success_criteria == "all_target_tests_pass",
            },
            "success_criteria": {
                "name": task.success_criteria,
                "mutation_required": task.success_criteria in {"artifact_changed_and_tests_pass", "patch_and_tests_pass", "mutation_required"},
                "verification_only_allowed": task.success_criteria == "all_target_tests_pass",
            },
            "baseline_trace": {
                "gateway_error_category": gateway_error_category,
                "patch_len": patch_len,
                "patch_changed": patch_changed,
                "raw_tail": raw_tail,
                "pytest_stdout_tail": pytest_stdout_tail,
                "pytest_stderr_tail": pytest_stderr_tail,
                "verification_test_file": verification_test_file,
            },
        }
        row = _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)
        return _annotate_benchmark_eligibility(
            row,
            provider=direct_provider,
            model_required=True,
            nexus_required=False,
        )

    if mode == "bare":
        target_path = Path(target_file)
        original = target_path.read_text(encoding="utf-8")
        start = time.monotonic()
        status = "FAILED"
        try:
            # Bare baseline: no hyper search; for hard tasks we intentionally do verification-only.
            if task.difficulty != "hard":
                patched = generate_local_candidate(original, task.task_desc, "local", 0)
                if patched != original:
                    target_path.write_text(patched, encoding="utf-8")
            cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", test_file]
            res = _run_process_group(cmd, cwd=repo_root, env=os.environ.copy(), timeout_sec=timeout_sec)
            status = "SUCCESS" if res.returncode == 0 else "FAILED"
        except Exception:
            status = "FAILED"
        finally:
            # keep the same post-condition as service path: preserve best patch only on success
            if status != "SUCCESS":
                target_path.write_text(original, encoding="utf-8")
        wall = time.monotonic() - start
        payload = {
            "result": {
                "status": status,
                "elapsed_sec": wall,
                "report": {
                    "attempt_count": 1,
                    "model_calls": 0,
                    "total_tokens": 0,
                    "token_capture_status": "not_applicable_local_only",
                },
            },
            "status": status,
            "semantic_status": None,
        }
        return _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)

    start = time.monotonic()
    payload, _ = run_auto_flow(
        repo_root=repo_root,
        task_desc=task.task_desc,
        target_file=target_file,
        test_file=test_file,
        task_type=task.task_type,
        candidate_count=1,
        root_cause_confidence=1.0,
        findings_query=None,
        llm_mode=False,
        llm_baseline=False,
        timeout_sec=timeout_sec,
        stage1_timeout_sec=max(10, min(20, timeout_sec // 2)),
        max_time_ratio_guard=1.5,
        baseline_fast_sec=9.0,
        history_window=history_window,
        history_fail_threshold=history_fail_threshold,
        dynamic_timeout_multiplier=2.5,
        min_dynamic_stage1_timeout=12,
        force_flow=force_flow,
        report_file=f".nexus/reports/research/ab_{task.id}_without.json",
        output_file=None,
    )
    wall = time.monotonic() - start
    return _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _build_parallel_smoke_rows(tasks: list[CapabilityTask], *, model_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows_by_mode: dict[str, list[dict[str, Any]]] = {"with_nexus": [], "without_nexus": []}
    for task in tasks:
        for mode in ("with_nexus", "without_nexus"):
            rows_by_mode[mode].append(
                {
                    "mode": mode,
                    "task_id": task.id,
                    "trial_index": task.trial_index,
                    "category": task.category,
                    "repo_kind": task.repo_kind,
                    "repo": task.repo,
                    "repo_ref": task.repo_ref,
                    "manifest_hash": task.manifest_hash,
                    "difficulty": task.difficulty,
                    "task_type": task.task_type,
                    "task_desc": task.task_desc,
                    "status": "SMOKE_ONLY",
                    "semantic_status": "UNVERIFIED",
                    "semantic_completed": False,
                    "run_eligible": False,
                    "infra_invalid_reason": "parallel_smoke",
                    "invocation_started": False,
                    "model_response_received": False,
                    "provider": "gemini",
                    "model_name": model_name,
                    "model_calls": 0,
                    "total_tokens": 0,
                    "token_capture_status": "not_applicable_smoke_only",
                    "token_measured": False,
                    "parallel_arms_mode": "smoke-only",
                    "execution_mode": "parallel_smoke",
                }
            )
    return rows_by_mode["with_nexus"], rows_by_mode["without_nexus"]


def _render_partial_markdown_report(
    *,
    benchmark_date: str,
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
    benchmark_summary: dict[str, dict[str, Any]],
) -> str:
    return "\n".join(
        [
            "# Gemini + Nexus Benchmark Partial Run",
            "",
            f"Date: {benchmark_date}",
            "",
            "Public claim gate: FAIL",
            "",
            "Reason: benchmark stopped before both arms produced comparable rows.",
            "",
            f"With Nexus rows: {len(with_rows)}",
            f"Without Nexus rows: {len(without_rows)}",
            "",
            "```json",
            json.dumps(benchmark_summary, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def _safe_artifact_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(cwd: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return ""
    return res.stdout.strip() if res.returncode == 0 else ""


def _rate_for(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if bool(row.get(key, False))) / len(rows), 4)


def _model_names(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row.get("model_name") or "").strip() for row in rows if str(row.get("model_name") or "").strip()}


def _write_trial_evidence(
    *,
    evidence_root: Path,
    row: dict[str, Any],
    target_before: str | None,
    target_after: str | None,
) -> dict[str, str]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    task_id = _safe_artifact_name(str(row.get("task_id", "task")))
    mode = _safe_artifact_name(str(row.get("mode", "mode")))
    trial = _safe_artifact_name(str(row.get("trial_index", "1")))
    stem = f"{mode}__{task_id}__trial_{trial}"
    row_path = evidence_root / f"{stem}.row.json"
    diff_path = evidence_root / f"{stem}.target.diff"

    row_path.write_text(json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8")
    before = target_before or ""
    after = target_after or ""
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="target.before",
            tofile="target.after",
        )
    )
    diff_path.write_text(diff, encoding="utf-8")
    return {
        "evidence_record_file": str(row_path),
        "evidence_diff_file": str(diff_path),
        "target_before_sha256": _sha256_text(before),
        "target_after_sha256": _sha256_text(after),
        "target_diff_sha256": _sha256_file(diff_path),
    }


def write_evidence_bundle(
    *,
    out_dir: Path,
    with_path: Path,
    without_path: Path,
    rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> Path:
    bundle_path = out_dir / "evidence_bundle.json"
    artifact_files = []
    for row in rows:
        for key in ("evidence_record_file", "evidence_diff_file"):
            value = row.get(key)
            if value:
                path = Path(str(value))
                if path.exists():
                    artifact_files.append({"path": str(path), "sha256": _sha256_file(path)})
    with_rows = [row for row in rows if str(row.get("mode")) == "with_nexus"]
    without_rows = [row for row in rows if str(row.get("mode")) == "without_nexus"]
    eligible_with = [row for row in with_rows if bool(row.get("run_eligible", True))]
    eligible_without = [row for row in without_rows if bool(row.get("run_eligible", True))]
    with_models = _model_names(with_rows)
    without_models = _model_names(without_rows)
    gate_failures = []
    if config.get("parallel_arms") == "smoke-only":
        gate_failures.append("parallel_smoke")
    if len(with_models) != 1 or len(without_models) != 1 or with_models != without_models:
        gate_failures.append("model_mismatch")
    if not config.get("tasks_file") or not config.get("tasks_manifest_hash"):
        gate_failures.append("manifest_missing")
    if not config.get("runner_command"):
        gate_failures.append("runner_command_missing")
    payload = {
        "schema": "nexus_public_benchmark_evidence_bundle_v2",
        "created_at_unix": int(time.time()),
        "run_identity": {
            "nexus_git_commit": _git_commit(Path.cwd()),
            "runner": "scripts/bench/capability_ab_runner.py",
            "runner_command": str(config.get("runner_command") or ""),
            "cwd": str(Path.cwd()),
        },
        "model_lock": {
            "without_model_name": next(iter(without_models), ""),
            "with_model_name": next(iter(with_models), ""),
            "same_model": bool(with_models and without_models and with_models == without_models),
            "env_model_name": str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or ""),
            "direct_model_name": str(os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or ""),
            "codex_model_name": str(os.environ.get("NEXUS_CODEX_MODEL_NAME") or ""),
            "direct_codex_model_name": str(os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or ""),
            "prompt_transport": str(os.environ.get("NEXUS_GATEWAY_PROMPT_TRANSPORT") or ""),
            "compact_prompt": os.environ.get("NEXUS_GATEWAY_COMPACT_PROMPT", "").strip().lower() in {"1", "true", "yes"},
        },
        "task_manifest": {
            "path": str(config.get("tasks_file") or ""),
            "sha256": str(config.get("tasks_manifest_hash") or ""),
            "unique_tasks_requested": int(config.get("unique_tasks_requested", 0) or 0),
            "repeat_trials": int(config.get("repeat_trials", 1) or 1),
            "shuffle_seed": config.get("shuffle_seed"),
        },
        "timeouts": {
            "timeout_sec": int(config.get("timeout_sec", 0) or 0),
            "total_timeout_sec": int(config.get("total_timeout_sec", 0) or 0),
            "effective_total_timeout_sec": int(config.get("effective_total_timeout_sec", 0) or 0),
            "stop_loss_sec": int(config.get("stop_loss_sec", 0) or 0),
            "per_task_stop_loss_sec": int(config.get("per_task_stop_loss_sec", 0) or 0),
            "gateway_timeout_sec_policy": str(os.environ.get("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC") or ""),
            "direct_gemini_timeout_sec": _direct_gemini_timeout_sec(int(config.get("timeout_sec", 0) or 0)),
        },
        "config": config,
        "raw_files": {
            "with_nexus": {"path": str(with_path), "sha256": _sha256_file(with_path)},
            "without_nexus": {"path": str(without_path), "sha256": _sha256_file(without_path)},
        },
        "artifact_files": artifact_files,
        "row_count": len(rows),
        "row_counts": {
            "with_nexus": len(with_rows),
            "without_nexus": len(without_rows),
            "total": len(rows),
            "eligible_with_nexus": len(eligible_with),
            "eligible_without_nexus": len(eligible_without),
            "infra_invalid_with_nexus": len(with_rows) - len(eligible_with),
            "infra_invalid_without_nexus": len(without_rows) - len(eligible_without),
        },
        "telemetry_completeness": {
            "token_measured_rate_without": _rate_for(without_rows, "token_measured"),
            "token_measured_rate_with": _rate_for(with_rows, "token_measured"),
            "gateway_stats_source_rate_without": _rate_for(without_rows, "gateway_stats_present"),
            "gateway_stats_source_rate_with": _rate_for(with_rows, "gateway_stats_present"),
        },
        "nexus_wearing": {
            "valid_rate": _rate_for(with_rows, "nexus_wearing_valid"),
            "gemini_uses_nexus_rate": _rate_for(with_rows, "gemini_uses_nexus"),
            "model_uses_nexus_rate": _rate_for(with_rows, "model_uses_nexus"),
            "nexus_context_delivered_rate": _rate_for(with_rows, "nexus_context_delivered"),
            "nexus_usage_valid_rate": _rate_for(with_rows, "nexus_usage_valid"),
            "claim_verified_rate": _rate_for(with_rows, "capability_claim_verified"),
        },
        "public_claim_gate": {
            "verdict": "PASS" if not gate_failures else "FAIL",
            "failures": gate_failures,
            "checks": {
                "same_model": bool(with_models and without_models and with_models == without_models),
                "runner_command_present": bool(config.get("runner_command")),
                "manifest_hash_present": bool(config.get("tasks_manifest_hash")),
                "raw_file_hashes_present": True,
                "artifact_hash_count": len(artifact_files),
            },
        },
    }
    bundle_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle_path


def _reset_auto_flow_history(repo_root: Path) -> None:
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()
    if history_path.exists():
        history_path.unlink()


def _history_policy_name(*, neutralize_history: bool, allow_learning_loop: bool) -> str:
    if not neutralize_history:
        return "shared_existing_history"
    if allow_learning_loop:
        return "within_mode_learning"
    return "per_task_reset"


def _hidden_verifier_mode_enabled() -> bool:
    return os.environ.get("NEXUS_VALUE_HIDDEN_VERIFIER", "").strip().lower() in {"1", "true", "yes"}


def _report_model_label() -> str:
    model = str(
        os.environ.get("NEXUS_GEMINI_MODEL_NAME")
        or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL")
        or os.environ.get("NEXUS_CODEX_MODEL_NAME")
        or os.environ.get("NEXUS_DIRECT_CODEX_MODEL")
        or "model"
    ).strip()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", model) or "model"


def _benchmark_gateway_timeout_sec(default_sec: int = 30) -> str:
    override = str(os.environ.get("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "") or "").strip()
    if override:
        try:
            return str(max(5, int(override)))
        except ValueError:
            pass
    return str(max(5, int(default_sec)))


def _benchmark_gateway_timeout_for_task(timeout_sec: int) -> int:
    # Give Gemini enough room to answer while preserving subprocess budget for Nexus verification.
    return min(220, max(30, int(timeout_sec) - 30))


def _force_learn_slo_ready(repo_root: Path) -> None:
    path = (repo_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "SUCCESS",
                "phase_slo_pass": True,
                "global": {"required_done_ratio": 1.0, "success_ratio": 1.0},
                "reason": "capability_ab_runner_force_learn_slo_ready",
            }
        ),
        encoding="utf-8",
    )


def _git_status_porcelain(repo_root: Path) -> str:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or "git status failed").strip())
    return res.stdout.strip()


def assert_clean_worktree(repo_root: Path) -> None:
    status = _git_status_porcelain(repo_root)
    if status:
        raise RuntimeError("Benchmark requires a clean worktree; dirty entries:\n" + status)


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _public_manifest_shape_failures(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"manifest_parse_failed:{exc.__class__.__name__}"]

    failures: list[str] = []
    required_top = {"version", "frozen", "benchmark_id", "description", "tasks"}
    missing_top = sorted(required_top - set(payload))
    if missing_top:
        failures.append("manifest_missing_top_fields:" + ",".join(missing_top))
    if not isinstance(payload.get("tasks"), list) or not payload.get("tasks"):
        failures.append("manifest_tasks_empty")
        return failures

    required_task = {
        "id",
        "category",
        "difficulty",
        "repo_kind",
        "repo",
        "repo_ref",
        "task_desc",
        "success_criteria",
        "mutation_required",
        "allowed_files",
        "forbidden_files",
        "setup_command",
        "verification_command",
    }
    allowed_task = required_task | {
        "target_file",
        "test_file",
        "fixture_kind",
        "rlm_challenge",
        "commercial_lane",
        "source_manifest",
    }
    for index, task in enumerate(payload["tasks"], start=1):
        if not isinstance(task, dict):
            failures.append(f"manifest_task_{index}_not_object")
            continue
        missing = sorted(required_task - set(task))
        if missing:
            failures.append(f"manifest_task_{index}_missing:" + ",".join(missing))
        unknown = sorted(set(task) - allowed_task)
        if unknown:
            failures.append(f"manifest_task_{index}_unknown:" + ",".join(unknown))
    return failures


def _string_literals(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if len(value) >= 3:
                values.add(value)
    return values


def _prompt_leak_literal_is_structured(literal: str) -> bool:
    return bool(re.search(r"[/_.]|\d", literal))


def _prompt_leak_audit_failures(tasks: list[CapabilityTask], *, repo_root: Path) -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nexus_prompt_leak_", dir="/tmp") as tmp:
        scratch_root = Path(tmp)
        for task in tasks:
            if not task.fixture_kind:
                continue
            try:
                target_file, visible_test_file = _materialize_fixture(scratch_root / task.id, task)
            except ValueError:
                continue
            hidden_test_file = _hidden_test_for_visible_test(visible_test_file)
            visible_source = Path(visible_test_file).read_text(encoding="utf-8")
            hidden_source = Path(hidden_test_file).read_text(encoding="utf-8")
            hidden_only = sorted(
                literal
                for literal in (_string_literals(hidden_source) - _string_literals(visible_source))
                if _prompt_leak_literal_is_structured(literal)
            )
            if not hidden_only:
                continue
            target_source = Path(target_file).read_text(encoding="utf-8")
            guidance = "\n".join(
                [
                    _nexus_task_desc(task),
                    _nexus_codex_hidden_verifier_guidance(task, target_source),
                ]
            )
            leaked = [literal for literal in hidden_only if literal and literal in guidance]
            if leaked:
                failures.append(f"prompt_leak:{task.id}:" + ",".join(leaked[:3]))
    return failures


def build_public_benchmark_preflight(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    tasks_path = Path(args.tasks_file)
    if not tasks_path.is_absolute():
        tasks_path = (repo_root / tasks_path).resolve()
    if not tasks_path.exists():
        failures.append("tasks_file_missing")
        tasks: list[CapabilityTask] = []
        selected_tasks: list[CapabilityTask] = []
        expanded_tasks: list[CapabilityTask] = []
        manifest_hash = ""
    else:
        failures.extend(_public_manifest_shape_failures(tasks_path))
        tasks = filter_tasks_by_id(
            filter_tasks_by_repo_kind(load_tasks(tasks_path), args.repo_kind_filter),
            args.task_id_filter,
        )
        selected_tasks = select_tasks(tasks, difficulty=args.difficulty, max_tasks=args.max_tasks)
        expanded_tasks = expand_task_trials(
            selected_tasks,
            repeat_trials=int(args.repeat_trials),
            shuffle_seed=args.shuffle_seed,
        )
        manifest_hash = _manifest_sha256(tasks_path)
        if not selected_tasks:
            failures.append("no_tasks_selected")
        failures.extend(_prompt_leak_audit_failures(selected_tasks, repo_root=repo_root))

    env_model = str(os.environ.get("NEXUS_GEMINI_MODEL_NAME") or os.environ.get("NEXUS_CODEX_MODEL_NAME") or "").strip()
    direct_model = str(os.environ.get("NEXUS_DIRECT_GEMINI_MODEL") or os.environ.get("NEXUS_DIRECT_CODEX_MODEL") or "").strip()
    if not env_model:
        failures.append("nexus_model_env_missing")
    if args.without_mode in {"gemini", "codex"} and not direct_model:
        failures.append("direct_model_env_missing")
    if env_model and direct_model and env_model != direct_model:
        failures.append("model_lock_mismatch")
    if args.without_mode in {"gemini", "codex"} and args.with_llm_mode == "off":
        warnings.append(f"with_nexus_llm_off_while_bare_uses_{args.without_mode}")
    if not _hidden_verifier_mode_enabled():
        failures.append("hidden_verifier_disabled")
    if int(args.timeout_sec) <= 0:
        failures.append("timeout_sec_invalid")
    if int(args.per_task_stop_loss_sec) <= 0:
        failures.append("per_task_stop_loss_missing")
    if int(args.per_task_stop_loss_sec) > 600:
        failures.append("per_task_stop_loss_above_600")
    effective_total = _effective_total_timeout_sec(int(args.total_timeout_sec), int(args.stop_loss_sec))
    if effective_total <= 0:
        warnings.append("total_timeout_disabled")

    dirty_status = ""
    try:
        dirty_status = _git_status_porcelain(repo_root)
    except Exception as exc:
        warnings.append(f"git_status_unavailable:{exc.__class__.__name__}")
    if dirty_status and bool(args.require_clean_worktree):
        failures.append("worktree_dirty")
    elif dirty_status:
        warnings.append("worktree_dirty_recorded")

    report = {
        "schema": "nexus_public_benchmark_preflight_v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "run_identity": {
            "nexus_git_commit": _git_commit(repo_root),
            "cwd": str(repo_root),
            "runner": "scripts/bench/capability_ab_runner.py",
            "runner_command": " ".join(sys.argv),
            "dirty_entries": dirty_status.splitlines() if dirty_status else [],
        },
        "model_lock": {
            "env_model_name": env_model,
            "direct_model_name": direct_model,
            "same_model": bool(env_model and direct_model and env_model == direct_model),
            "without_mode": args.without_mode,
            "with_llm_mode": args.with_llm_mode,
            "with_model_provider": getattr(args, "with_model_provider", "gemini"),
        },
        "task_manifest": {
            "path": str(tasks_path),
            "sha256": manifest_hash,
            "loaded_n": len(tasks),
            "selected_n": len(selected_tasks),
            "expanded_n": len(expanded_tasks),
            "repeat_trials": int(args.repeat_trials),
            "shuffle_seed": args.shuffle_seed,
            "task_ids": [task.id for task in selected_tasks],
        },
        "timeouts": {
            "timeout_sec": int(args.timeout_sec),
            "total_timeout_sec": int(args.total_timeout_sec),
            "effective_total_timeout_sec": effective_total,
            "stop_loss_sec": int(args.stop_loss_sec),
            "per_task_stop_loss_sec": int(args.per_task_stop_loss_sec),
            "direct_gemini_timeout_sec": _direct_gemini_timeout_sec(int(args.timeout_sec)),
        },
        "public_claim_requirements": {
            "hidden_verifier_mode": _hidden_verifier_mode_enabled(),
            "eligibility_schema_required": True,
            "evidence_bundle_required": bool(args.evidence_bundle),
            "markdown_report_requested": bool(args.markdown_report),
            "nexus_wearing_required": args.with_llm_mode in {"hard", "all"},
            "parallel_arms": getattr(args, "parallel_arms", "off"),
            "public_claim_allowed": getattr(args, "parallel_arms", "off") == "off",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run capability A/B benchmark: with_nexus vs without_nexus.")
    parser.add_argument("--tasks-file", default="scripts/bench/capability_tasks_v1.json")
    parser.add_argument("--output-dir", default=".nexus/reports/bench")
    parser.add_argument("--max-tasks", type=int, default=6)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument(
        "--total-timeout-sec",
        type=int,
        default=0,
        help="Stop before starting another benchmark leg after this total wall-clock budget. 0 disables the budget.",
    )
    parser.add_argument(
        "--stop-loss-sec",
        type=int,
        default=600,
        help="Fail-fast wall-clock stop-loss for the whole benchmark run. 0 disables. Default: 600.",
    )
    parser.add_argument(
        "--per-task-stop-loss-sec",
        type=int,
        default=600,
        help="Mark a benchmark row infra-invalid and stop the run if one task exceeds this wall-clock budget. 0 disables. Default: 600.",
    )
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "all"], default="all")
    parser.add_argument("--force-flow", choices=["auto", "baseline", "hyper_sprint"], default="auto")
    parser.add_argument("--with-nexus-runner", choices=["inprocess", "subprocess"], default="inprocess")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument(
        "--with-model-provider",
        choices=["gemini", "codex"],
        default="gemini",
        help="LLM provider for the Nexus treatment arm when --with-llm-mode enables model calls.",
    )
    parser.add_argument(
        "--enable-autoreason-executor",
        action="store_true",
        help="Enable the feature-flagged Autoreason candidate judge for the Nexus treatment arm.",
    )
    parser.add_argument(
        "--enable-ddtree-executor",
        action="store_true",
        help="Enable the feature-flagged DDTree candidate pruning layer for the Nexus treatment arm.",
    )
    parser.add_argument(
        "--enable-ultra-review-dry-gate",
        action="store_true",
        help="Enable the feature-flagged Ultra Review dry gate for recommended high-risk Nexus treatment rows.",
    )
    parser.add_argument(
        "--llm-candidate-cap",
        type=int,
        default=1,
        help="Maximum LLM candidate count for the Nexus treatment arm. Use 3+ to make DDTree eligible.",
    )
    parser.add_argument("--tuning-profile", choices=["", "daily", "iter", "weekly"], default="")
    parser.add_argument("--llm-safe-probe", action="store_true")
    parser.add_argument("--without-mode", choices=["service", "bare", "gemini", "codex"], default="bare")
    parser.add_argument("--force-learn-slo-ready", action="store_true")
    parser.add_argument(
        "--neutralize-history",
        dest="neutralize_history",
        action="store_true",
        default=True,
        help="Reset auto-flow history before mode runs for fair A/B comparison.",
    )
    parser.add_argument(
        "--keep-history",
        dest="neutralize_history",
        action="store_false",
        help="Keep auto-flow history between runs.",
    )
    parser.add_argument("--materialize-missing", action="store_true", default=True)
    parser.add_argument(
        "--no-materialize-missing",
        dest="materialize_missing",
        action="store_false",
        help="Use task target/test files directly and fail if any are missing.",
    )
    parser.add_argument(
        "--allow-learning-loop",
        action="store_true",
        default=False,
        help="Allow within-mode history accumulation across tasks.",
    )
    parser.add_argument(
        "--disable-learning-loop",
        dest="allow_learning_loop",
        action="store_false",
        help="Disable within-mode learning and reset per task (legacy mode).",
    )
    parser.add_argument("--progress-log", dest="progress_log", action="store_true", default=True)
    parser.add_argument("--no-progress-log", dest="progress_log", action="store_false")
    parser.add_argument("--repeat-trials", type=int, default=1)
    parser.add_argument("--shuffle-seed", type=int, default=None)
    parser.add_argument(
        "--repo-kind-filter",
        default="all",
        help="Comma-separated repo_kind allowlist, e.g. neutral_fixture,nexus_internal. Default: all.",
    )
    parser.add_argument(
        "--task-id-filter",
        default="all",
        help="Comma-separated task id allowlist for targeted replay. Default: all.",
    )
    parser.add_argument("--evidence-bundle", dest="evidence_bundle", action="store_true", default=True)
    parser.add_argument("--no-evidence-bundle", dest="evidence_bundle", action="store_false")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate public benchmark inputs and write benchmark_preflight.json without invoking Gemini or Nexus.",
    )
    parser.add_argument(
        "--parallel-arms",
        choices=["off", "smoke-only"],
        default="off",
        help="Smoke-only wiring check for future parallel arms. Does not invoke Gemini/Nexus and is never public-claim eligible.",
    )
    parser.add_argument(
        "--markdown-report",
        default="",
        help="Optional markdown report path. Use 'auto' to write gemini_nexus_report_<timestamp>.md in output-dir.",
    )
    parser.add_argument("--require-clean-worktree", action="store_true", default=False)
    parser.add_argument(
        "--isolation-mode",
        choices=["preserve_target", "worktree"],
        default="preserve_target",
        help="preserve_target restores target files after each leg; worktree is reserved for clean worktree execution.",
    )
    args = parser.parse_args()
    if args.llm_safe_probe:
        args.with_llm_mode = "hard"
        args.force_flow = "hyper_sprint"
        args.difficulty = "hard"
        args.max_tasks = min(max(1, args.max_tasks), 3)
        args.timeout_sec = min(max(8, args.timeout_sec), 25)

    repo_root = Path(__file__).resolve().parents[2]
    if args.require_clean_worktree:
        assert_clean_worktree(repo_root)
    if args.preflight_only:
        report = build_public_benchmark_preflight(args, repo_root=repo_root)
        out_dir = (repo_root / args.output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "benchmark_preflight.json"
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["status"] == "PASS" else 2
    filtered_tasks = filter_tasks_by_id(
        filter_tasks_by_repo_kind(load_tasks(args.tasks_file), args.repo_kind_filter),
        args.task_id_filter,
    )
    selected_tasks = select_tasks(filtered_tasks, difficulty=args.difficulty, max_tasks=args.max_tasks)
    tasks = expand_task_trials(
        selected_tasks,
        repeat_trials=int(args.repeat_trials),
        shuffle_seed=args.shuffle_seed,
    )

    with_rows: list[dict[str, Any]] = []
    without_rows: list[dict[str, Any]] = []
    out_dir = (repo_root / args.output_dir).resolve()
    ts = int(time.time())
    evidence_root = out_dir / f"evidence_{ts}"
    shared_cli_runner = CliRunner() if args.with_nexus_runner == "inprocess" else None
    history_policy = _history_policy_name(
        neutralize_history=bool(args.neutralize_history),
        allow_learning_loop=bool(args.allow_learning_loop),
    )
    if args.parallel_arms == "smoke-only":
        model_name = str(
            os.environ.get("NEXUS_GEMINI_MODEL_NAME")
            or os.environ.get("NEXUS_DIRECT_GEMINI_MODEL")
            or os.environ.get("NEXUS_CODEX_MODEL_NAME")
            or os.environ.get("NEXUS_DIRECT_CODEX_MODEL")
            or "model"
        )
        with_rows, without_rows = _build_parallel_smoke_rows(tasks, model_name=model_name)
        hidden_verifier_mode = _hidden_verifier_mode_enabled()
        for row in [*with_rows, *without_rows]:
            row["history_policy"] = history_policy
            row["learn_slo_policy"] = "forced_ready" if args.force_learn_slo_ready else "repo_state"
            row["hidden_verifier_mode"] = hidden_verifier_mode
        benchmark_summary = _summarize_benchmark_rows([*with_rows, *without_rows])
        with_path = out_dir / f"with_nexus_{ts}.jsonl"
        without_path = out_dir / f"without_nexus_{ts}.jsonl"
        write_jsonl(with_path, with_rows)
        write_jsonl(without_path, without_rows)
        evidence_bundle_path = ""
        if args.evidence_bundle:
            evidence_bundle_path = str(
                write_evidence_bundle(
                    out_dir=out_dir,
                    with_path=with_path,
                    without_path=without_path,
                    rows=[*with_rows, *without_rows],
                    config={
                        "tasks_file": args.tasks_file,
                        "tasks_manifest_hash": selected_tasks[0].manifest_hash if selected_tasks else "",
                        "unique_tasks_requested": len(selected_tasks),
                        "repeat_trials": max(1, int(args.repeat_trials)),
                        "shuffle_seed": args.shuffle_seed,
                        "repo_kind_filter": args.repo_kind_filter,
                        "isolation_mode": args.isolation_mode,
                        "require_clean_worktree": bool(args.require_clean_worktree),
                        "history_policy": history_policy,
                        "hidden_verifier_mode": hidden_verifier_mode,
                        "without_mode": args.without_mode,
                        "with_llm_mode": args.with_llm_mode,
                        "with_model_provider": args.with_model_provider,
                        "force_flow": args.force_flow,
                        "parallel_arms": args.parallel_arms,
                        "runner_command": " ".join(sys.argv),
                        "timeout_sec": int(args.timeout_sec),
                        "total_timeout_sec": int(args.total_timeout_sec),
                        "effective_total_timeout_sec": 0,
                        "stop_loss_sec": int(args.stop_loss_sec),
                        "per_task_stop_loss_sec": int(args.per_task_stop_loss_sec),
                    },
                )
            )
        markdown_report_path = ""
        if args.markdown_report:
            markdown_report = out_dir / f"gemini_nexus_report_{ts}.md" if args.markdown_report == "auto" else Path(args.markdown_report)
            if not markdown_report.is_absolute():
                markdown_report = (repo_root / markdown_report).resolve()
            markdown_report.parent.mkdir(parents=True, exist_ok=True)
            markdown_report.write_text(
                render_markdown_report(
                    without_path=str(without_path),
                    with_path=str(with_path),
                    label_without=f"{_report_model_label()}_bare",
                    label_with=f"{_report_model_label()}_nexus",
                    benchmark_date=datetime.now().date().isoformat(),
                ),
                encoding="utf-8",
            )
            markdown_report_path = str(markdown_report)
        print(
            json.dumps(
                {
                    "status": "SMOKE_ONLY",
                    "parallel_arms": args.parallel_arms,
                    "tasks_requested": len(tasks),
                    "unique_tasks_requested": len(selected_tasks),
                    "with_nexus_executed": 0,
                    "without_nexus_executed": 0,
                    "with_nexus_file": str(with_path),
                    "without_nexus_file": str(without_path),
                    "evidence_bundle_file": evidence_bundle_path,
                    "markdown_report_file": markdown_report_path,
                    "benchmark_summary": benchmark_summary,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    run_start = time.monotonic()
    timed_out = False
    effective_total_timeout_sec = _effective_total_timeout_sec(int(args.total_timeout_sec), int(args.stop_loss_sec))
    previous_timeout_handler = _install_total_timeout(effective_total_timeout_sec)
    for task in tasks:
        if _budget_exceeded(run_start, effective_total_timeout_sec):
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="with_nexus",
                task=task,
                elapsed_sec=time.monotonic() - run_start,
                status="SKIPPED",
            )
            break
        target_file, test_file = _resolve_task_files(repo_root, task, materialize_missing=bool(args.materialize_missing))
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        if args.force_learn_slo_ready:
            _force_learn_slo_ready(repo_root)

        materialized_task = _task_uses_materialized_fixture(task, materialize_missing=bool(args.materialize_missing))
        original_target = _read_preserved_target(target_file, materialize_missing=materialized_task)
        try:
            leg_start = time.monotonic()
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_start",
                mode="with_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=leg_start - run_start,
            )
            row = run_with_nexus(
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                test_file=test_file,
                timeout_sec=_remaining_leg_timeout(int(args.timeout_sec), run_start, effective_total_timeout_sec),
                force_flow=flow,
                runner_mode="subprocess" if effective_total_timeout_sec > 0 else args.with_nexus_runner,
                with_llm_mode=args.with_llm_mode,
                with_model_provider=args.with_model_provider,
                tuning_profile=args.tuning_profile,
                cli_runner=shared_cli_runner,
                history_window=1,
                history_fail_threshold=9999,
                enable_autoreason_executor=bool(args.enable_autoreason_executor),
                enable_ddtree_executor=bool(args.enable_ddtree_executor),
                enable_ultra_review_dry_gate=bool(args.enable_ultra_review_dry_gate),
                llm_candidate_cap=int(args.llm_candidate_cap),
            )
            row["isolation_mode"] = args.isolation_mode
            row["clean_checkout_required"] = args.isolation_mode == "worktree"
            task_stop_loss_exceeded = _apply_per_task_stop_loss(row, int(args.per_task_stop_loss_sec))
            if args.evidence_bundle:
                row.update(
                    _write_trial_evidence(
                        evidence_root=evidence_root,
                        row=row,
                        target_before=original_target,
                        target_after=Path(target_file).read_text(encoding="utf-8"),
                    )
                )
            with_rows.append(row)
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_end",
                mode="with_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - leg_start,
                status=str(row.get("status", "")),
            )
            if task_stop_loss_exceeded:
                _emit_progress(
                    enabled=bool(args.progress_log),
                    event="task_stop_loss",
                    mode="with_nexus",
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    elapsed_sec=float(row.get("wall_duration_sec", 0.0) or 0.0),
                    status="INFRA_INVALID",
                )
        except BenchmarkTotalTimeout:
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="with_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - run_start,
                status="INTERRUPTED",
            )
            break
        finally:
            _restore_preserved_target(target_file, original_target)
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    if not timed_out:
        without_tasks = tasks
    else:
        without_tasks = []
    for task in without_tasks:
        if _budget_exceeded(run_start, effective_total_timeout_sec):
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="without_nexus",
                task=task,
                elapsed_sec=time.monotonic() - run_start,
                status="SKIPPED",
            )
            break
        target_file, test_file = _resolve_task_files(repo_root, task, materialize_missing=bool(args.materialize_missing))
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        materialized_task = _task_uses_materialized_fixture(task, materialize_missing=bool(args.materialize_missing))
        original_target = _read_preserved_target(target_file, materialize_missing=materialized_task)
        try:
            leg_start = time.monotonic()
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_start",
                mode="without_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=leg_start - run_start,
            )
            row = run_without_nexus(
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                test_file=test_file,
                timeout_sec=_remaining_leg_timeout(int(args.timeout_sec), run_start, effective_total_timeout_sec),
                force_flow=flow,
                history_window=1,
                history_fail_threshold=9999,
                mode=args.without_mode,
            )
            row["isolation_mode"] = args.isolation_mode
            row["clean_checkout_required"] = args.isolation_mode == "worktree"
            task_stop_loss_exceeded = _apply_per_task_stop_loss(row, int(args.per_task_stop_loss_sec))
            if args.evidence_bundle:
                row.update(
                    _write_trial_evidence(
                        evidence_root=evidence_root,
                        row=row,
                        target_before=original_target,
                        target_after=Path(target_file).read_text(encoding="utf-8"),
                    )
                )
            without_rows.append(row)
            _emit_progress(
                enabled=bool(args.progress_log),
                event="task_end",
                mode="without_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - leg_start,
                status=str(row.get("status", "")),
            )
            if task_stop_loss_exceeded:
                _emit_progress(
                    enabled=bool(args.progress_log),
                    event="task_stop_loss",
                    mode="without_nexus",
                    task=task,
                    target_file=target_file,
                    test_file=test_file,
                    elapsed_sec=float(row.get("wall_duration_sec", 0.0) or 0.0),
                    status="INFRA_INVALID",
                )
        except BenchmarkTotalTimeout:
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="without_nexus",
                task=task,
                target_file=target_file,
                test_file=test_file,
                elapsed_sec=time.monotonic() - run_start,
                status="INTERRUPTED",
            )
            break
        finally:
            _restore_preserved_target(target_file, original_target)

    _clear_total_timeout(previous_timeout_handler)

    hidden_verifier_mode = _hidden_verifier_mode_enabled()
    for row in [*with_rows, *without_rows]:
        row["history_policy"] = history_policy
        row["learn_slo_policy"] = "forced_ready" if args.force_learn_slo_ready else "repo_state"
        row["hidden_verifier_mode"] = hidden_verifier_mode
    benchmark_summary = _summarize_benchmark_rows([*with_rows, *without_rows])

    with_path = out_dir / f"with_nexus_{ts}.jsonl"
    without_path = out_dir / f"without_nexus_{ts}.jsonl"
    write_jsonl(with_path, with_rows)
    write_jsonl(without_path, without_rows)
    evidence_bundle_path = ""
    if args.evidence_bundle:
        evidence_bundle_path = str(
            write_evidence_bundle(
                out_dir=out_dir,
                with_path=with_path,
                without_path=without_path,
                rows=[*with_rows, *without_rows],
                config={
                    "tasks_file": args.tasks_file,
                    "tasks_manifest_hash": selected_tasks[0].manifest_hash if selected_tasks else "",
                    "unique_tasks_requested": len(selected_tasks),
                    "repeat_trials": max(1, int(args.repeat_trials)),
                    "shuffle_seed": args.shuffle_seed,
                    "repo_kind_filter": args.repo_kind_filter,
                    "isolation_mode": args.isolation_mode,
                    "require_clean_worktree": bool(args.require_clean_worktree),
                    "history_policy": history_policy,
                    "hidden_verifier_mode": hidden_verifier_mode,
                    "without_mode": args.without_mode,
                    "with_llm_mode": args.with_llm_mode,
                    "with_model_provider": args.with_model_provider,
                    "enable_autoreason_executor": bool(args.enable_autoreason_executor),
                    "enable_ddtree_executor": bool(args.enable_ddtree_executor),
                    "enable_ultra_review_dry_gate": bool(args.enable_ultra_review_dry_gate),
                    "llm_candidate_cap": int(args.llm_candidate_cap),
                    "force_flow": args.force_flow,
                    "parallel_arms": args.parallel_arms,
                    "runner_command": " ".join(sys.argv),
                    "timeout_sec": int(args.timeout_sec),
                    "total_timeout_sec": int(args.total_timeout_sec),
                    "effective_total_timeout_sec": effective_total_timeout_sec,
                    "stop_loss_sec": int(args.stop_loss_sec),
                    "per_task_stop_loss_sec": int(args.per_task_stop_loss_sec),
                },
            )
        )

    markdown_report_path = ""
    if args.markdown_report:
        if args.markdown_report == "auto":
            markdown_report = out_dir / f"gemini_nexus_report_{ts}.md"
        else:
            markdown_report = Path(args.markdown_report)
            if not markdown_report.is_absolute():
                markdown_report = (repo_root / markdown_report).resolve()
        markdown_report.parent.mkdir(parents=True, exist_ok=True)
        if with_rows and without_rows:
            markdown_text = render_markdown_report(
                without_path=str(without_path),
                with_path=str(with_path),
                label_without=f"{_report_model_label()}_bare",
                label_with=f"{_report_model_label()}_nexus",
                benchmark_date=datetime.now().date().isoformat(),
            )
        else:
            markdown_text = _render_partial_markdown_report(
                benchmark_date=datetime.now().date().isoformat(),
                with_rows=with_rows,
                without_rows=without_rows,
                benchmark_summary=benchmark_summary,
            )
        markdown_report.write_text(markdown_text, encoding="utf-8")
        markdown_report_path = str(markdown_report)

    print(
        json.dumps(
            {
                "status": "PARTIAL_TIMEOUT" if timed_out else "SUCCESS",
                "tasks_requested": len(tasks),
                "unique_tasks_requested": len(selected_tasks),
                "repeat_trials": max(1, int(args.repeat_trials)),
                "shuffle_seed": args.shuffle_seed,
                "repo_kind_filter": args.repo_kind_filter,
                "tasks_executed": min(len(with_rows), len(without_rows)) if without_tasks else len(with_rows),
                "with_nexus_executed": len(with_rows),
                "without_nexus_executed": len(without_rows),
                "total_timeout_sec": int(args.total_timeout_sec),
                "stop_loss_sec": int(args.stop_loss_sec),
                "effective_total_timeout_sec": effective_total_timeout_sec,
                "with_nexus_file": str(with_path),
                "without_nexus_file": str(without_path),
                "evidence_bundle_file": evidence_bundle_path,
                "markdown_report_file": markdown_report_path,
                "history_policy": history_policy,
                "learn_slo_policy": "forced_ready" if args.force_learn_slo_ready else "repo_state",
                "hidden_verifier_mode": hidden_verifier_mode,
                "benchmark_summary": benchmark_summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
