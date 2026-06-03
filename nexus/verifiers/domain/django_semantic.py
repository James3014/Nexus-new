import re
from typing import List, Dict, Any
from nexus.verifiers.contracts import VerifierVerdict, EvidenceRef

class DjangoSemanticVerifier:
    """
    🌐 Task T4: Django Semantic Verifier
    職責: 捕捉 Django 模型、遷移與中繼資料的隱性副作用。
    """
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        # 1. 偵測隱性副作用：誤刪重要 Meta 屬性
        critical_patterns = [
            (r"class Meta:", r"db_table\s*=", "MISSING_DB_TABLE_SPEC"),
            (r"class Meta:", r"managed\s*=", "MISSING_MANAGED_FLAG")
        ]
        
        failure_tags = []
        for class_pat, attr_pat, tag in critical_patterns:
            if re.search(class_pat, patch) and not re.search(attr_pat, patch):
                # 只有在 patch 修改了 Meta 卻沒包含屬性時報警
                failure_tags.append(tag)
        
        if failure_tags:
            return VerifierVerdict(
                verifier_name="django_semantic",
                candidate_id=candidate_id,
                passed=False,
                score=-8.0,
                failure_tags=failure_tags
            )
            
        return VerifierVerdict("django_semantic", candidate_id, True, 1.0, ["SEMANTIC_STABLE"])
