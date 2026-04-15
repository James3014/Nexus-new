from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = REPO_ROOT / ".nexus" / "learn_refresh_daemon_status.json"
LOG_FILE = REPO_ROOT / ".nexus" / "learn_refresh_daemon.log"
PID_FILE = REPO_ROOT / ".nexus" / "learn_refresh_daemon.pid"
DEFAULT_PLAN_REPORT = REPO_ROOT / ".nexus" / "reports" / "learn" / "daemon_refresh_plan.json"
DEFAULT_REFRESH_REPORT = REPO_ROOT / ".nexus" / "reports" / "learn" / "daemon_refresh_run.json"
DEFAULT_BENCHMARK_REPORT = REPO_ROOT / ".nexus" / "reports" / "learn" / "daemon_benchmark.json"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def write_status(payload: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_plan_cmd(*, topic: str, due_within_days: int, report_file: Path) -> list[str]:
    return [
        str(VENV_PYTHON),
        "scripts/engine/nexus_cli.py",
        "nexus",
        "learn:refresh-plan",
        "--due-within-days",
        str(due_within_days),
        "--report-file",
        str(report_file.relative_to(REPO_ROOT)),
        "--output-json",
        *(["--topic", topic] if topic else []),
    ]


def build_refresh_cmd(*, topic: str, pass_threshold: float, question_count: int, report_file: Path) -> list[str]:
    return [
        str(VENV_PYTHON),
        "scripts/engine/nexus_cli.py",
        "nexus",
        "learn:refresh",
        "--due-only",
        "--pass-threshold",
        str(pass_threshold),
        "--question-count",
        str(question_count),
        "--report-file",
        str(report_file.relative_to(REPO_ROOT)),
        "--output-json",
        *(["--topic", topic] if topic else []),
    ]


def build_benchmark_cmd(*, topic: str, manifest_file: str, report_file: Path) -> list[str]:
    return [
        str(VENV_PYTHON),
        "scripts/engine/nexus_cli.py",
        "nexus",
        "learn:benchmark",
        "--manifest-file",
        manifest_file,
        "--topic",
        topic,
        "--report-file",
        str(report_file.relative_to(REPO_ROOT)),
        "--output-json",
    ]


def run_cycle(
    *,
    topic: str = "",
    due_within_days: int = 0,
    pass_threshold: float = 0.6,
    question_count: int = 5,
    benchmark_manifest: str = "",
) -> dict[str, Any]:
    plan_rc, plan_out, plan_err = run_cmd(
        build_plan_cmd(topic=topic, due_within_days=due_within_days, report_file=DEFAULT_PLAN_REPORT)
    )
    plan = load_json(DEFAULT_PLAN_REPORT)
    due_count = int(plan.get("due_count", 0)) if plan_rc == 0 else 0

    result: dict[str, Any] = {
        "status": "SUCCESS" if plan_rc == 0 else "FAIL",
        "topic": topic,
        "due_within_days": due_within_days,
        "plan_rc": plan_rc,
        "plan_error": plan_err.strip(),
        "due_count": due_count,
        "refreshed_count": 0,
        "benchmark_ran": False,
        "benchmark_rc": None,
        "timestamp": now_iso(),
    }
    if plan_rc != 0:
        return result

    refresh_rc = 0
    refresh_err = ""
    if due_count > 0:
        refresh_rc, _, refresh_err = run_cmd(
            build_refresh_cmd(
                topic=topic,
                pass_threshold=pass_threshold,
                question_count=question_count,
                report_file=DEFAULT_REFRESH_REPORT,
            )
        )
        refresh = load_json(DEFAULT_REFRESH_REPORT)
        result["refresh_rc"] = refresh_rc
        result["refresh_error"] = refresh_err.strip()
        result["refreshed_count"] = int(refresh.get("refreshed_count", 0)) if refresh_rc == 0 else 0
        if refresh_rc != 0:
            result["status"] = "FAIL"

    if benchmark_manifest and topic and due_count > 0 and result["status"] == "SUCCESS":
        bench_rc, _, bench_err = run_cmd(
            build_benchmark_cmd(topic=topic, manifest_file=benchmark_manifest, report_file=DEFAULT_BENCHMARK_REPORT)
        )
        result["benchmark_ran"] = True
        result["benchmark_rc"] = bench_rc
        result["benchmark_error"] = bench_err.strip()
        benchmark = load_json(DEFAULT_BENCHMARK_REPORT)
        if bench_rc == 0:
            result["benchmark_success_rate"] = benchmark.get("best", {}).get("success_rate", 0.0)
        else:
            result["status"] = "FAIL"

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Learn refresh daemon")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-sec", type=int, default=3600)
    parser.add_argument("--topic", default="")
    parser.add_argument("--due-within-days", type=int, default=0)
    parser.add_argument("--pass-threshold", type=float, default=0.6)
    parser.add_argument("--question-count", type=int, default=5)
    parser.add_argument("--benchmark-manifest", default="")
    args = parser.parse_args()

    loop_count = 0
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    logging.info("Learn refresh daemon started (once=%s)", args.once)

    try:
        while True:
            loop_count += 1
            write_status({
                "state": "RUNNING",
                "loop_count": loop_count,
                "pid": os.getpid(),
                "updated_at": now_iso(),
                "topic": args.topic,
            })
            cycle = run_cycle(
                topic=args.topic,
                due_within_days=args.due_within_days,
                pass_threshold=args.pass_threshold,
                question_count=args.question_count,
                benchmark_manifest=args.benchmark_manifest,
            )
            cycle["state"] = "IDLE" if cycle.get("status") == "SUCCESS" else "ERROR"
            cycle["loop_count"] = loop_count
            cycle["pid"] = os.getpid()
            write_status(cycle)
            logging.info("Learn refresh cycle result: %s", json.dumps(cycle, ensure_ascii=False))
            if args.once:
                return 0 if cycle.get("status") == "SUCCESS" else 1
            time.sleep(max(30, int(args.interval_sec)))
    finally:
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
