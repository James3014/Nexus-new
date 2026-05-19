#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_OVERLAY = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json")
DEFAULT_ORIGINAL_MAP = Path("docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json")
DEFAULT_SMOKE = Path("docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_CURRENT_SKILL_SSOT_CHECK_2026-05-20.json")

RECEIPT_CHAIN_KEYS = (
    "selected",
    "injected",
    "used",
    "evidence_present",
    "gate_passed",
    "outcome_contributed",
)


def build_current_skill_ssot(
    *,
    overlay: Mapping[str, Any],
    original_map: Mapping[str, Any],
    smoke: Mapping[str, Any],
) -> dict[str, Any]:
    primary_by_capability = overlay.get("primary_skill_by_capability", {})
    if not isinstance(primary_by_capability, Mapping):
        primary_by_capability = {}
    original_by_capability = _index_by(original_map.get("rows", []), "capability")
    smoke_by_capability = _index_by(smoke.get("cases", []), "capability")

    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for capability, skill_id in sorted((str(k), str(v)) for k, v in primary_by_capability.items()):
        original = original_by_capability.get(capability, {})
        smoke_case = smoke_by_capability.get(capability, {})
        row_blockers = _row_blockers(
            capability=capability,
            skill_id=skill_id,
            original=original,
            smoke_case=smoke_case,
        )
        blockers.extend(row_blockers)
        rows.append(
            {
                "capability": capability,
                "primary_skill_id": skill_id,
                "original_skill_name": str(original.get("original_skill_name") or ""),
                "original_source_path": str(original.get("original_source_path") or ""),
                "source_round_or_root": str(original.get("source_round_or_root") or ""),
                "decision": str(original.get("decision") or ""),
                "smoke_status": str(smoke_case.get("status") or ""),
                "expected_skill": str(smoke_case.get("expected_skill") or ""),
                "runtime_final_receipt_chain": _receipt_chain(smoke_case),
                "blocking_skill_mount_violations": list(smoke_case.get("blocking_skill_mount_violations") or []),
                "blockers": row_blockers,
            }
        )

    expected_count = int((overlay.get("summary") or {}).get("capability_count") or len(primary_by_capability))
    if len(rows) != expected_count:
        blockers.append(f"capability_count_mismatch:{len(rows)}!={expected_count}")
    if overlay.get("status") != "PASS":
        blockers.append("overlay_status_not_pass")
    if smoke.get("status") != "PASS":
        blockers.append("smoke_status_not_pass")
    status = "PASS" if rows and not blockers else "RETURN"
    return {
        "schema": "nexus.sf_current_skill_ssot_check.v1",
        "status": status,
        "runtime_update_allowed": bool(status == "PASS" and overlay.get("runtime_update_allowed")),
        "public_benchmark_allowed": False,
        "summary": {
            "capability_count": len(rows),
            "blocker_count": len(blockers),
            "runtime_update_allowed": bool(status == "PASS" and overlay.get("runtime_update_allowed")),
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "This SSOT check reconciles current SF overlay, original skill provenance, and runtime smoke receipts.",
            "It does not run or unlock public benchmark claims.",
            "Runtime consumers must still emit runtime-confirmed skill mount receipts on live routes.",
        ],
    }


def _index_by(items: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(items, list):
        return {}
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if isinstance(item, Mapping):
            indexed[str(item.get(key) or "")] = item
    return {key: value for key, value in indexed.items() if key}


def _row_blockers(
    *,
    capability: str,
    skill_id: str,
    original: Mapping[str, Any],
    smoke_case: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not skill_id:
        blockers.append(f"{capability}:missing_primary_skill")
    if not original:
        blockers.append(f"{capability}:{skill_id}:missing_original_skill_provenance")
    if original and str(original.get("primary_skill_id") or "") != skill_id:
        blockers.append(f"{capability}:{skill_id}:original_map_primary_mismatch")
    if not smoke_case:
        blockers.append(f"{capability}:{skill_id}:missing_smoke_case")
        return blockers
    if str(smoke_case.get("expected_skill") or "") != skill_id:
        blockers.append(f"{capability}:{skill_id}:smoke_expected_skill_mismatch")
    if str(smoke_case.get("status") or "") != "PASS":
        blockers.append(f"{capability}:{skill_id}:smoke_not_pass")
    violations = smoke_case.get("blocking_skill_mount_violations") or []
    if violations:
        blockers.append(f"{capability}:{skill_id}:blocking_skill_mount_violations")
    receipt_chain = _receipt_chain(smoke_case)
    for key in RECEIPT_CHAIN_KEYS:
        if receipt_chain.get(key) is not True:
            blockers.append(f"{capability}:{skill_id}:receipt_chain_missing_{key}")
    return blockers


def _receipt_chain(smoke_case: Mapping[str, Any]) -> dict[str, bool]:
    chain = smoke_case.get("runtime_final_receipt_chain", {})
    chain = chain if isinstance(chain, Mapping) else {}
    return {key: bool(chain.get(key, False)) for key in RECEIPT_CHAIN_KEYS}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the current SF capability-skill SSOT check.")
    parser.add_argument("--overlay", default=str(DEFAULT_OVERLAY), type=Path)
    parser.add_argument("--original-map", default=str(DEFAULT_ORIGINAL_MAP), type=Path)
    parser.add_argument("--smoke", default=str(DEFAULT_SMOKE), type=Path)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = build_current_skill_ssot(
        overlay=_load_json(args.overlay),
        original_map=_load_json(args.original_map),
        smoke=_load_json(args.smoke),
    )
    if not args.dry_run:
        _write(args.output, manifest)
    print(json.dumps({"status": manifest["status"], **manifest["summary"]}, ensure_ascii=False, sort_keys=True))
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
