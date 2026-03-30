from typing import Any

def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() == "true"

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
