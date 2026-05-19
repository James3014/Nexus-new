#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.contracts.evidence_dataset import (
    build_evidence_dataset_manifest,
    evidence_record_from_benchmark_row,
    evidence_record_from_sf_smoke_case,
)
from nexus.contracts.optimization_report import ClaimClass
from scripts.ops.build_claim_evidence_read_model import build_read_model_from_evidence_manifest
from scripts.ops.report_output import resolve_report_output


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"invalid evidence row {line_number}: expected object")
        rows.append(row)
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid evidence source: expected object")
    return payload


def build_manifest_from_benchmark_jsonl(
    *,
    input_path: Path,
    output_path: Path,
    claim_class: ClaimClass | str = ClaimClass.INTERNAL_DIAGNOSTIC,
    read_model_output_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    records = [
        evidence_record_from_benchmark_row(row, source_path=str(input_path), claim_class=claim_class)
        for row in _load_jsonl(input_path)
    ]
    manifest = build_evidence_dataset_manifest(records, source_path=str(input_path), claim_class=claim_class)
    if not dry_run:
        _write(output_path, manifest)
    return _summary(
        manifest,
        output_path=output_path,
        read_model_summary=_optional_read_model(
            output_path=output_path,
            read_model_output_path=read_model_output_path,
            dry_run=dry_run,
        ),
        dry_run=dry_run,
    )


def build_manifest_from_sf_smoke_json(
    *,
    input_path: Path,
    output_path: Path,
    read_model_output_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = _load_json(input_path)
    cases = payload.get("cases", []) or payload.get("rows", []) or []
    if not isinstance(cases, list):
        raise ValueError("invalid sf smoke source: cases must be a list")
    records = [
        evidence_record_from_sf_smoke_case(case, source_path=str(input_path))
        for case in cases
        if isinstance(case, dict)
    ]
    manifest = build_evidence_dataset_manifest(
        records,
        source_path=str(input_path),
        claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
    )
    if not dry_run:
        _write(output_path, manifest)
    return _summary(
        manifest,
        output_path=output_path,
        read_model_summary=_optional_read_model(
            output_path=output_path,
            read_model_output_path=read_model_output_path,
            dry_run=dry_run,
        ),
        dry_run=dry_run,
    )


def _summary(
    manifest: dict[str, Any],
    *,
    output_path: Path,
    dry_run: bool,
    read_model_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "nexus_evidence_dataset_manifest_export.v1",
        "status": "PASS" if manifest.get("blocker_count", 0) == 0 else "RETURN",
        "dry_run": bool(dry_run),
        "output_path": str(output_path),
        "record_count": int(manifest.get("record_count") or 0),
        "blocker_count": int(manifest.get("blocker_count") or 0),
        "runtime_update_allowed": bool(manifest.get("runtime_update_allowed")),
        "public_benchmark_allowed": bool(manifest.get("public_benchmark_allowed")),
        "provider_token_cleanliness_counts": dict(manifest.get("provider_token_cleanliness_counts", {}) or {}),
        "read_model": read_model_summary,
    }


def _optional_read_model(
    *,
    output_path: Path,
    read_model_output_path: Path | None,
    dry_run: bool,
) -> dict[str, Any] | None:
    if read_model_output_path is None:
        return None
    if dry_run:
        return {
            "schema": "nexus_claim_evidence_read_model_export.v1",
            "status": "PASS",
            "dry_run": True,
            "input_path": str(output_path),
            "output_path": str(read_model_output_path),
        }
    return build_read_model_from_evidence_manifest(
        input_path=output_path,
        output_path=read_model_output_path,
        dry_run=False,
    )


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a normalized Nexus evidence dataset manifest.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-kind", choices=("benchmark-jsonl", "sf-smoke-json"), required=True)
    parser.add_argument("--claim-class", default=ClaimClass.INTERNAL_DIAGNOSTIC.value)
    parser.add_argument("--read-model-output", default=None, type=Path)
    parser.add_argument("--read-model-output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    read_model_output_dir = args.read_model_output_dir if str(args.read_model_output_dir) else None
    read_model_output = None
    if args.read_model_output is not None or read_model_output_dir is not None:
        read_model_output = resolve_report_output(
            Path("claim_evidence_read_model.json"),
            output=args.read_model_output,
            output_dir=read_model_output_dir or args.output.parent,
        )

    try:
        if args.source_kind == "benchmark-jsonl":
            summary = build_manifest_from_benchmark_jsonl(
                input_path=args.input,
                output_path=args.output,
                claim_class=args.claim_class,
                read_model_output_path=read_model_output,
                dry_run=args.dry_run,
            )
        else:
            summary = build_manifest_from_sf_smoke_json(
                input_path=args.input,
                output_path=args.output,
                read_model_output_path=read_model_output,
                dry_run=args.dry_run,
            )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        summary = {
            "schema": "nexus_evidence_dataset_manifest_export.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "output_path": str(args.output),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
