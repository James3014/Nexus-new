"""分析 R↔A 循環的根因，讓戰甲記住「為什麼會循環」"""

CYCLE_CAUSES = {
    "phantom_proof":     "模型聲稱修好但缺乏物理證明",
    "patch_apply_fail":  "Patch 生成但無法套用到目標檔案",
    "scope_drift":       "修復偏離原始任務範圍",
    "insufficient_diag": "診斷不夠深入導致方向錯誤",
    "unknown":           "無法分類的循環原因",
}

def analyze_cycle(rejection_history: list) -> dict:
    """
    輸入：rejection_history = ["phantom:missing_physical_proof", "rejected:REJECTED", ...]
    輸出：{"cycle_count": 3, "root_cause": "phantom_proof", "desc": "模型聲稱修好但缺乏物理證明"}
    """
    if not rejection_history:
        return {"cycle_count": 0, "root_cause": "", "desc": "無循環"}

    phantom = sum(1 for r in rejection_history 
                  if "proof" in str(r).lower() or "phantom" in str(r).lower())
    patch = sum(1 for r in rejection_history if "patch" in str(r).lower())

    if phantom >= len(rejection_history) * 0.5:
        cause = "phantom_proof"
    elif patch > 0:
        cause = "patch_apply_fail"
    elif len(rejection_history) >= 3:
        cause = "insufficient_diag"
    else:
        cause = "scope_drift"

    return {
        "cycle_count": len(rejection_history),
        "root_cause": cause,
        "desc": CYCLE_CAUSES.get(cause, "未知"),
    }
