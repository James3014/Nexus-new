#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import write_json
from nexus.learning.zero_trust_v2_physical_sandbox import run_macos_sandbox_probe
from nexus.learning.zero_trust_v2_sandbox import validate_sandbox_attestation


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_SANDBOX_PROBE_2026-05-21.json")


def build_zero_trust_v2_sandbox_probe(*, command: list[str], signing_secret: str) -> dict:
    probe = run_macos_sandbox_probe(command, signing_secret=signing_secret)
    verdict = validate_sandbox_attestation(probe["sandbox_attestation"])
    return {
        "schema": "nexus.zero_trust_v2.sandbox_probe_report.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "summary": {
            "probe_status": probe["status"],
            "promotion_eligible": probe["promotion_eligible"] and verdict["status"] == "PASS",
            "sandbox_mode": probe["sandbox_attestation"]["sandbox_mode"],
            "attestation_validation_status": verdict["status"],
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "probe": probe,
        "attestation_validation": verdict,
        "claim_boundary": [
            "This probe validates runner-owned sandbox attestation shape only.",
            "A blocked probe must not produce V2 promotion credit.",
            "The signing secret is consumed by the runner observer and is not forwarded to the child process.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 physical sandbox probe report.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--command", nargs="+", default=["/bin/echo", "nexus-zero-trust-v2-sandbox-probe"])
    args = parser.parse_args(argv)
    signing_secret = os.environ.get("NEXUS_V2_RUNNER_SIGNING_SECRET", "local-nonproduction-v2-sandbox-probe")
    result = build_zero_trust_v2_sandbox_probe(command=args.command, signing_secret=signing_secret)
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
