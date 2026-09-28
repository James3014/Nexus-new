#!/usr/bin/env python3
"""Replayable physical benchmark for the experimental Apple FM worker pool."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Add repo root to path for direct script execution, matching the provider-adoption runner.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from nexus.calibration.provider_adoption.apple_fm_adapter import AppleFMCandidateAdapter
from nexus.calibration.provider_adoption.apple_fm_worker_pool import (
    NETWORK_DENY_PROFILE,
    AppleFMReadOnlyTask,
    AppleFMReadOnlyWorkerPool,
    AppleFMTaskKind,
)


def _tasks(count: int) -> tuple[list[AppleFMReadOnlyTask], dict[str, str]]:
    templates = (
        (
            AppleFMTaskKind.CLASSIFICATION,
            "Classify this provider event. Options: AUTH_ERROR, RATE_LIMIT, "
            "PROVIDER_TIMEOUT, MODEL_NOT_FOUND, TRANSPORT_FAILURE, UNKNOWN. "
            "Event: HTTP 429 Too Many Requests was returned because quota was exhausted. "
            "Return only the label.",
            "RATE_LIMIT",
        ),
        (
            AppleFMTaskKind.CLASSIFICATION,
            "Classify this provider event. Options: AUTH_ERROR, RATE_LIMIT, "
            "PROVIDER_TIMEOUT, MODEL_NOT_FOUND, TRANSPORT_FAILURE, UNKNOWN. "
            "Event: no provider response arrived before the 30 second deadline. "
            "Return only the label.",
            "PROVIDER_TIMEOUT",
        ),
        (
            AppleFMTaskKind.LITERAL_EXTRACTION,
            "Return only the integer HTTP status code. "
            "Event: the provider returned HTTP 503 Service Unavailable.",
            "503",
        ),
        (
            AppleFMTaskKind.LITERAL_EXTRACTION,
            "Return only the integer retry count. "
            "Event: the request failed after exactly 3 retries.",
            "3",
        ),
    )
    tasks: list[AppleFMReadOnlyTask] = []
    expected: dict[str, str] = {}
    for index in range(count):
        kind, prompt, truth = templates[index % len(templates)]
        task_id = f"P-{index + 1:03d}"
        tasks.append(AppleFMReadOnlyTask(task_id, kind, prompt))
        expected[task_id] = truth
    return tasks, expected


def _verify_network_denial() -> dict[str, object]:
    direct = subprocess.run(
        [
            "/usr/bin/curl",
            "--max-time",
            "3",
            "-sS",
            "https://example.com",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    sandboxed = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-p",
            NETWORK_DENY_PROFILE,
            "/usr/bin/curl",
            "--max-time",
            "3",
            "-sS",
            "https://example.com",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    verified = direct.returncode == 0 and sandboxed.returncode != 0
    return {
        "direct_control_exit_code": direct.returncode,
        "direct_control_reachable": direct.returncode == 0,
        "sandboxed_control_exit_code": sandboxed.returncode,
        "network_denial_verified": verified,
        "sandboxed_stderr": sandboxed.stderr.strip()[:300],
    }


def _git_identity() -> dict[str, str]:
    def resolve(revision: str) -> str:
        completed = subprocess.run(
            ["git", "rev-parse", revision],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return completed.stdout.strip()

    return {
        "source_commit": resolve("HEAD"),
        "source_tree": resolve("HEAD^{tree}"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--requests", type=int, default=16)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    if args.requests < 1:
        raise SystemExit("--requests must be >= 1")

    network = _verify_network_denial()
    if not network["network_denial_verified"]:
        print(json.dumps({"status": "BLOCKED", "network_control": network}, indent=2))
        return 2

    source = _git_identity()
    candidate_identity = AppleFMCandidateAdapter().inspect_identity().to_dict()
    tasks, expected = _tasks(args.requests)
    receipt = AppleFMReadOnlyWorkerPool().run_batch(tasks, concurrency=args.concurrency)
    exact = {
        result.task_id: result.ok and result.output_text == expected[result.task_id]
        for result in receipt.results
    }
    payload = {
        "schema": "nexus.provider_experiment.apple_fm_worker_pool_benchmark.v1",
        "status": "PASS" if all(exact.values()) else "FAIL",
        **source,
        "candidate_identity": candidate_identity,
        "network_control": network,
        "exact_correct": sum(exact.values()),
        "exact_total": len(exact),
        "receipt": receipt.to_dict(),
    }
    if args.output_json:
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
