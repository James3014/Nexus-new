#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Phase 7 loop: phase6 research + skills autotune.",
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--workspace", required=True, help="Autoresearch workspace path")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--proof-ratio-min", type=float, default=95.0)
    parser.add_argument("--output-prefix", default="phase7")
    parser.add_argument("--skip-autopilot", action="store_true")
    parser.add_argument("--autotune-apply", action="store_true")
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--baseline", type=float, default=0.55)
    parser.add_argument("--learning-rate", type=float, default=0.6)
    parser.add_argument("--degrade-threshold", type=float, default=0.2)
    parser.add_argument("--max-step", type=float, default=0.35)
    parser.add_argument("--degrade-consecutive-rounds", type=int, default=3)
    return parser


def _run(cmd: list[str], cwd: Path) -> int:
    return subprocess.call(cmd, cwd=str(cwd))


def main() -> int:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()

    phase6_script = project_root / "scripts" / "ops" / "phase6_research.py"
    if not phase6_script.exists():
        print(f"[phase7] missing script: {phase6_script}")
        return 2

    phase6_cmd = [
        sys.executable,
        str(phase6_script),
        "--workspace",
        str(workspace),
        "--rounds",
        str(args.rounds),
        "--proof-ratio-min",
        str(args.proof_ratio_min),
        "--output-prefix",
        args.output_prefix,
    ]
    if args.skip_autopilot:
        phase6_cmd.append("--skip-autopilot")
    phase6_rc = _run(phase6_cmd, project_root)

    autotune_cmd = [
        sys.executable,
        str(project_root / "scripts" / "ops" / "skills_autotune.py"),
        "--project-root",
        str(project_root),
        "--min-samples",
        str(args.min_samples),
        "--baseline",
        str(args.baseline),
        "--learning-rate",
        str(args.learning_rate),
        "--degrade-threshold",
        str(args.degrade_threshold),
        "--max-step",
        str(args.max_step),
        "--degrade-consecutive-rounds",
        str(args.degrade_consecutive_rounds),
    ]
    if args.autotune_apply:
        autotune_cmd.append("--apply")
    autotune_rc = _run(autotune_cmd, project_root)

    phase6_report = workspace / f"{args.output_prefix}_research_report_cn.json"
    autotune_report = project_root / ".nexus" / "metrics" / "skills_autotune_report.json"
    phase6_payload: dict = {}
    autotune_payload: dict = {}

    if phase6_report.exists():
        phase6_payload = json.loads(phase6_report.read_text(encoding="utf-8"))
    if autotune_report.exists():
        autotune_payload = json.loads(autotune_report.read_text(encoding="utf-8"))

    final_report = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "workspace": str(workspace),
        "phase6_return_code": phase6_rc,
        "autotune_return_code": autotune_rc,
        "phase6_report": str(phase6_report),
        "autotune_report": str(autotune_report),
        "phase6_gate_passed": phase6_payload.get("phase6_gate_passed"),
        "autotune_tuned_skill_count": autotune_payload.get("tuned_skill_count"),
        "autotune_applied": autotune_payload.get("applied"),
    }

    final_path = workspace / f"{args.output_prefix}_phase7_report_cn.json"
    final_path.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[phase7] report:", final_path)
    print("[phase7] phase6_rc:", phase6_rc, "autotune_rc:", autotune_rc)

    if phase6_rc != 0:
        return phase6_rc
    return autotune_rc


if __name__ == "__main__":
    raise SystemExit(main())
