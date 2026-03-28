#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest
from nexus.delivery.models import TaskLevel
from nexus.delivery.report import write_report_bundle


def _read_lines(path: str | None) -> list[str]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Missing file: {file_path}")
    return [
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Nexus completion verification and emit delivery reports.",
    )
    parser.add_argument("--task-name", required=True)
    parser.add_argument(
        "--task-level",
        required=True,
        choices=[level.value for level in TaskLevel],
    )
    parser.add_argument("--verify", action="append", default=[])
    parser.add_argument("--verify-file")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--artifact-file")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--output-dir", default="logs/delivery")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    verification_commands = list(args.verify) + _read_lines(args.verify_file)
    artifact_paths = [Path(path) for path in args.artifact] + [
        Path(path) for path in _read_lines(args.artifact_file)
    ]
    if not verification_commands:
        parser.error("at least one verification command is required")

    request = CompletionRequest(
        task_name=args.task_name,
        task_level=TaskLevel(args.task_level),
        verification_commands=verification_commands,
        artifact_paths=artifact_paths,
        cwd=Path(args.cwd).resolve(),
    )
    result = evaluate_completion(request)
    json_path, md_path = write_report_bundle(result, Path(args.output_dir))

    print(f"[completion-gate] status={result.status.value}")
    print(f"[completion-gate] gate_passed={str(result.gate_passed).lower()}")
    print(f"[completion-gate] json={json_path}")
    print(f"[completion-gate] report={md_path}")
    return 0 if result.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
