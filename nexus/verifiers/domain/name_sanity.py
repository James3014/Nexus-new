import re
from typing import List, Dict, Any
from nexus.verifiers.contracts import VerifierVerdict, EvidenceRef

class NameSanityVerifier:
    """
    🔠 Task T3: NameSanityVerifier
    職責: 檢查命名一致性，攔截隱性全局污染。
    """
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        # 1. 偵測引用 (例如: np. 或 os.)
        # 使用 raw string 並確保括號匹配
        usages = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.', patch))
        usages.discard('self')
        
        # 2. 檢查 import (包含 as 別名)
        imports = re.findall(r'import\s+([a-zA-Z0-9_]+)', patch)
        aliases = re.findall(r'as\s+([a-zA-Z0-9_]+)', patch)
        all_allowed = set(imports + aliases + ['os', 'sys', 'time'])
        
        missing = [u for u in usages if u not in all_allowed]
        
        if missing:
            return VerifierVerdict(
                verifier_name='name_sanity', 
                candidate_id=candidate_id, 
                passed=False, 
                score=-5.0, 
                failure_tags=[f'MISSING: {missing}']
            )
            
        if usages and any(u in all_allowed for u in usages):
            return VerifierVerdict(
                verifier_name='name_sanity', 
                candidate_id=candidate_id, 
                passed=True, 
                score=2.0, 
                failure_tags=['SUCCESS']
            )
            
        return VerifierVerdict(
            verifier_name='name_sanity', 
            candidate_id=candidate_id, 
            passed=True, 
            score=1.0, 
            failure_tags=['NEUTRAL']
        )
