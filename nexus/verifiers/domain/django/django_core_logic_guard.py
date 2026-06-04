import re
from typing import List, Optional
from nexus.verifiers.contracts import VerifierVerdict, FailureTag

class DjangoCoreLogicGuard:
    """
    🛡️ [v27.2 B04 & v27.3 T1] Django_Core_Logic
    職責: 攔截 Django HTTP/View/Middleware 層的危險實作。
    """
    
    @staticmethod
    def evaluate(candidate_id: str, patch: str) -> VerifierVerdict:
        failure_tags = []
        
        # 1. 偵測危險的 SQL Injection 風險
        if ".raw(" in patch or "RawSQL" in patch:
            if "params" not in patch and "%s" not in patch:
                failure_tags.append(FailureTag(
                    code="SQL_INJECTION_RISK", 
                    description="Raw SQL detected without parameter binding."
                ))
                
        # 2. 偵測中介軟體 (Middleware) 漏洞
        if "process_request" in patch or "process_response" in patch:
            lines = patch.split('\n')
            has_return = False
            for line in lines:
                line = line.split('#')[0] 
                if re.search(r'\breturn\b', line) or re.search(r'\byield\b', line):
                    has_return = True
                    break
                    
            if not has_return:
                failure_tags.append(FailureTag(
                    code="MIDDLEWARE_BROKEN_CHAIN", 
                    description="Middleware method does not return a response, breaking the chain."
                ))

        # 3. 偵測全域狀態污染 (Global State Mutation in Views)
        if "global " in patch and ("def get" in patch or "def post" in patch):
            failure_tags.append(FailureTag(
                code="VIEW_GLOBAL_MUTATION", 
                description="Global state mutation detected inside a View. Not thread-safe."
            ))

        # 4. [v27.3] 偵測缺少 Transaction Atomic
        # 移除空格後計數，避免排版干擾
        compact_patch = "".join(patch.split())
        write_ops = compact_patch.count(".save(") + compact_patch.count(".create(") + compact_patch.count(".update(")
        if write_ops > 1 and "transaction.atomic" not in patch:
            failure_tags.append(FailureTag(
                code="MISSING_TRANSACTION", 
                description=f"Multiple write operations ({write_ops}) detected without transaction.atomic() protection."
            ))

        # 5. [v27.3] 偵測 Async Context 中的 Sync ORM 操作
        if "async def " in patch:
            sync_ops = [".objects.get(", ".objects.filter(", ".objects.all("]
            if any(op in patch for op in sync_ops) and "sync_to_async" not in patch:
                failure_tags.append(FailureTag(
                    code="SYNC_IN_ASYNC_CONTEXT", 
                    description="Synchronous ORM call detected inside an async view context."
                ))

        if failure_tags:
             return VerifierVerdict(
                verifier_name="django_core_logic", 
                candidate_id=candidate_id, 
                passed=False, 
                score=-12.0, 
                failure_tags=failure_tags
            )
            
        return VerifierVerdict(
            verifier_name="django_core_logic", 
            candidate_id=candidate_id, 
            passed=True, 
            score=4.0, 
            failure_tags=[FailureTag(code="SUCCESS", description="Core logic passes security and framework constraints.")]
        )
