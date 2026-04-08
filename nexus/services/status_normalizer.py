import json
from typing import Dict, Any

class StatusNormalizer:
    """
    归 Work Order C: State Normalization Layer
    將所有狀態、Phase、命名異形歸一化，防止 UI 與 Agent 理解分裂。
    """

    MAPPING = {
        # Audit Status
        "A_PASSED": "APASSED",
        "AUDIT_PASS": "APASSED",
        "PASS": "APASSED",
        "audit_passed": "APASSED",
        
        # Pipeline Status
        "PDRAC": "pxdrac",
        "PXDRAC": "pxdrac",
        
        # Release Status
        "release-ready": "releaseReady",
        "can_publish": "canPublish",
        "READY_TO_SHIP": "releaseReady",
        
        # Terminal States
        "SUCCESS": "crystalized",
        "FINISHED": "crystalized",
        "FAILED": "failed"
    }

    LABELS = {
        "APASSED": {"label": "稽核通過", "severity": "success"},
        "pxdrac": {"label": "六階段演化鏈", "severity": "info"},
        "releaseReady": {"label": "發布就緒", "severity": "success"},
        "canPublish": {"label": "可發布", "severity": "success"},
        "crystalized": {"label": "已結晶", "severity": "success"},
        "failed": {"label": "執行失敗", "severity": "error"}
    }

    @staticmethod
    def normalize(raw_status: str) -> str:
        """執行歸一化"""
        return StatusNormalizer.MAPPING.get(raw_status, raw_status)

    @staticmethod
    def get_metadata(normalized_status: str) -> Dict[str, str]:
        """獲取 UI 顯示元數據"""
        return StatusNormalizer.LABELS.get(normalized_status, {"label": normalized_status, "severity": "default"})

    @staticmethod
    def generate_normalization_artifact() -> Dict[str, Any]:
        """產出實作包所需的正規化表"""
        return {
            "mapping": StatusNormalizer.MAPPING,
            "labels": StatusNormalizer.LABELS,
            "version": "v1.0"
        }

if __name__ == "__main__":
    # 測試
    test_cases = ["A_PASSED", "PDRAC", "can_publish", "UNKNOWN"]
    for tc in test_cases:
        norm = StatusNormalizer.normalize(tc)
        meta = StatusNormalizer.get_metadata(norm)
        print(f"Raw: {tc} -> Normalized: {norm} ({meta['label']})")
