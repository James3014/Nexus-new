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

from nexus.contracts.claim_evidence_read_model import build_claim_evidence_read_model
from nexus.contracts.evidence_dataset import EVIDENCE_DATASET_MANIFEST_SCHEMA
from nexus.contracts.optimization_report import ClaimClass
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path(".nexus/reports/claim_evidence_read_model.json")


def build_read_model_from_evidence_manifest(
    *,
    input_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    manifest = _load_manifest(input_path)
    records = manifest.get("rows", [])
    if not isinstance(records, list):
        raise ValueError("invalid evidence manifest: rows must be a list")
    claim_class = str(manifest.get("claim_class") or ClaimClass.INTERNAL_DIAGNOSTIC.value)
    evidence_refs = _refs_from_manifest(manifest, key="evidence_refs")
    receipt_refs = _refs_from_manifest(manifest, key="receipt_refs")
    model = build_claim_evidence_read_model(
        claim_class=claim_class,
        records=[record for record in records if isinstance(record, dict)],
        evidence_bundle_refs=evidence_refs,
        receipt_refs=receipt_refs,
        sealed_evidence_required=bool(manifest.get("sealed_evidence_required", claim_class == ClaimClass.PUBLIC_READY.value)),
    )
    _attach_manifest_schema_gate(model, manifest)
    _attach_completion_gate(model, manifest)
    if not dry_run:
        _write(output_path, model)
    return _summary(model, input_path=input_path, output_path=output_path, dry_run=dry_run)


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid evidence manifest: expected object")
    return payload


def _refs_from_manifest(manifest: dict[str, Any], *, key: str) -> list[str]:
    refs: list[str] = []
    for row in manifest.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
        for ref in row.get(key, []) or []:
            ref = str(ref)
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def _attach_manifest_schema_gate(model: dict[str, Any], manifest: dict[str, Any]) -> None:
    manifest_schema = str(manifest.get("schema") or "")
    model["source_manifest_schema"] = manifest_schema
    model["source_manifest_status"] = (
        "PASS" if manifest_schema == EVIDENCE_DATASET_MANIFEST_SCHEMA else "LEGACY_OR_DIAGNOSTIC"
    )
    if model.get("claim_class") in {ClaimClass.RUNTIME_APPLY_REVIEW.value, ClaimClass.PUBLIC_READY.value}:
        if manifest_schema != EVIDENCE_DATASET_MANIFEST_SCHEMA:
            blockers = list(model.get("blockers", []) or [])
            blockers.append("invalid_or_missing_evidence_dataset_manifest_schema")
            model["blockers"] = sorted(set(blockers))
            model["status"] = "RETURN"


def _attach_completion_gate(model: dict[str, Any], manifest: dict[str, Any]) -> None:
    completion_status = str(manifest.get("completion_status") or "NOT_APPLICABLE").upper()
    completion_ref = str(manifest.get("completion_envelope_ref") or "")
    model["completion_status"] = completion_status
    model["completion_envelope_ref"] = completion_ref
    if model.get("claim_class") in {ClaimClass.RUNTIME_APPLY_REVIEW.value, ClaimClass.PUBLIC_READY.value}:
        if completion_status not in {"PASS", "NOT_APPLICABLE"}:
            blockers = list(model.get("blockers", []) or [])
            blockers.append("completion_envelope_not_pass")
            model["blockers"] = sorted(set(blockers))
            model["status"] = "RETURN"


def _summary(model: dict[str, Any], *, input_path: Path, output_path: Path, dry_run: bool) -> dict[str, Any]:
    return {
        "schema": "nexus_claim_evidence_read_model_export.v1",
        "status": str(model.get("status") or "RETURN"),
        "dry_run": bool(dry_run),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "source_manifest_schema": str(model.get("source_manifest_schema") or ""),
        "source_manifest_status": str(model.get("source_manifest_status") or ""),
        "completion_status": str(model.get("completion_status") or ""),
        "completion_envelope_ref": str(model.get("completion_envelope_ref") or ""),
        "claim_class": str(model.get("claim_class") or ""),
        "gate_count": len(model.get("gates", []) or []),
        "blocker_count": len(model.get("blockers", []) or []),
        "runtime_update_allowed": bool(model.get("runtime_update_allowed", False)),
        "public_benchmark_allowed": bool(model.get("public_benchmark_allowed", False)),
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a claim/evidence read model from an evidence dataset manifest.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    try:
        summary = build_read_model_from_evidence_manifest(
            input_path=args.input,
            output_path=output,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        summary = {
            "schema": "nexus_claim_evidence_read_model_export.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "input_path": str(args.input),
            "output_path": str(output),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
