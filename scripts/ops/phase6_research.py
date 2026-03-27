#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.research.phase6 import compute_phase6_metrics
from nexus.research.phase6 import gate_passed
from nexus.research.phase6 import load_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Phase 6 research loop and emit a delivery-grade report.",
    )
    parser.add_argument("--workspace", required=True, help="Autoresearch workspace path")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--proof-ratio-min", type=float, default=95.0)
    parser.add_argument("--output-prefix", default="phase6")
    parser.add_argument("--skip-autopilot", action="store_true")
    return parser


def _run(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=str(cwd), text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def main() -> int:
    args = build_parser().parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists():
        print(f"[phase6] workspace not found: {workspace}")
        return 2

    autopilot = workspace / "autopilot.py"
    hardening = workspace / "formal_research_hardening.py"
    summary_jsonl = workspace / "round_summary.jsonl"
    if not autopilot.exists() or not hardening.exists():
        print("[phase6] missing autopilot.py or formal_research_hardening.py")
        return 2

    if not args.skip_autopilot:
        try:
            _run([sys.executable, str(autopilot), "--rounds", str(args.rounds)], workspace)
        except RuntimeError:
            # Backward compatibility for older autopilot without --rounds argument.
            _run([sys.executable, str(autopilot)], workspace)

    if not summary_jsonl.exists():
        print("[phase6] round_summary.jsonl not found after autopilot run")
        return 2

    phase6_out = workspace / f"{args.output_prefix}_out"
    _run(
        [
            sys.executable,
            str(hardening),
            "--input",
            str(summary_jsonl),
            "--out",
            str(phase6_out),
            "--proof-ratio-min",
            str(args.proof_ratio_min),
        ],
        workspace,
    )

    rows = load_jsonl(summary_jsonl)
    metrics = compute_phase6_metrics(rows)
    passed = gate_passed(metrics)

    gate_eval_path = phase6_out / "gate_eval.json"
    gate_eval = {}
    if gate_eval_path.exists():
        gate_eval = json.loads(gate_eval_path.read_text(encoding="utf-8"))

    report = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "rounds": args.rounds,
        "proof_ratio_min_threshold": args.proof_ratio_min,
        "metrics": {
            "mismatch_lt_0.5_last20": metrics.mismatch_lt_0_5_last20,
            "mismatch_max_last20": round(metrics.mismatch_max_last20, 3),
            "proof_ratio_min_last20": round(metrics.proof_ratio_min_last20, 2),
            "best_precision": round(metrics.best_precision, 4),
        },
        "gate_eval": gate_eval,
        "phase6_gate_passed": passed,
    }

    report_path = workspace / f"{args.output_prefix}_research_report_cn.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[phase6] report:", report_path)
    print("[phase6] phase6_gate_passed:", str(passed).lower())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
