#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from nexus.app.research_flow_service import run_auto_flow
from nexus.research.local_sprint_mutator import generate_local_candidate
from scripts.engine.nexus_cli import nexus as nexus_root


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
                )
            )
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(expanded)
    return expanded


def _materialize_fixture(repo_root: Path, task: CapabilityTask) -> tuple[str, str]:
    case_dir = (repo_root / ".nexus" / "bench_cases" / task.id).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    target_path = case_dir / "target.py"
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


def _resolve_task_files(repo_root: Path, task: CapabilityTask, *, materialize_missing: bool) -> tuple[str, str]:
    if task.repo_kind == "nexus_internal":
        materialize_missing = False
    if task.repo_kind == "external" and materialize_missing:
        raise NotImplementedError(
            f"{task.id} is external; clone/setup adapter is required before public execution"
        )
    if materialize_missing:
        return _materialize_fixture(repo_root, task)

    target_path = (repo_root / task.target_file).resolve()
    test_path = (repo_root / task.test_file).resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Missing target_file for {task.id}: {task.target_file}")
    if not test_path.exists():
        raise FileNotFoundError(f"Missing test_file for {task.id}: {task.test_file}")
    return str(target_path), str(test_path)


def _read_preserved_target(target_file: str, *, materialize_missing: bool) -> str | None:
    if materialize_missing:
        return None
    return Path(target_file).read_text(encoding="utf-8")


def _restore_preserved_target(target_file: str, original: str | None) -> None:
    if original is None:
        return
    Path(target_file).write_text(original, encoding="utf-8")


def _budget_exceeded(start_time: float, total_timeout_sec: int) -> bool:
    return total_timeout_sec > 0 and (time.time() - start_time) >= total_timeout_sec


def _remaining_leg_timeout(default_timeout_sec: int, start_time: float, total_timeout_sec: int) -> int:
    if total_timeout_sec <= 0:
        return default_timeout_sec
    remaining = int(total_timeout_sec - (time.time() - start_time))
    return max(1, min(default_timeout_sec, remaining))


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
    pillars = usage_trace.get("pillars", {}) if isinstance(usage_trace, dict) else {}
    pillars = pillars if isinstance(pillars, dict) else {}
    phase_trace = usage_trace.get("phase_trace", {}) if isinstance(usage_trace, dict) else {}
    phase_trace = phase_trace if isinstance(phase_trace, dict) else {}
    capabilities = usage_trace.get("capabilities", {}) if isinstance(usage_trace, dict) else {}
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    learn_phase_slo = payload.get("learn_phase_slo", {}) if isinstance(payload, dict) else {}
    consensus = route.get("consensus", {}) if isinstance(route, dict) else {}
    consensus_votes = consensus.get("votes", {}) if isinstance(consensus, dict) else {}
    task_duration = float(result.get("elapsed_sec", wall_time_sec) or wall_time_sec)
    model_calls = int(report.get("model_calls", 0) or 0)
    total_tokens = int(report.get("total_tokens", 0) or 0)
    token_capture_status = str(report.get("token_capture_status", "unknown") or "unknown")
    semantic_status = payload.get("semantic_status")
    semantic_completed = bool(
        payload.get("status") == "SUCCESS"
        and semantic_status in {"VERIFIED", "PARTIAL"}
    )
    return {
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
        "retryable": payload.get("retryable"),
        "duration_sec": round(task_duration, 4),
        "task_duration_sec": round(task_duration, 4),
        "wall_duration_sec": round(wall_time_sec, 4),
        "elapsed_sec": task_duration,
        "attempt_count": int(report.get("attempt_count", 0) or 0),
        "model_calls": model_calls,
        "total_tokens": total_tokens,
        "token_capture_status": token_capture_status,
        "token_measured": bool(total_tokens > 0),
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
        "gemini_uses_nexus": bool(usage_trace.get("gemini_uses_nexus", False)),
        "nexus_context_delivered": bool(usage_trace.get("nexus_context_delivered", False)),
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
        "capability_swarm_used": bool(capabilities.get("swarm_used", False)),
        "capability_drone_used": bool(capabilities.get("drone_used", False)),
    }


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
    tuning_profile: str = "",
    cli_runner: CliRunner | None = None,
    history_window: int = 1,
    history_fail_threshold: int = 9999,
) -> dict[str, Any]:
    args = [
        "nexus",
        "research:auto-flow",
        "--task-desc",
        task.task_desc,
        "--target-file",
        target_file,
        "--test-file",
        test_file,
        "--task-type",
        task.task_type,
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
    if llm_enabled:
        args.append("--llm-mode")
    if force_flow:
        args.extend(["--force-flow", force_flow])

    start = time.time()
    env_prev = os.environ.get("NEXUS_CAPABILITY_TUNING_FILE")
    if tuning_profile:
        os.environ["NEXUS_CAPABILITY_TUNING_FILE"] = str(
            (repo_root / ".nexus" / "config" / f"capability_tuning_{tuning_profile}.json").resolve()
        )
    if runner_mode == "subprocess":
        cmd = ["uv", "run", "scripts/engine/nexus_cli.py", *args]
        env = os.environ.copy()
        try:
            res = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, env=env, timeout=timeout_sec)
            output = res.stdout or ""
        except subprocess.TimeoutExpired:
            output = json.dumps(
                {
                    "status": "FAILED",
                    "semantic_status": "UNVERIFIED",
                    "runtime_classification": "subprocess_timeout",
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
            )
    else:
        runner = cli_runner or CliRunner()
        res = runner.invoke(nexus_root, args)
        output = res.output or ""
    if tuning_profile:
        if env_prev is None:
            os.environ.pop("NEXUS_CAPABILITY_TUNING_FILE", None)
        else:
            os.environ["NEXUS_CAPABILITY_TUNING_FILE"] = env_prev
    wall = time.time() - start

    payload = _extract_json_payload(output)
    if not payload:
        payload = {"status": "FAILED", "semantic_status": "UNVERIFIED"}
    return _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=wall)


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
    if mode == "gemini":
        target_path = Path(target_file)
        original = target_path.read_text(encoding="utf-8")
        start = time.time()
        status = "FAILED"
        err = ""
        model_calls = 0
        total_tokens = 0
        token_capture_status = "unknown"
        try:
            from nexus.services.gateway import BattlesuitGateway

            prompt = (
                "You are Gemini 3 Flash running without Nexus orchestration.\n"
                f"Task: {task.task_desc}\n\n"
                f"[CURRENT SOURCE]\n{original}\n\n"
                "Return the full updated file content in the patch field."
            )
            gateway = BattlesuitGateway(project_root=repo_root)
            out, raw = gateway.ask_structured(
                prompt=prompt,
                payload="Return FULL file content only.",
                phase="R",
                output_schema={"status": "APPROVED | FAIL", "patch": "Full target file content"},
                model_name="gemini-3-flash-preview",
            )
            model_calls = 1
            patch = raw
            if isinstance(out, dict):
                patch = str(out.get("patch") or raw)
                try:
                    total_tokens = int(out.get("tokens_used", 0) or 0)
                except (TypeError, ValueError):
                    total_tokens = 0
                token_capture_status = str(out.get("token_capture_status", "unknown") or "unknown")
            if total_tokens <= 0:
                total_tokens = max(1, (len(prompt) + len(str(patch))) // 4)
                token_capture_status = "estimated"
            if patch and patch != original:
                target_path.write_text(patch, encoding="utf-8")
                cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", test_file]
                res = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, timeout=timeout_sec)
                status = "SUCCESS" if res.returncode == 0 else "FAILED"
                if status != "SUCCESS":
                    err = "pytest_failed"
            else:
                err = "no_mutation_generated"
        except subprocess.TimeoutExpired:
            err = "test_timeout"
        except Exception as exc:  # noqa: BLE001
            err = f"gemini_error:{type(exc).__name__}"
        finally:
            if status != "SUCCESS":
                target_path.write_text(original, encoding="utf-8")
        wall = time.time() - start
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
                    "model_name": "gemini-3-flash-preview",
                },
            },
            "status": status,
            "semantic_status": "VERIFIED" if status == "SUCCESS" else "UNVERIFIED",
            "runtime_classification": "direct_gemini_flash",
        }
        return _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)

    if mode == "bare":
        target_path = Path(target_file)
        original = target_path.read_text(encoding="utf-8")
        start = time.time()
        status = "FAILED"
        try:
            # Bare baseline: no hyper search; for hard tasks we intentionally do verification-only.
            if task.difficulty != "hard":
                patched = generate_local_candidate(original, task.task_desc, "local", 0)
                if patched != original:
                    target_path.write_text(patched, encoding="utf-8")
            cmd = ["uv", "run", "pytest", "-q", "--maxfail=1", test_file]
            res = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, timeout=timeout_sec)
            status = "SUCCESS" if res.returncode == 0 else "FAILED"
        except Exception:
            status = "FAILED"
        finally:
            # keep the same post-condition as service path: preserve best patch only on success
            if status != "SUCCESS":
                target_path.write_text(original, encoding="utf-8")
        wall = time.time() - start
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

    start = time.time()
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
    wall = time.time() - start
    return _extract_record(mode="without_nexus", task=task, payload=payload, wall_time_sec=wall)


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _safe_artifact_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    payload = {
        "schema": "nexus_public_benchmark_evidence_bundle_v1",
        "created_at_unix": int(time.time()),
        "config": config,
        "raw_files": {
            "with_nexus": {"path": str(with_path), "sha256": _sha256_file(with_path)},
            "without_nexus": {"path": str(without_path), "sha256": _sha256_file(without_path)},
        },
        "artifact_files": artifact_files,
        "row_count": len(rows),
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
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "all"], default="all")
    parser.add_argument("--force-flow", choices=["auto", "baseline", "hyper_sprint"], default="auto")
    parser.add_argument("--with-nexus-runner", choices=["inprocess", "subprocess"], default="inprocess")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument("--tuning-profile", choices=["", "daily", "iter", "weekly"], default="")
    parser.add_argument("--llm-safe-probe", action="store_true")
    parser.add_argument("--without-mode", choices=["service", "bare", "gemini"], default="bare")
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
    parser.add_argument("--evidence-bundle", dest="evidence_bundle", action="store_true", default=True)
    parser.add_argument("--no-evidence-bundle", dest="evidence_bundle", action="store_false")
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
    filtered_tasks = filter_tasks_by_repo_kind(load_tasks(args.tasks_file), args.repo_kind_filter)
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
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    run_start = time.time()
    timed_out = False
    previous_timeout_handler = _install_total_timeout(int(args.total_timeout_sec))
    for task in tasks:
        if _budget_exceeded(run_start, int(args.total_timeout_sec)):
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="with_nexus",
                task=task,
                elapsed_sec=time.time() - run_start,
                status="SKIPPED",
            )
            break
        target_file, test_file = _resolve_task_files(repo_root, task, materialize_missing=bool(args.materialize_missing))
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        if args.force_learn_slo_ready:
            _force_learn_slo_ready(repo_root)

        original_target = _read_preserved_target(target_file, materialize_missing=bool(args.materialize_missing))
        try:
            leg_start = time.time()
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
                timeout_sec=_remaining_leg_timeout(int(args.timeout_sec), run_start, int(args.total_timeout_sec)),
                force_flow=flow,
                runner_mode="subprocess" if int(args.total_timeout_sec) > 0 else args.with_nexus_runner,
                with_llm_mode=args.with_llm_mode,
                tuning_profile=args.tuning_profile,
                cli_runner=shared_cli_runner,
                history_window=1,
                history_fail_threshold=9999,
            )
            row["isolation_mode"] = args.isolation_mode
            row["clean_checkout_required"] = args.isolation_mode == "worktree"
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
                elapsed_sec=time.time() - leg_start,
                status=str(row.get("status", "")),
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
                elapsed_sec=time.time() - run_start,
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
        if _budget_exceeded(run_start, int(args.total_timeout_sec)):
            timed_out = True
            _emit_progress(
                enabled=bool(args.progress_log),
                event="total_timeout",
                mode="without_nexus",
                task=task,
                elapsed_sec=time.time() - run_start,
                status="SKIPPED",
            )
            break
        target_file, test_file = _resolve_task_files(repo_root, task, materialize_missing=bool(args.materialize_missing))
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        original_target = _read_preserved_target(target_file, materialize_missing=bool(args.materialize_missing))
        try:
            leg_start = time.time()
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
                timeout_sec=_remaining_leg_timeout(int(args.timeout_sec), run_start, int(args.total_timeout_sec)),
                force_flow=flow,
                history_window=1,
                history_fail_threshold=9999,
                mode=args.without_mode,
            )
            row["isolation_mode"] = args.isolation_mode
            row["clean_checkout_required"] = args.isolation_mode == "worktree"
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
                elapsed_sec=time.time() - leg_start,
                status=str(row.get("status", "")),
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
                elapsed_sec=time.time() - run_start,
                status="INTERRUPTED",
            )
            break
        finally:
            _restore_preserved_target(target_file, original_target)

    _clear_total_timeout(previous_timeout_handler)

    for row in [*with_rows, *without_rows]:
        row["history_policy"] = history_policy
        row["learn_slo_policy"] = "forced_ready" if args.force_learn_slo_ready else "repo_state"

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
                    "without_mode": args.without_mode,
                    "with_llm_mode": args.with_llm_mode,
                    "force_flow": args.force_flow,
                },
            )
        )

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
                "with_nexus_file": str(with_path),
                "without_nexus_file": str(without_path),
                "evidence_bundle_file": evidence_bundle_path,
                "history_policy": history_policy,
                "learn_slo_policy": "forced_ready" if args.force_learn_slo_ready else "repo_state",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
