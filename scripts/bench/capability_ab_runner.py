#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from nexus.app.research_flow_service import run_auto_flow
from nexus.research.local_sprint_mutator import generate_local_candidate
from scripts.engine.nexus_cli import nexus as nexus_root


@dataclass(frozen=True)
class CapabilityTask:
    id: str
    difficulty: str
    task_type: str
    task_desc: str
    target_file: str
    test_file: str
    success_criteria: str


def load_tasks(path: str | Path) -> list[CapabilityTask]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks_raw = payload.get("tasks", [])
    tasks: list[CapabilityTask] = []
    for row in tasks_raw:
        tasks.append(
            CapabilityTask(
                id=str(row["id"]),
                difficulty=str(row["difficulty"]),
                task_type=str(row["task_type"]),
                task_desc=str(row["task_desc"]),
                target_file=str(row["target_file"]),
                test_file=str(row["test_file"]),
                success_criteria=str(row.get("success_criteria", "all_target_tests_pass")),
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
        "artifact_diff_line_count": int(artifact_summary.get("diff_line_count", 0) or 0),
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
        res = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True, env=env)
        output = res.stdout or ""
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


def _reset_auto_flow_history(repo_root: Path) -> None:
    history_path = (repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json").resolve()
    if history_path.exists():
        history_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run capability A/B benchmark: with_nexus vs without_nexus.")
    parser.add_argument("--tasks-file", default="scripts/bench/capability_tasks_v1.json")
    parser.add_argument("--output-dir", default=".nexus/reports/bench")
    parser.add_argument("--max-tasks", type=int, default=6)
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "all"], default="all")
    parser.add_argument("--force-flow", choices=["auto", "baseline", "hyper_sprint"], default="auto")
    parser.add_argument("--with-nexus-runner", choices=["inprocess", "subprocess"], default="inprocess")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument("--tuning-profile", choices=["", "daily", "iter", "weekly"], default="")
    parser.add_argument("--llm-safe-probe", action="store_true")
    parser.add_argument("--without-mode", choices=["service", "bare"], default="bare")
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
        "--allow-learning-loop",
        action="store_true",
        default=True,
        help="Allow within-mode history accumulation across tasks.",
    )
    parser.add_argument(
        "--disable-learning-loop",
        dest="allow_learning_loop",
        action="store_false",
        help="Disable within-mode learning and reset per task (legacy mode).",
    )
    args = parser.parse_args()
    if args.llm_safe_probe:
        args.with_llm_mode = "hard"
        args.force_flow = "hyper_sprint"
        args.difficulty = "hard"
        args.max_tasks = min(max(1, args.max_tasks), 3)
        args.timeout_sec = min(max(8, args.timeout_sec), 25)

    repo_root = Path(__file__).resolve().parents[2]
    tasks = select_tasks(load_tasks(args.tasks_file), difficulty=args.difficulty, max_tasks=args.max_tasks)

    with_rows: list[dict[str, Any]] = []
    without_rows: list[dict[str, Any]] = []
    shared_cli_runner = CliRunner() if args.with_nexus_runner == "inprocess" else None
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    for task in tasks:
        target_file, test_file = task.target_file, task.test_file
        if args.materialize_missing:
            target_file, test_file = _materialize_fixture(repo_root, task)
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)

        with_rows.append(
            run_with_nexus(
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                test_file=test_file,
                timeout_sec=args.timeout_sec,
                force_flow=flow,
                runner_mode=args.with_nexus_runner,
                with_llm_mode=args.with_llm_mode,
                tuning_profile=args.tuning_profile,
                cli_runner=shared_cli_runner,
                history_window=1,
                history_fail_threshold=9999,
            )
        )
    if args.neutralize_history:
        _reset_auto_flow_history(repo_root)
    for task in tasks:
        target_file, test_file = task.target_file, task.test_file
        if args.materialize_missing:
            target_file, test_file = _materialize_fixture(repo_root, task)
        flow = None if args.force_flow == "auto" else args.force_flow
        if args.neutralize_history and not args.allow_learning_loop:
            _reset_auto_flow_history(repo_root)
        without_rows.append(
            run_without_nexus(
                repo_root=repo_root,
                task=task,
                target_file=target_file,
                test_file=test_file,
                timeout_sec=args.timeout_sec,
                force_flow=flow,
                history_window=1,
                history_fail_threshold=9999,
                mode=args.without_mode,
            )
        )

    out_dir = (repo_root / args.output_dir).resolve()
    ts = int(time.time())
    with_path = out_dir / f"with_nexus_{ts}.jsonl"
    without_path = out_dir / f"without_nexus_{ts}.jsonl"
    write_jsonl(with_path, with_rows)
    write_jsonl(without_path, without_rows)

    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "tasks_executed": len(tasks),
                "with_nexus_file": str(with_path),
                "without_nexus_file": str(without_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
