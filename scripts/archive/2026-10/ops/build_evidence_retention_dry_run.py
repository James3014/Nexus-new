#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.contracts.evidence_retention import (
    build_evidence_retention_dry_run,
    current_evidence_paths_from_manifest,
)
from scripts.ops.report_output import resolve_report_output


def _json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tracked_paths(root: Path, reports_root: Path) -> tuple[str, ...]:
    proc = subprocess.run(
        ["git", "ls-files", "--", str(reports_root)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line.strip() for line in proc.stdout.splitlines() if line.strip())


def _report_paths(reports_root: Path) -> tuple[str, ...]:
    resolved_root = reports_root if reports_root.is_absolute() else PROJECT_ROOT / reports_root
    if not resolved_root.exists():
        return ()
    return tuple(
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted(resolved_root.iterdir())
        if path.is_file() and path.suffix in {".json", ".md"}
    )


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a dry-run evidence retention manifest.")
    parser.add_argument("--reports-root", default="docs/reports")
    parser.add_argument(
        "--current-manifest",
        default="docs/reports/NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json",
    )
    parser.add_argument("--catalog-pinned", action="append", default=[])
    parser.add_argument("--archive-root", default="docs/reports/archive/optimization-retention-dry-run")
    parser.add_argument("--output", default="", type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    args = parser.parse_args(argv)

    reports_root = Path(args.reports_root)
    current_manifest = _json(Path(args.current_manifest))
    payload = build_evidence_retention_dry_run(
        _report_paths(reports_root),
        tracked_paths=_tracked_paths(PROJECT_ROOT, reports_root),
        current_evidence_paths=current_evidence_paths_from_manifest(current_manifest),
        catalog_pinned_paths=tuple(args.catalog_pinned),
        archive_root=args.archive_root,
    )
    output_arg = str(args.output)
    output_dir_arg = str(args.output_dir)
    output = resolve_report_output(
        Path("NEXUS_OPT_EVIDENCE_RETENTION_DRY_RUN_2026-05-20.json"),
        output=args.output if output_arg and output_arg != "." else None,
        output_dir=args.output_dir if output_dir_arg and output_dir_arg != "." else None,
    )
    if (output_arg and output_arg != ".") or (output_dir_arg and output_dir_arg != "."):
        _write(output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "path_count": payload["summary"]["path_count"],
                "archive_candidate_count": payload["summary"]["archive_candidate_count"],
                "tracked_keep_count": payload["summary"]["tracked_keep_count"],
                "current_evidence_keep_count": payload["summary"]["current_evidence_keep_count"],
                "pinned_by_catalog_count": payload["summary"]["pinned_by_catalog_count"],
                "blocker_count": payload["summary"]["blocker_count"],
                "output": str(output)
                if (output_arg and output_arg != ".") or (output_dir_arg and output_dir_arg != ".")
                else "",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
