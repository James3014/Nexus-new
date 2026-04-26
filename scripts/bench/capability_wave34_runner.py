#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def _extract_json(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass
    brace_positions = [idx for idx, ch in enumerate(text) if ch == "{"]
    for idx in reversed(brace_positions):
        try:
            payload = json.loads(text[idx:])
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Wave3/4 benchmark pipeline: full_ab -> ops_loop -> s_grade -> regression_guard.")
    parser.add_argument("--ops-profile", choices=["daily", "iter", "weekly"], default="daily")
    parser.add_argument("--ops-rounds", type=int, default=14)
    parser.add_argument("--stress-tasks-file", default="scripts/bench/capability_tasks_cross_module_v1.json")
    parser.add_argument("--min-grade", default="S9_PASS")
    parser.add_argument("--with-llm-mode", choices=["off", "hard", "all"], default="off")
    parser.add_argument("--with-model-label", default="")
    parser.add_argument("--without-model-label", default="")
    parser.add_argument("--baseline-s-grade-file", default=".nexus/reports/bench/s_grade/s_grade_baseline.json")
    parser.add_argument("--write-baseline-on-pass", action="store_true")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    start = time.time()

    full_ab_bare_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_full_report.py",
        "--with-nexus-runner",
        "inprocess",
        "--enable-stress-cross-bucket",
        "--stress-tasks-file",
        str(args.stress_tasks_file),
        "--without-mode",
        "bare",
        "--with-llm-mode",
        str(args.with_llm_mode),
        "--stress-force-flow",
        "auto",
        "--stress-tuning-profile",
        "iter",
        "--output-json",
    ]
    if args.with_model_label:
        full_ab_bare_cmd.extend(["--with-model-label", str(args.with_model_label)])
    if args.without_model_label:
        full_ab_bare_cmd.extend(["--without-model-label", str(args.without_model_label)])
    full_ab_bare_res = _run(full_ab_bare_cmd, cwd=repo_root)
    full_ab_bare_payload = _extract_json(full_ab_bare_res.stdout)
    if full_ab_bare_res.returncode != 0:
        print(json.dumps({"status": "FAIL", "stage": "full_ab_bare", "stderr": full_ab_bare_res.stderr}, ensure_ascii=False))
        return 2

    full_ab_service_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_full_report.py",
        "--with-nexus-runner",
        "subprocess",
        "--enable-stress-cross-bucket",
        "--stress-tasks-file",
        str(args.stress_tasks_file),
        "--without-mode",
        "service",
        "--with-llm-mode",
        str(args.with_llm_mode),
        "--stress-force-flow",
        "auto",
        "--stress-tuning-profile",
        "iter",
        "--output-json",
    ]
    if args.with_model_label:
        full_ab_service_cmd.extend(["--with-model-label", str(args.with_model_label)])
    if args.without_model_label:
        full_ab_service_cmd.extend(["--without-model-label", str(args.without_model_label)])
    full_ab_service_res = _run(full_ab_service_cmd, cwd=repo_root)
    full_ab_service_payload = _extract_json(full_ab_service_res.stdout)
    if full_ab_service_res.returncode != 0:
        print(json.dumps({"status": "FAIL", "stage": "full_ab_service", "stderr": full_ab_service_res.stderr}, ensure_ascii=False))
        return 2

    ops_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ops_loop.py",
        "--profile",
        str(args.ops_profile),
        "--rounds",
        str(max(1, int(args.ops_rounds))),
        "--with-llm-mode",
        str(args.with_llm_mode),
        "--output-json",
    ]
    ops_res = _run(ops_cmd, cwd=repo_root)
    ops_payload = _extract_json(ops_res.stdout)
    if ops_res.returncode != 0:
        print(json.dumps({"status": "FAIL", "stage": "ops_loop", "stderr": ops_res.stderr}, ensure_ascii=False))
        return 2

    s_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_s_grade.py",
        "--full-ab-file",
        str(full_ab_bare_payload.get("report_file", "")),
        "--service-full-ab-file",
        str(full_ab_service_payload.get("report_file", "")),
        "--ops-rounds-file",
        str(ops_payload.get("report_file", "")),
        "--output-json",
    ]
    s_res = _run(s_cmd, cwd=repo_root)
    s_payload = _extract_json(s_res.stdout)
    if s_res.returncode != 0:
        print(json.dumps({"status": "FAIL", "stage": "s_grade", "stderr": s_res.stderr}, ensure_ascii=False))
        return 2

    guard_cmd = [
        "uv",
        "run",
        "python",
        "scripts/bench/capability_regression_guard.py",
        "--current-s-grade-file",
        str(s_payload.get("report_file", "")),
        "--service-full-ab-file",
        str(full_ab_service_payload.get("report_file", "")),
        "--baseline-s-grade-file",
        str(args.baseline_s_grade_file),
        "--min-grade",
        str(args.min_grade),
        "--output-json",
    ]
    if args.write_baseline_on_pass:
        guard_cmd.append("--write-baseline-on-pass")
    guard_res = _run(guard_cmd, cwd=repo_root)
    guard_payload = _extract_json(guard_res.stdout)

    result = {
        "status": "SUCCESS" if guard_res.returncode == 0 else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_sec": round(time.time() - start, 3),
        "with_llm_mode": str(args.with_llm_mode),
        "model_profiles": {
            "with_nexus": {
                "label": str(args.with_model_label or ("gemini-3-flash-preview" if args.with_llm_mode != "off" else "local-first")),
                "with_llm_mode": str(args.with_llm_mode),
            },
            "without_nexus": {
                "label": str(args.without_model_label or "baseline"),
                "with_llm_mode": "off",
            },
        },
        "stages": {
            "full_ab_bare": {"exit_code": full_ab_bare_res.returncode, "report_file": full_ab_bare_payload.get("report_file", "")},
            "full_ab_service": {"exit_code": full_ab_service_res.returncode, "report_file": full_ab_service_payload.get("report_file", "")},
            "ops_loop": {"exit_code": ops_res.returncode, "report_file": ops_payload.get("report_file", "")},
            "s_grade": {"exit_code": s_res.returncode, "report_file": s_payload.get("report_file", "")},
            "regression_guard": {"exit_code": guard_res.returncode, "report_file": guard_payload.get("report_file", "")},
        },
        "summary": {
            "s_grade_verdict": ((s_payload.get("summary", {}) or {}).get("verdict") if isinstance(s_payload.get("summary", {}), dict) else ""),
            "guard_status": guard_payload.get("status", "FAIL"),
            "guard_failures": guard_payload.get("failures", []),
        },
    }
    out_file = Path(".nexus/reports/bench/wave34").resolve() / f"wave34_run_{int(time.time())}.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["report_file"] = str(out_file)

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Wave3/4 pipeline: {result['status']}")
        print(f"Report: {out_file}")
    return 0 if guard_res.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
