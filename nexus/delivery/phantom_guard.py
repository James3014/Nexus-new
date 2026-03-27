from __future__ import annotations

from typing import Any


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == "true"


def compute_phantom_success(rows: list[dict[str, Any]]) -> dict[str, Any]:
    phantom_count = 0
    inconclusive_count = 0
    total = len(rows)

    if total == 0:
        return {"phantom_count": 0, "inconclusive_count": 0, "phantom_rate": 0.0}

    for row in rows:
        status = str(row.get("status", "")).upper()
        patch_generated = _as_bool(row.get("patch_generated"))
        patch_apply_success = _as_bool(row.get("patch_apply_success"))
        no_change_reason = str(row.get("no_change_reason", "")).strip()
        proof_type = str(row.get("proof_type", "")).strip()
        proof_value = str(row.get("proof_value", "")).strip()

        if status == "PASS" and patch_generated and not patch_apply_success:
            phantom_count += 1
        elif status == "PASS" and patch_generated and patch_apply_success and not _has_physical_proof(proof_type, proof_value):
            inconclusive_count += 1
        elif status == "PASS" and not patch_generated and not no_change_reason:
            inconclusive_count += 1

    return {
        "phantom_count": phantom_count,
        "inconclusive_count": inconclusive_count,
        "phantom_rate": (phantom_count / total) * 100,
    }


def detect_inconclusive_success(
    *,
    status: str,
    patch_generated: Any,
    patch_apply_success: Any,
    no_change_reason: str,
    proof_type: str = "",
    proof_value: str = "",
) -> str | None:
    normalized_status = str(status).upper()
    if normalized_status not in {"PASS", "APPROVED"}:
        return None

    generated = _as_bool(patch_generated)
    applied = _as_bool(patch_apply_success)
    reason = str(no_change_reason or "").strip()

    if generated and not applied:
        return "patch_apply_failed"
    if generated and applied and not _has_physical_proof(proof_type, proof_value):
        return "missing_physical_proof"
    if not generated and not reason:
        return "missing_no_change_reason"
    return None


def _has_physical_proof(proof_type: str, proof_value: str) -> bool:
    t = str(proof_type or "").strip().lower()
    v = str(proof_value or "").strip()
    if not t or not v:
        return False
    return t in {"git_diff", "git_diff_checksum", "checksum"}
