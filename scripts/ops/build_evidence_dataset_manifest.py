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
from nexus.contracts.evidence_sealing import seal_evidence
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
    rows = _load_jsonl(input_path)
    records = [
        evidence_record_from_benchmark_row(
            _prepare_benchmark_row_for_claim(row, claim_class=claim_class, index=index),
            source_path=str(input_path),
            claim_class=claim_class,
        )
        for index, row in enumerate(rows)
    ]
    manifest = _seal_manifest_rows(
        build_evidence_dataset_manifest(records, source_path=str(input_path), claim_class=claim_class)
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
    manifest = _seal_manifest_rows(
        build_evidence_dataset_manifest(
            records,
            source_path=str(input_path),
            claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
        )
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


def _prepare_benchmark_row_for_claim(
    row: dict[str, Any],
    *,
    claim_class: ClaimClass | str,
    index: int,
) -> dict[str, Any]:
    prepared = dict(row)
    if _claim_class(claim_class) != ClaimClass.PUBLIC_READY:
        return prepared
    if str(prepared.get("evidence_seal_status") or "").upper() == "PASS" and str(
        prepared.get("evidence_hash_status") or ""
    ).upper() == "PASS":
        return prepared
    evidence_id = str(prepared.get("task_id") or prepared.get("benchmark_id") or f"benchmark-row-{index}")
    seal = seal_evidence(prepared, evidence_id=evidence_id)
    prepared["evidence_seal_status"] = seal["evidence_seal_status"]
    prepared["evidence_hash_status"] = seal["evidence_hash_status"]
    prepared["evidence_sha256"] = seal["sha256"]
    prepared["evidence_seal_ref"] = f"sha256:{seal['sha256']}"
    return prepared


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


def _seal_manifest_rows(manifest: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in manifest.get("rows", []) if isinstance(row, dict)]
    sealed_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        sealed = dict(row)
        if str(sealed.get("evidence_seal_status") or "NOT_APPLICABLE").upper() == "NOT_APPLICABLE":
            seal = seal_evidence(sealed, evidence_id=str(sealed.get("record_id") or f"record-{index}"))
            sealed["evidence_seal_status"] = seal["evidence_seal_status"]
            sealed["evidence_hash_status"] = seal["evidence_hash_status"]
            sealed["evidence_sha256"] = seal["sha256"]
            sealed["evidence_seal_ref"] = f"sha256:{seal['sha256']}"
        sealed_rows.append(sealed)
    manifest = dict(manifest)
    manifest["rows"] = sealed_rows
    manifest["evidence_sealed_record_count"] = sum(
        1 for row in sealed_rows if str(row.get("evidence_seal_status") or "").upper() == "PASS"
    )
    return manifest


def _claim_class(value: ClaimClass | str) -> ClaimClass:
    if isinstance(value, ClaimClass):
        return value
    return ClaimClass(str(value))


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
