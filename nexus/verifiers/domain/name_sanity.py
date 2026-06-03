import re
from typing import List, Dict, Any
from nexus.verifiers.models import VerifierVerdict

class NameSanityVerifier:
    """
    🔠 Task T3: NameSanityVerifier (Prototype)
    職責: 檢查命名一致性，攔截隱性全局污染。
    """
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        # 1. 致命缺陷攔截
        if "np." in patch and "import numpy" not in patch:
            return VerifierVerdict("name_sanity", candidate_id, False, -5.0, ["UNDEFINED_SYMBOL: np"], "NAME_ERROR")
            
        # 2. 正確修復加成
        if "import numpy as np" in patch and "np." in patch:
            return VerifierVerdict("name_sanity", candidate_id, True, 2.0, ["CORRECT_IMPORT_AND_USAGE"])
            
        return VerifierVerdict("name_sanity", candidate_id, True, 1.0, ["NAMES_NEUTRAL"])
