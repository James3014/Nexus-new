from nexus.core.phantom_detect import detect_inconclusive_success

def compute_phantom_success(rows):
    """
    🧮 計算「幻覺成功」與「不明成功」的統計量。
    用於 CI Gate 攔截缺乏實體證據的 PASS。
    """
    phantom_count = 0
    inconclusive_count = 0
    for row in rows:
        sig = detect_inconclusive_success(
            status=row.get("status", ""),
            patch_generated=row.get("patch_generated", ""),
            patch_apply_success=row.get("patch_apply_success", ""),
            no_change_reason=row.get("no_change_reason", ""),
            proof_type=row.get("proof_type", ""),
            proof_value=row.get("proof_value", ""),
        )
        if sig == "patch_apply_failed":
            phantom_count += 1
        elif sig in {"missing_physical_proof", "missing_no_change_reason"}:
            inconclusive_count += 1
            
    return {
        "phantom_count": phantom_count,
        "inconclusive_count": inconclusive_count
    }
