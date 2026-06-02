from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
import re


class PrePatchRejectClass(str, Enum):
    REFUSAL_DETECTED = "refusal_detected"
    EMPTY_RESPONSE = "empty_response"
    MALFORMED_PATCH_INPUT = "malformed_patch_input"
    MISSING_PATCH_BODY = "missing_patch_body"
    UNSUPPORTED_PATCH_FORMAT = "unsupported_patch_format"
    NONE = "none"


@dataclass(frozen=True)
class PrePatchPreparationPolicy:
    schema_version: str = "pre_patch_preparation_policy.v1"
    enforce_syntax_check: bool = True
    enforce_refusal_detection: bool = True
    max_input_chars: int = 50000


@dataclass(frozen=True)
class PrePatchInputReceipt:
    """Phase 6 補丁前置預處理收據，記錄輸入品質與攔截結果"""
    schema_version: str = "pre_patch_input_receipt.v1"
    status: str = "PASS"
    classification: PrePatchRejectClass = PrePatchRejectClass.NONE
    gate_passed: bool = True
    input_origin: str = "unknown"
    sanitization_applied: bool = False
    patch_phase_invoked: bool = False
    rejection_reason: str = ""
    evidence_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["classification"] = self.classification.value
        return data


class PatchInputClassifier:
    """負責偵測 refusal, empty, malformed 等前置拒絕類別"""
    
    REFUSAL_PATTERNS = [
        r"I apologize",
        r"I cannot assist",
        r"as an AI language model",
        r"sorry",
        r"對不起",
        r"抱歉",
        r"無法提供"
    ]

    def classify(self, raw_text: str) -> PrePatchRejectClass:
        if not raw_text or not raw_text.strip():
            return PrePatchRejectClass.EMPTY_RESPONSE
        
        # 偵測拒絕
        for pattern in self.REFUSAL_PATTERNS:
            if re.search(pattern, raw_text, re.IGNORECASE):
                return PrePatchRejectClass.REFUSAL_DETECTED
        
        # 偵測關鍵字結構 (Aider SEARCH/REPLACE)
        if "<<<<<<< SEARCH" not in raw_text or ">>>>>>> REPLACE" not in raw_text:
            return PrePatchRejectClass.MISSING_PATCH_BODY
            
        return PrePatchRejectClass.NONE


class PatchInputSanitizer:
    """淨化原始補丁載體，確保格式一致性"""
    
    def sanitize(self, raw_text: str) -> tuple[str, bool]:
        """回傳 (sanitized_text, was_modified)"""
        if not raw_text:
            return "", False
            
        # 移除前後多餘空白與 Markdown 標籤 (如果有的話)
        sanitized = raw_text.strip()
        
        # 簡單的 Aider 格式清洗（移除開頭的 ```python 等）
        modified = False
        if sanitized.startswith("```"):
            sanitized = re.sub(r"^```[a-zA-Z]*\n", "", sanitized)
            sanitized = re.sub(r"\n```$", "", sanitized)
            modified = True
            
        return sanitized, modified
