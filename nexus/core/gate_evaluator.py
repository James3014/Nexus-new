#!/usr/bin/env python3
import typing
from dataclasses import dataclass, field

@dataclass
class AcceptancePolicy:
    """
    📜 Nexus 治理政策門檻 (v24.0 Meta-Hardened)
    支持外部 YAML 加載、物理回退與九環元參數控制。
    """
    # [gates] 區塊
    d_risk_threshold: float = 0.5
    max_risk_prob: float = 0.8
    v_pass_rate_min: float = 80.0
    max_forecast_tokens: int = 50000

    # [health] 區塊
    drift_max: float = 0.5
    token_efficiency_min: float = 0.7

    # 🌌 [meta_evolution] 區塊 (v24.0 九環共振)
    global_nas_aggression: float = 0.85
    system_entropy_tolerance: float = 25.0
    creativity_gradient_slope: float = 0.25
    memory_half_life_days: int = 21
    backpressure_nerve_threshold: float = 0.25

    @staticmethod
    def default() -> "AcceptancePolicy":
        """獲取內置基準政策。"""
        return AcceptancePolicy()

    @staticmethod
    def from_dict(data: dict) -> "AcceptancePolicy":
        """
        🔗 階層式政策映射 (v24.0 Hardened)
        支持 gates, health 與 meta_evolution 區塊的物理提取。
        """
        policy = AcceptancePolicy.default()
        gates = data.get("gates", {})
        health = data.get("health", {})
        meta = data.get("meta_evolution", {})

        # 🎯 物理映射：Gates
        policy.d_risk_threshold = gates.get("d_risk_threshold", policy.d_risk_threshold)
        policy.max_risk_prob = gates.get("max_risk", gates.get("max_risk_prob", policy.max_risk_prob))
        policy.v_pass_rate_min = gates.get("v_pass_rate_min", policy.v_pass_rate_min)
        policy.max_forecast_tokens = gates.get("max_forecast_tokens", policy.max_forecast_tokens)

        # 🎯 物理映射：Health
        policy.drift_max = health.get("drift_max", policy.drift_max)
        policy.token_efficiency_min = health.get("token_efficiency_min", policy.token_efficiency_min)

        # 🌌 物理映射：Meta-Evolution (The 9 Rings)
        policy.global_nas_aggression = meta.get("global_nas_aggression", policy.global_nas_aggression)
        policy.system_entropy_tolerance = meta.get("system_entropy_tolerance", policy.system_entropy_tolerance)
        policy.creativity_gradient_slope = meta.get("creativity_gradient_slope", policy.creativity_gradient_slope)
        policy.memory_half_life_days = meta.get("memory_half_life_days", policy.memory_half_life_days)
        policy.backpressure_nerve_threshold = meta.get("backpressure_nerve_threshold", policy.backpressure_nerve_threshold)

        return policy



class GateEvaluator:
    """
    ⚖️ 治理閘門判定器 (GateEvaluator v24.0 Hardened)
    負責 PDRAC 指令在各個 Phase 的通行判定與司法解釋。
    """
    def __init__(self, policy: typing.Optional[AcceptancePolicy] = None):
        self.policy = policy or AcceptancePolicy()

    def should_proceed(self, phase: str, forecast: dict, risk: dict) -> typing.Tuple[bool, str]:
        """
        核心判定邏輯：具備司法解釋的高維度通行判定。
        """
        # ROI/Risk 判定 (Phase P -> D)
        if phase == "D":
            roi = forecast.get("roi_score", 1.0)
            reject_prob = risk.get("reject_prob", 0.0)
            
            if roi < self.policy.d_risk_threshold:
                reason = f"POLICY_VIOLATION[D-ROI]: {roi:.2f} below threshold {self.policy.d_risk_threshold}. Strategy too expensive."
                return False, reason
            
            if reject_prob > self.policy.max_risk_prob:
                reason = f"POLICY_VIOLATION[D-RISK]: {reject_prob:.2f} exceeds safety limit {self.policy.max_risk_prob}."
                return False, reason
                
            return True, "passed_p_to_d_gate"

        # 審計與驗證判定 (Phase V/A)
        if phase == "A":
            audit_passed = forecast.get("audit_passed", False)
            drift = forecast.get("drift_score", 0.0)
            
            if not audit_passed:
                return False, "POLICY_VIOLATION[A-AUDIT]: Feynman Audit rejected code integrity."
            
            if drift > self.policy.drift_max:
                return False, f"POLICY_VIOLATION[A-DRIFT]: Semantic drift {drift:.2f} exceeds {self.policy.drift_max}."
                
            return True, "governance_audit_decision"

        return True, "default_pass"

    def evaluate_pass_rate(self, gate_results: typing.List[dict]) -> float:
        """計算閘門通過率 (Crystallize 輔助)。"""
        if not gate_results:
            return 0.0
        passed_count = sum(1 for r in gate_results if r.get("passed"))
        return (passed_count / len(gate_results)) * 100.0
