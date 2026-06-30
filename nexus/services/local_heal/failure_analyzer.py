from nexus.services.local_heal.errors import PatchErrorKind

class FailureAnalyzer:
    """🛡️ Failure Analyzer: Centralized logic for classifying LLM & Pipeline failures."""
    
    INFRASTRUCTURE_ERRORS = ["MODEL_TIMEOUT", "MODEL_PROVIDER_ERROR"]

    def classify_patch_failure(self, failure_reason: str) -> PatchErrorKind:
        """根據失敗字串判定 PatchErrorKind"""
        reason = failure_reason.upper()
        if "SEARCH_MISMATCH" in reason:
            return PatchErrorKind.SEARCH_MISMATCH
        if "SYNTAX_ERROR" in reason:
            return PatchErrorKind.SYNTAX_ERROR
        if any(kw in reason for kw in ["MODEL_REFUSAL", "REFUSAL_DETECTED"]):
            return PatchErrorKind.REFUSAL_DETECTED
        if any(kw in reason for kw in ["MODEL_EMPTY_RESPONSE", "EMPTY_RESPONSE"]):
            return PatchErrorKind.EMPTY_RESPONSE
        if "NAME_SANITY_ERROR" in reason:
            return PatchErrorKind.NAME_SANITY_ERROR
        if "REPLACEMENT_MARKDOWN_FENCE" in reason:
            return PatchErrorKind.REPLACEMENT_MARKDOWN_FENCE
        
        return PatchErrorKind.NO_BLOCKS_FOUND

    def should_retry(self, failure_reason: str) -> bool:
        """判定該失敗是否值得重試 (排除基礎設施與不可恢復錯誤)"""
        reason = failure_reason.upper()
        if any(err in reason for err in self.INFRASTRUCTURE_ERRORS):
            return False
        return True
