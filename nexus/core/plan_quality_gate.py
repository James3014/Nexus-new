from dataclasses import dataclass

@dataclass
class PlanQualityResult:
    passed: bool
    score: float           # 0.0 ~ 1.0
    missing_fields: list   # 缺少的必要欄位
    warnings: list         # 非致命警告
    reason: str            # 人類可讀的拒絕原因

class PlanQualityGate:
    """
    驗證計劃的結構完整性。
    
    必要欄位（缺任一項 → REJECT）:
    1. intent_pass == True
    2. risk_score 已被評估（非 None/0.0）
    3. handoff_readiness >= 0.3（最低可執行水準）
    
    建議欄位（缺少 → 降分但不拒絕）:
    4. impact_map 非空（有進行依賴分析）
    5. acceptance_criteria 非空
    6. deliverables 非空
    """
    
    REQUIRED_KEYS = ["intent_pass", "risk_score", "handoff_readiness", "target_files"]
    RECOMMENDED_KEYS = ["impact_map", "acceptance_criteria", "deliverables"]
    MIN_HANDOFF_READINESS = 0.3
    
    def evaluate(self, prediction: dict, state_metadata: dict) -> PlanQualityResult:
        missing = []
        warnings = []
        score = 1.0
        
        # 1. intent_pass 必須為 True
        if not prediction.get("intent_pass", False):
            missing.append("intent_pass")
            score -= 0.4
        
        # 2. risk_score 必須非零（已評估）
        risk = prediction.get("risk_score")
        if risk is None:
            missing.append("risk_score")
            score -= 0.2
        
        # 3. handoff_readiness 最低門檻
        readiness = float(prediction.get("handoff_readiness", 0.0) or 0.0)
        if readiness < self.MIN_HANDOFF_READINESS:
            missing.append(f"handoff_readiness ({readiness:.2f} < {self.MIN_HANDOFF_READINESS})")
            score -= 0.3
            
        # 3.5 target_files 必填 (T15)
        target_files = prediction.get("target_files")
        if not target_files or not isinstance(target_files, list) or len(target_files) == 0:
            missing.append("target_files (must be non-empty list)")
            score -= 0.3
        
        # 4-6. 建議欄位
        if not state_metadata.get("impact_map"):
            warnings.append("missing impact_map (dependency analysis skipped)")
            score -= 0.05
        
        for key in ["acceptance_criteria", "deliverables"]:
            if not prediction.get(key):
                warnings.append(f"missing {key}")
                score -= 0.05
        
        score = max(0.0, min(1.0, score))
        passed = len(missing) == 0 and score >= 0.5
        
        reason = ""
        if not passed:
            reason = f"Plan rejected: missing {missing}. Score: {score:.2f}"
        
        return PlanQualityResult(
            passed=passed,
            score=score,
            missing_fields=missing,
            warnings=warnings,
            reason=reason,
        )
