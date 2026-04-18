from typing import Any, Dict, List, Optional, Tuple

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
    git_diff_empty: bool | None = None,         # NEW
    verify_commands_executed: bool | None = None, # NEW
) -> str | None:
    normalized_status = str(status).upper()
    if normalized_status not in {"PASS", "APPROVED"}:
        return None

    generated = _as_bool(patch_generated)
    applied = _as_bool(patch_apply_success)
    reason = str(no_change_reason or "").strip()

    # === NEW: 零變更完成偵測 ===
    # Agent 宣稱 PASS，但 git diff 為空 → 什麼都沒做
    if git_diff_empty is True and generated:
        return "empty_diff_with_claimed_patch"
        
    if generated and not applied:
        return "patch_apply_failed"
    if generated and applied and not _has_physical_proof(proof_type, proof_value):
        return "missing_physical_proof"
    if not generated and not reason:
        return "missing_no_change_reason"
    
    # === NEW: 自述式 reason 偵測 ===
    # Agent 塞了一個空洞的 no_change_reason 繞過檢查
    if not generated and reason:
        hollow_phrases = [
            "verified working", "already fixed", "no changes needed",
            "works as expected", "confirmed correct", "tested ok"
        ]
        reason_lower = reason.lower()
        if any(phrase in reason_lower for phrase in hollow_phrases):
            if not _has_physical_proof(proof_type, proof_value):
                return "hollow_no_change_claim"
    
    # === NEW: 未執行驗證命令 ===
    if verify_commands_executed is False:
        return "verification_commands_not_executed"
    
    return None

def _has_physical_proof(proof_type: str, proof_value: str) -> bool:
    t = str(proof_type or "").strip().lower()
    v = str(proof_value or "").strip()
    if not t or not v:
        return False
    return t in {"git_diff", "git_diff_checksum", "checksum", "pr_link", "test_output", "screenshot", "ci_link"}
