#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_OPTIMIZATION_ARTIFACT_INDEX_2026-05-20.md")
DEFAULT_ARTIFACTS = (
    "nexus/contracts/retrieval_receipt.py",
    "nexus/contracts/claim_evidence_read_model.py",
    "nexus/contracts/context_assembly.py",
    "nexus/contracts/route_context_seam_freeze.py",
    "nexus/contracts/hard_gate_compatibility.py",
    "scripts/ops/build_claim_evidence_read_model.py",
    "scripts/ops/build_context_assembly_contract.py",
    "scripts/ops/build_route_context_seam_freeze.py",
    "scripts/ops/build_evidence_dataset_manifest.py",
    "scripts/ops/check_optimization_artifact_hygiene.py",
    "scripts/ops/check_route_context_seam_freeze.py",
    "nexus/contracts/sf_replacement.py",
    "docs/reports/NEXUS_OPT_EVIDENCE_RETENTION_DRY_RUN_2026-05-20.json",
    "docs/plans/NEXUS_OPTIMIZATION_CONTRACT_AND_RETENTION_2026-05-19.md",
    "docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md",
)


def build_optimization_artifact_index(
    *,
    artifact_paths: Iterable[str] = DEFAULT_ARTIFACTS,
    output_path: Path = DEFAULT_OUTPUT,
    title: str = "Nexus Optimization Artifact Index - 2026-05-20",
    dry_run: bool = False,
) -> dict[str, object]:
    paths = tuple(dict.fromkeys(str(path) for path in artifact_paths if str(path).strip()))
    markdown = _render_index(title=title, artifact_paths=paths)
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    return {
        "schema": "nexus_optimization_artifact_index_export.v1",
        "status": "PASS" if paths else "RETURN",
        "dry_run": bool(dry_run),
        "output_path": str(output_path),
        "artifact_count": len(paths),
    }


def _render_index(*, title: str, artifact_paths: tuple[str, ...]) -> str:
    lines = [
        f"# {title}",
        "",
        "## Scope",
        "- Internal optimization evidence and gate artifacts only.",
        "- Not a runtime apply approval.",
        "- Not a public benchmark claim.",
        "",
        "## Artifacts",
    ]
    for path in artifact_paths:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "- Retrieval receipts explain retrieval selection and scoring.",
            "- Claim/evidence read models summarize gates without mutating runtime policy.",
            "- Hygiene hooks validate artifacts and must not delete files.",
            "- SF replacement gates may approve review candidates but do not unlock public benchmark claims.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Nexus optimization artifact index.")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) and str(args.output_dir) != "." else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    artifacts = tuple(args.artifact) if args.artifact else DEFAULT_ARTIFACTS
    summary = build_optimization_artifact_index(
        artifact_paths=artifacts,
        output_path=output,
        dry_run=args.dry_run,
    )
    print(summary)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
