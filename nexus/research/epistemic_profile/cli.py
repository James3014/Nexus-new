"""
CLI for Nexus Epistemic Research Profile Exporter Verification.
"""

import argparse
import json
import sys
from pathlib import Path

from nexus.research.epistemic_profile.io import (
    verify_epistemic_profile_export,
    write_epistemic_receipt,
)


def cmd_verify_export(args: argparse.Namespace) -> int:
    try:
        res = verify_epistemic_profile_export(args.input)
        res_dict = res.to_dict()

        output_summary = {
            "status": res.status.value,
            "records_checked": res.records_checked,
            "blockers": list(res.blockers),
            "runtime_update_allowed": False,
            "public_claim_allowed": False,
            "public_benchmark_allowed": False,
            "production_ready": False,
            "integration_approved": False,
        }

        if res.status.value != "PASS":
            print(json.dumps(output_summary, indent=2), file=sys.stderr)
            return 1

        if getattr(args, "output", None):
            write_epistemic_receipt(res, args.output)

        print(json.dumps(output_summary, indent=2))
        return 0
    except Exception as e:
        err_out = {
            "status": "RETURN",
            "error": str(e),
            "runtime_update_allowed": False,
            "public_claim_allowed": False,
            "public_benchmark_allowed": False,
            "production_ready": False,
            "integration_approved": False,
        }
        print(json.dumps(err_out, indent=2), file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Nexus Epistemic Profile CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ve = subparsers.add_parser("verify-export")
    p_ve.add_argument("--input", required=True, help="Path to research ledger epistemic export JSON")
    p_ve.add_argument("--output", help="Optional path to save verification receipt JSON")

    args = parser.parse_args()

    if args.command == "verify-export":
        sys.exit(cmd_verify_export(args))


if __name__ == "__main__":
    main()
