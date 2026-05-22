from __future__ import annotations

from typing import Any


def receipt_data_contract(row: dict[str, Any]) -> dict[str, Any]:
    if str(row.get("mode") or "") != "with_nexus":
        return {"status": "NOT_APPLICABLE", "missing": [], "reason": "non_nexus_arm"}
    coverage = row.get("expected_capability_receipt_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    missing = [str(item) for item in coverage.get("missing", []) or [] if str(item).strip()]
    return {
        "status": "DATA_CONTRACT_VIOLATION" if missing else "PASS",
        "missing": missing,
        "reason": "missing_expected_capability_receipts" if missing else "",
    }
