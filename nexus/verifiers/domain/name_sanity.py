import re
from typing import List, Dict, Any
from nexus.verifiers.contracts import VerifierVerdict, EvidenceRef

class NameSanityVerifier:
    """
    🔠 Task T3: NameSanityVerifier (Corrected version)
    職責: 檢查命名一致性，攔截隱性全局污染。
    """
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        # 1. 偵測引用 (例如: np. 或 os.)
        usages = set(re.findall(r'([a-zA-Z0-9_]+)\.', patch))
        usages.discard('self')
        
        # 2. 檢查導入關鍵字
        imports = re.findall(r'import\s+([a-zA-Z0-9_]+)', patch)
        aliases = re.findall(r'as\s+([a-zA-Z0-9_]+)', patch)
        
        allowed = set(imports + aliases + ['os', 'sys', 'time', 'numpy', 'np', 'pandas', 'pd'])
        
        missing = [u for u in usages if u not in allowed]
        
        if missing:
            return VerifierVerdict(
                verifier_name='name_sanity', 
                candidate_id=candidate_id, 
                passed=False, 
                score=-5.0, 
                failure_tags=[f'MISSING: {missing}']
            )
            
        return VerifierVerdict(
            verifier_name='name_sanity', 
            candidate_id=candidate_id, 
            passed=True, 
            score=2.0 if usages else 1.0, 
            failure_tags=['SUCCESS']
        )
