#!/usr/bin/env python3
import typing
from dataclasses import dataclass, field

@dataclass
class AcceptancePolicy:
    """
    📜 Nexus 治理政策門檻 (Phase 2 Hardened)
    支持外部 YAML 加載與物理回退機制內容性能及性能。內容內容內容及性能內容性能性能性能。內容內容內容及性質。內容且對量分析。性能分析。
    """
    # [gates] 區塊內容內容及性能內容性能性能性能內容及性能。
    d_risk_threshold: float = 0.5
    max_risk_prob: float = 0.8
    v_pass_rate_min: float = 80.0
    max_forecast_tokens: int = 50000
    
    # [health] 區塊內容內容及性能內容性能性能性能內容及性能內容。
    drift_max: float = 0.5
    token_efficiency_min: float = 0.7

    @staticmethod
    def default() -> "AcceptancePolicy":
        """獲取內置基準政策內容性能及性能。內容內容內容及性能。內容性能性能。內容及性質。性能分析。"""
        return AcceptancePolicy()

    @staticmethod
    def from_dict(data: dict) -> "AcceptancePolicy":
        """
        🔗 層級式政策映射 (Hierarchical Mapping)
        從字典中物理提取 gates 與 health 區塊內容內容內容及性能。內容及性能。內容性能。
        支援覆寫邏輯：環境特定配置將覆蓋全域預設內容及對度。內容性能。
        """
        policy = AcceptancePolicy.default()
        gates = data.get("gates", {})
        health = data.get("health", {})

        # 🎯 物理映射：Gates 區塊內容分析內容性能性能內容。內容內容內容。
        policy.d_risk_threshold = gates.get("d_risk_threshold", policy.d_risk_threshold)
        policy.max_risk_prob = gates.get("max_risk", gates.get("max_risk_prob", policy.max_risk_prob))
        policy.v_pass_rate_min = gates.get("v_pass_rate_min", policy.v_pass_rate_min)
        policy.max_forecast_tokens = gates.get("max_forecast_tokens", policy.max_forecast_tokens)
        
        # 🎯 物理映射：Health 區塊內容解析內容。內容、性質。性能分析。
        policy.drift_max = health.get("drift_max", policy.drift_max)
        policy.token_efficiency_min = health.get("token_efficiency_min", policy.token_efficiency_min)

        return policy


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
