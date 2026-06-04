from nexus.problem.taxonomy import ProblemClass

class ProblemClassClassifier:
    """
    🧭 Task M3: Problem Class Classifier (Level 1)
    職責: 基於輸入特徵，判定問題的核心類別。
    這是為了實現「問題導向」治理的第一步。
    """
    
    @staticmethod
    def classify(content: str) -> ProblemClass:
        content_lower = content.lower()
        
        # 1. 偵測 Production 事故 (緊急修復)
        if any(kw in content_lower for kw in ["incident", "outage", "emergency", "production", "urgent"]):
            return ProblemClass.PRODUCTION
            
        # 2. 偵測 Safety / Security / Concurrency 
        if any(kw in content_lower for kw in ["injection", "unauthorized", "race condition", "lock", "safety", "security"]):
            return ProblemClass.SAFETY
            
        # 3. 偵測 Debug 需求 (定位與觀測)
        if any(kw in content_lower for kw in ["root cause", "diagnosis", "locate", "investigate"]):
            return ProblemClass.DEBUG
            
        # 4. 偵測 Review 需求 (審查與風險)
        if any(kw in content_lower for kw in ["review", "audit", "security check", "conformity"]):
            return ProblemClass.REVIEW
            
        # 5. 偵測 Performance 需求
        if any(kw in content_lower for kw in ["latency", "slow", "throughput", "p95", "hot path"]):
            return ProblemClass.PERFORMANCE
            
        # 6. 偵測 Migration / Schema 需求
        if any(kw in content_lower for kw in ["migration", "db_table", "schema"]):
            return ProblemClass.MIGRATION

        # 7. 偵測 Governance 需求 (政策與封板)
        if any(kw in content_lower for kw in ["policy", "freeze", "seal", "compliance"]):
            return ProblemClass.GOVERNANCE
            
        # 8. 預設為 Change (新功能、重構、遷移)
        return ProblemClass.CHANGE
