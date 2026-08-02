"""
Epistemic Workflow Benchmark v0 — CLI.

Usage:
  python -m nexus.research.epistemic_benchmark.cli validate-corpus
  python -m nexus.research.epistemic_benchmark.cli prepare-run --output <dir> --seed <seed>
  python -m nexus.research.epistemic_benchmark.cli import-observation --run-dir <dir> --input <obs.json>
  python -m nexus.research.epistemic_benchmark.cli evaluate --run-dir <dir> --json-output <r.json> [--markdown-output <r.md>]
  python -m nexus.research.epistemic_benchmark.cli verify-report --run-dir <dir> --input <report.json>

Success statuses:
  CORPUS_VALID
  RUN_PREPARED
  OBSERVATION_IMPORTED
  BENCHMARK_EVALUATED
  BENCHMARK_REPORT_VERIFIED

Oracle is never written to run directory.
"""
import argparse
import json
import sys
from typing import List, Optional


def _cmd_validate_corpus(args: argparse.Namespace) -> int:
    """Validate the synthetic corpus. Exits 0 on success."""
    from nexus.research.epistemic_benchmark.corpus import (
        get_corpus,
        get_all_oracles,
        REQUIRED_CASE_IDS,
    )
    from nexus.research.epistemic_benchmark.contracts import validate_case, validate_oracle

    cases = get_corpus()
    oracles = get_all_oracles()

    errors: List[str] = []

    case_ids = {c["case_id"] for c in cases}
    for required_id in REQUIRED_CASE_IDS:
        if required_id not in case_ids:
            errors.append(f"CASE_MISSING: {required_id}")

    for case in cases:
        errs = validate_case(case)
        if errs:
            errors.extend([f"CASE_{case.get('case_id', '?')}: {e}" for e in errs])

    for oracle in oracles:
        errs = validate_oracle(oracle)
        if errs:
            errors.extend([f"ORACLE_{oracle.get('case_id', '?')}: {e}" for e in errs])

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"CORPUS_VALID: {len(cases)} cases, {len(oracles)} oracles")
    return 0


def _cmd_prepare_run(args: argparse.Namespace) -> int:
    """Prepare a benchmark run. Does NOT write oracle or seed to public run directory."""
    from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run
    import os

    public_output_dir = args.output
    private_context_path = args.private_context
    seed = int(args.seed)
    corpus_version = getattr(args, "corpus_version", "v0")

    try:
        manifest = prepare_benchmark_run(
            public_output_dir=public_output_dir,
            private_context_path=private_context_path,
            seed=seed,
            corpus_version=corpus_version,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    run_id = manifest["benchmark_run_id"]
    case_count = manifest["case_count"]
    packet_count = len(manifest.get("packets", []))
    manifest_sha = manifest.get("run_manifest_sha256", "")

    # Safety: verify oracle NOT in run directory
    for root, dirs, files in os.walk(public_output_dir):
        for fname in files:
            if any(f in fname.lower() for f in ("oracle", "case_id_map", "expected_results", "answer_key")):
                print(f"SECURITY_VIOLATION: oracle-like file written to run dir: {fname}", file=sys.stderr)
                return 1

    # Output: no seed, no blinding key, no case IDs, no alias bindings, no oracle decisions
    print(
        f"RUN_PREPARED: run_id={run_id} cases={case_count} packets={packet_count} "
        f"manifest_sha256={manifest_sha} output={public_output_dir}"
    )
    return 0


def _cmd_validate_run(args: argparse.Namespace) -> int:
    """Validate public run integrity."""
    from nexus.research.epistemic_benchmark.packets import validate_public_run_integrity

    run_dir = args.run_dir

    try:
        ok, errors = validate_public_run_integrity(run_dir)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not ok:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"PUBLIC_RUN_VALID: run_dir={run_dir}")
    return 0


def _cmd_validate_private_context(args: argparse.Namespace) -> int:
    """Validate private scoring context against public run."""
    from nexus.research.epistemic_benchmark.packets import validate_private_scoring_context

    run_dir = args.run_dir
    private_context_path = args.private_context

    try:
        ok, errors = validate_private_scoring_context(run_dir, private_context_path)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if not ok:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"PRIVATE_CONTEXT_VALID: run_dir={run_dir}")
    return 0


def _cmd_import_observation(args: argparse.Namespace) -> int:
    """Import a single observation into a run directory."""
    from nexus.research.epistemic_benchmark.observations import import_observation_from_file

    run_dir = args.run_dir
    obs_path = args.input

    success, errors = import_observation_from_file(run_dir, obs_path)
    if not success:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"OBSERVATION_IMPORTED: {obs_path}")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    """Evaluate the benchmark and write JSON/Markdown reports."""
    from nexus.research.epistemic_benchmark.report import (
        build_benchmark_report,
        write_benchmark_report,
    )
    import os

    run_dir = args.run_dir
    json_output = args.json_output
    private_context_path = args.private_context
    markdown_output = getattr(args, "markdown_output", None)

    if markdown_output is None:
        # Default: same path as JSON but .md
        base = json_output.rsplit(".", 1)[0]
        markdown_output = base + ".md"

    try:
        report = build_benchmark_report(run_dir, private_context_path=private_context_path)
        write_benchmark_report(report, json_output, markdown_output)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # Safety: ensure oracle terms not present in stdout
    sha = report.get("report_sha256", "")
    print(f"BENCHMARK_EVALUATED: json={json_output} md={markdown_output} sha256={sha}")
    return 0


def _cmd_verify_report(args: argparse.Namespace) -> int:
    """Verify an existing benchmark report."""
    from nexus.research.epistemic_benchmark.report import verify_benchmark_report

    run_dir = args.run_dir
    report_path = args.input
    private_context_path = args.private_context

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception as e:
        print(f"ERROR: Cannot load report: {e}", file=sys.stderr)
        return 1

    valid, errors = verify_benchmark_report(report, run_dir, private_context_path=private_context_path)
    if not valid:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"BENCHMARK_REPORT_VERIFIED: {report_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m nexus.research.epistemic_benchmark.cli",
        description="Epistemic Workflow Benchmark v0 CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate-corpus
    subparsers.add_parser("validate-corpus", help="Validate the synthetic corpus")

    # prepare-run
    p_prepare = subparsers.add_parser("prepare-run", help="Prepare a benchmark run")
    p_prepare.add_argument("--output", required=True, help="Output directory for the public run")
    p_prepare.add_argument("--private-context", required=True, help="Output path for private context JSON")
    p_prepare.add_argument("--seed", required=True, help="Deterministic seed (integer)")
    p_prepare.add_argument("--corpus-version", default="v0", help="Corpus version (default: v0)")

    # validate-run
    p_vrun = subparsers.add_parser("validate-run", help="Validate public run integrity")
    p_vrun.add_argument("--run-dir", required=True, help="Public run directory")

    # validate-private-context
    p_vctx = subparsers.add_parser("validate-private-context", help="Validate private scoring context")
    p_vctx.add_argument("--run-dir", required=True, help="Public run directory")
    p_vctx.add_argument("--private-context", required=True, help="Path to private context JSON")

    # import-observation
    p_import = subparsers.add_parser("import-observation", help="Import a single observation")
    p_import.add_argument("--run-dir", required=True, help="Run directory")
    p_import.add_argument("--input", required=True, help="Path to observation JSON file")

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate benchmark and write reports")
    p_eval.add_argument("--run-dir", required=True, help="Run directory")
    p_eval.add_argument("--private-context", required=True, help="Path to private scoring context JSON")
    p_eval.add_argument("--json-output", required=True, help="Output path for JSON report")
    p_eval.add_argument("--markdown-output", default=None, help="Output path for Markdown report")

    # verify-report
    p_verify = subparsers.add_parser("verify-report", help="Verify a benchmark report")
    p_verify.add_argument("--run-dir", required=True, help="Run directory")
    p_verify.add_argument("--private-context", required=True, help="Path to private scoring context JSON")
    p_verify.add_argument("--input", required=True, help="Path to report JSON file")

    args = parser.parse_args(argv)

    if args.command == "validate-corpus":
        return _cmd_validate_corpus(args)
    elif args.command == "prepare-run":
        return _cmd_prepare_run(args)
    elif args.command == "import-observation":
        return _cmd_import_observation(args)
    elif args.command == "evaluate":
        return _cmd_evaluate(args)
    elif args.command == "verify-report":
        return _cmd_verify_report(args)
    elif args.command == "validate-run":
        return _cmd_validate_run(args)
    elif args.command == "validate-private-context":
        return _cmd_validate_private_context(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
