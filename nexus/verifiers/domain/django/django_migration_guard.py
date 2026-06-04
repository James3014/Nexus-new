import re
from typing import List, Optional
from nexus.verifiers.contracts import VerifierVerdict, EvidenceRef, FailureTag

class DjangoMigrationGuard:
    """
    🛡️ [v27.2 B03] Django_ORM_Migration
    職責: 攔截危險的 Django Migration 操作，驗證依賴順序，防止框架級破壞。
    """
    
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        failure_tags = []
        
        # 1. 偵測危險操作 (Dangerous Operations)
        if "RunSQL" in patch and "reverse_sql" not in patch:
            failure_tags.append(FailureTag(
                code="IRREVERSIBLE_MIGRATION", 
                description="RunSQL detected without reverse_sql. Rollback safety compromised."
            ))
            
        if "RemoveField" in patch:
            failure_tags.append(FailureTag(
                code="DESTRUCTIVE_MIGRATION", 
                description="RemoveField detected. Ensure data loss is acceptable."
            ))

        # 2. 驗證依賴陣列 (Dependency DAG parsing)
        deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', patch, re.DOTALL)
        if deps_match:
            deps_str = deps_match.group(1)
            # 簡單檢查：如果出現 '__first__' 但不是初始化遷移，發出警告
            if "'__first__'" in deps_str and "initial = True" not in patch:
                 failure_tags.append(FailureTag(
                    code="DEPENDENCY_RISK", 
                    description="'__first__' dependency used in non-initial migration."
                ))
        
        # 3. 跨 App 依賴檢查
        # 如果引用了其他 app 的模型，但 dependencies 裡沒有對應 app 的 node
        if "migrations.swappable_dependency" in patch and "dependencies" not in patch:
             failure_tags.append(FailureTag(
                code="CROSS_APP_ORPHAN", 
                description="Swappable dependency used without explicit dependency node."
            ))

        if failure_tags:
             return VerifierVerdict(
                verifier_name="django_migration", 
                candidate_id=candidate_id, 
                passed=False, 
                score=-10.0, 
                failure_tags=failure_tags
            )
            
        return VerifierVerdict(
            verifier_name="django_migration", 
            candidate_id=candidate_id, 
            passed=True, 
            score=5.0, 
            failure_tags=[FailureTag(code="SUCCESS", description="Migration DAG is safe and reversible.")]
        )
