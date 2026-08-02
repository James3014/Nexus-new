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
from nexus.research.epistemic_profile.report import (
    build_epistemic_review_report,
    render_epistemic_review_markdown,
    verify_epistemic_review_report,
    write_epistemic_review_report,
)


def cmd_verify_export(args: argparse.Namespace) -> int:
    try:
        res = verify_epistemic_profile_export(args.input)
        res_dict = res.to_dict()

        output_summary = {
            "status": res.status.value,
            "records_checked": res.records_checked,
            "blockers": list(res.blockers),
            "source_export_id": res.source_export_id,
            "source_export_sha256": res.source_export_sha256,
            "source_state_manifest_sha256": res.source_state_manifest_sha256,
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
            write_epistemic_receipt(res, args.output, source_export_path=args.input)

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


def cmd_render_report(args: argparse.Namespace) -> int:
    try:
        report = write_epistemic_review_report(
            source_export=args.input,
            json_output_path=args.json_output,
            markdown_output_path=args.markdown_output,
        )
        output_summary = {
            "status": "REVIEW_READY",
            "source_export_id": report.get("source", {}).get("export_id", ""),
            "source_export_sha256": report.get("source", {}).get("export_sha256", ""),
            "report_sha256": report.get("report_sha256", ""),
            "claim_count": report.get("claim_count", 0),
            "records_checked": report.get("records_checked", 0),
            "public_claim_allowed": False,
            "production_ready": False,
        }
        print(json.dumps(output_summary, indent=2))
        return 0
    except Exception as e:
        err_out = {
            "status": "RETURN",
            "error": str(e),
            "public_claim_allowed": False,
            "production_ready": False,
        }
        print(json.dumps(err_out, indent=2), file=sys.stderr)
        return 1


def cmd_verify_report(args: argparse.Namespace) -> int:
    try:
        import json as _json
        with open(args.input, "r", encoding="utf-8") as f:
            report = _json.load(f)
        result = verify_epistemic_review_report(report, args.source_export)
        if result.get("status") != "REVIEW_VERIFIED":
            print(json.dumps(result, indent=2), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        err_out = {"status": "REVIEW_INVALID", "error": str(e)}
        print(json.dumps(err_out, indent=2), file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Nexus Epistemic Profile CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ve = subparsers.add_parser("verify-export")
    p_ve.add_argument("--input", required=True, help="Path to research ledger epistemic export JSON")
    p_ve.add_argument("--output", help="Optional path to save verification receipt JSON")

    p_rr = subparsers.add_parser("render-report")
    p_rr.add_argument("--input", required=True, help="Path to research ledger epistemic export JSON")
    p_rr.add_argument("--json-output", required=True, help="Path to write review report JSON")
    p_rr.add_argument("--markdown-output", required=True, help="Path to write review report Markdown")

    p_vr = subparsers.add_parser("verify-report")
    p_vr.add_argument("--input", required=True, help="Path to review report JSON")
    p_vr.add_argument("--source-export", required=True, help="Path to source export JSON")

    args = parser.parse_args()

    if args.command == "verify-export":
        sys.exit(cmd_verify_export(args))
    elif args.command == "render-report":
        sys.exit(cmd_render_report(args))
    elif args.command == "verify-report":
        sys.exit(cmd_verify_report(args))


if __name__ == "__main__":
    main()
