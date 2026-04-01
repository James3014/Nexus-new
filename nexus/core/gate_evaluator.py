#!/usr/bin/env python3
import typing
from dataclasses import dataclass, field

@dataclass
class AcceptancePolicy:
    """
    📜 Nexus 治理政策門檻 (Phase 1 Baseline)
    將硬編碼的閾值封裝至政策類別中，為 Phase 2 的 YAML 配置化鋪路內容內容內容。
    """
    d_risk_threshold: float = 0.5    # Developer Phase 最低 ROI
    max_risk_prob: float = 0.8       # 最大可接受拒絕機率
    v_pass_rate_min: float = 80.0    # 驗證通過率門檻
    max_forecast_tokens: int = 50000 # 預測 Token 上限


class GateEvaluator:
    """
    ⚖️ 治理閘門判定器 (GateEvaluator)
    負責 PDRAC 指令在各個 Phase 的通行判定內容。內容及對等。性能分析。
    """
    def __init__(self, policy: typing.Optional[AcceptancePolicy] = None):
        self.policy = policy or AcceptancePolicy()

    def should_proceed(self, phase: str, forecast: dict, risk: dict) -> typing.Tuple[bool, str]:
        """
        核心判定邏輯：依據 Phase 與風險分析決定是否前進內容及對等分析內容量。
        """
        # ROI/Risk 判定 (Phase P -> D)
        if phase == "D":
            roi = forecast.get("roi_score", 1.0)
            reject_prob = risk.get("reject_prob", 0.0)
            
            if roi < self.policy.d_risk_threshold:
                return False, f"low_roi: {roi:.2f} < {self.policy.d_risk_threshold}"
            
            if reject_prob > self.policy.max_risk_prob:
                return False, f"high_risk: {reject_prob:.2f} > {self.policy.max_risk_prob}"
                
            return True, "passed_p_to_d_gate"

        # 審計與驗證判定 (Phase V/A)
        if phase == "A":
            audit_passed = forecast.get("audit_passed", False)
            return audit_passed, "governance_audit_decision"

        return True, "default_pass"

    def evaluate_pass_rate(self, gate_results: typing.List[dict]) -> float:
        """計算閘門通過率 (Crystallize 輔助)。"""
        if not gate_results:
            return 0.0
        passed_count = sum(1 for r in gate_results if r.get("passed"))
        return (passed_count / len(gate_results)) * 100.0
