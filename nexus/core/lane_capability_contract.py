"""
🛡️ Nexus L5.7 / v26.0 — Layer 1: Lane Capability Contract (Execution Plane)

職責：專職執行期路由准入判定。
- 輸入：expected_capabilities、executor_capabilities、*_receipt_lite 控制旗標、compact 啟動條件。
- 當 expected capabilities 超出白名單時，主動觸發 expected_capability_protection 並安全回退。
- 嚴格區分「configured but blocked」與「active rescue」，防止阻斷原因碼被誤判為有效公共證據。

此模組不承擔 receipt 因果驗證（由 L2 負責）也不承擔路由政策序列化（由 L3 負責）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 白名單：允許進入 Light Route 的受控能力集合
# ──────────────────────────────────────────────
LIGHT_ROUTE_CAPABILITY_WHITELIST: frozenset[str] = frozenset({
    "mempalace",
    "autonomic_router",
    "belief",
    "repair_loop",
    "learning_closure",
    "context_sync_capped",
    "hiddenlite",
})

# 必須走完整 Hyper 路徑的高風險能力
HYPER_ONLY_CAPABILITIES: frozenset[str] = frozenset({
    "ultra_review",
    "swarm_multi_agent",
    "hyper_sprint",
    "policy_capability_gate",
    "governance_hardened",
})


# ──────────────────────────────────────────────
# 准入決定結果 dataclass
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class LaneAdmissionResult:
    """L1 路由准入裁定結果。"""

    status: str                         # "ADMITTED" | "BLOCKED" | "RESCUED"
    lane: str                           # "light" | "hyper" | "blocked"
    reason_codes: List[str]             # 決策理由碼序列
    admitted_capabilities: List[str]    # 實際進入 lane 的能力集
    blocked_capabilities: List[str]     # 被阻斷的能力（configured but blocked）
    rescue_triggered: bool              # 是否觸發 expected_capability_protection 回退
    rescue_reason: Optional[str]        # 回退具體原因
    is_active_rescue: bool              # 嚴格標示：True = active rescue；False = configured but blocked
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────
# L1 主契約類別
# ──────────────────────────────────────────────
class LaneCapabilityContract:
    """
    🛡️ L1 Execution Plane — 路由准入硬性契約。

    核心規則：
    1. expected_capabilities 若包含 HYPER_ONLY 成員 → 強制回退至 Hyper，不得進入 Light Route。
    2. compact_mode=True 且 risk_level ∈ {LOW} 且 impact_complexity ≤ 3.0 → 允許 Light Route。
    3. configured_but_blocked 的能力絕對不得被標記為 active_rescue，兩者物理分離。
    4. 任何 rescue 觸發必須寫入 reason_codes，且不得包含 "cost_capped_shortcut"。
    """

    def __init__(
        self,
        light_route_whitelist: Optional[frozenset] = None,
        hyper_only_caps: Optional[frozenset] = None,
    ) -> None:
        self._whitelist = light_route_whitelist or LIGHT_ROUTE_CAPABILITY_WHITELIST
        self._hyper_only = hyper_only_caps or HYPER_ONLY_CAPABILITIES

    def admit(
        self,
        expected_capabilities: List[str],
        executor_capabilities: List[str],
        compact_mode: bool,
        risk_level: str,
        impact_complexity: float,
        receipt_lite_flags: Optional[Dict[str, bool]] = None,
    ) -> LaneAdmissionResult:
        """
        執行准入裁定。

        Args:
            expected_capabilities: 任務聲明需要的能力列表（可能含 HYPER_ONLY）。
            executor_capabilities: executor 實際可執行的能力列表。
            compact_mode: 是否啟動 compact 執行模式。
            risk_level: 任務風險等級 "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"。
            impact_complexity: 任務複雜度浮點數（0.0–5.0）。
            receipt_lite_flags: *_receipt_lite 控制旗標 dict（可選）。

        Returns:
            LaneAdmissionResult 裁定結果。
        """
        reason_codes: List[str] = ["expected_capability_protection"]
        blocked_caps: List[str] = []
        rescue_triggered = False
        rescue_reason: Optional[str] = None
        is_active_rescue = False

        # ── Step 1: 檢查 HYPER_ONLY 能力是否出現在 expected_capabilities ──
        hyper_only_requested = [c for c in expected_capabilities if c in self._hyper_only]
        if hyper_only_requested:
            reason_codes.append("hyper_only_capability_forces_full_path")
            logger.info("🛡️ [L1] HYPER_ONLY caps requested: %s → forcing full Hyper path", hyper_only_requested)
            return LaneAdmissionResult(
                status="ADMITTED",
                lane="hyper",
                reason_codes=reason_codes,
                admitted_capabilities=list(expected_capabilities),
                blocked_capabilities=[],
                rescue_triggered=False,
                rescue_reason=None,
                is_active_rescue=False,
                metadata={"hyper_only_requested": hyper_only_requested},
            )

        # ── Step 2: 計算 Light Route 准入條件 ──
        light_eligible = (
            compact_mode
            and risk_level not in ("HIGH", "CRITICAL")
            and impact_complexity <= 3.0
        )

        if not light_eligible:
            reason_codes.append("light_route_ineligible_by_risk_or_complexity")
            return LaneAdmissionResult(
                status="ADMITTED",
                lane="hyper",
                reason_codes=reason_codes,
                admitted_capabilities=list(expected_capabilities),
                blocked_capabilities=[],
                rescue_triggered=False,
                rescue_reason=None,
                is_active_rescue=False,
                metadata={"risk_level": risk_level, "impact_complexity": impact_complexity},
            )

        # ── Step 3: 過濾白名單以外的能力（configured but blocked）──
        admitted_caps: List[str] = []
        for cap in expected_capabilities:
            if cap in self._whitelist:
                admitted_caps.append(cap)
            else:
                blocked_caps.append(cap)
                logger.warning(
                    "🛡️ [L1] Cap '%s' is CONFIGURED BUT BLOCKED from light route (not in whitelist)", cap
                )

        # ── Step 4: 判定是否需要觸發 expected_capability_protection 回退 ──
        if blocked_caps:
            # 被阻斷的能力存在 → 不是 active rescue，是 configured but blocked
            reason_codes.append("capability_blocked_not_in_light_whitelist")
            # 如果 admitted_caps 為空，必須回退至 hyper
            if not admitted_caps:
                rescue_triggered = True
                is_active_rescue = True
                rescue_reason = "all_expected_capabilities_blocked_from_light_route"
                reason_codes.append("active_rescue_fallback_to_hyper")
                logger.warning("🛡️ [L1] Active rescue triggered: all caps blocked → falling back to Hyper path")
                return LaneAdmissionResult(
                    status="RESCUED",
                    lane="hyper",
                    reason_codes=reason_codes,
                    admitted_capabilities=list(expected_capabilities),
                    blocked_capabilities=blocked_caps,
                    rescue_triggered=True,
                    rescue_reason=rescue_reason,
                    is_active_rescue=True,
                    metadata={"blocked_caps": blocked_caps},
                )

        # ── Step 5: receipt_lite_flags 控制檢核 ──
        if receipt_lite_flags:
            for flag_name, flag_val in receipt_lite_flags.items():
                if flag_val and flag_name.endswith("_receipt_lite"):
                    cap_name = flag_name.replace("_receipt_lite", "")
                    if cap_name not in self._whitelist:
                        blocked_caps.append(cap_name)
                        reason_codes.append(f"receipt_lite_flag_blocked_{cap_name}")
                        logger.warning("🛡️ [L1] receipt_lite flag '%s' blocked: cap not whitelisted", flag_name)

        # ── Step 6: 准入 Light Route ──
        reason_codes.append("light_route_admission_granted")
        logger.info("🛡️ [L1] Light route ADMITTED. caps=%s blocked=%s", admitted_caps, blocked_caps)

        return LaneAdmissionResult(
            status="ADMITTED",
            lane="light",
            reason_codes=reason_codes,
            admitted_capabilities=admitted_caps,
            blocked_capabilities=blocked_caps,
            rescue_triggered=rescue_triggered,
            rescue_reason=rescue_reason,
            is_active_rescue=is_active_rescue,
            metadata={
                "compact_mode": compact_mode,
                "risk_level": risk_level,
                "impact_complexity": impact_complexity,
            },
        )

    def is_configured_but_blocked(self, result: LaneAdmissionResult) -> bool:
        """
        判定結果是否為「configured but blocked」狀態（而非 active rescue）。
        此方法供 L3 Evidence 平面使用，確保 blocked 原因碼不被誤植為有效 route evidence。
        """
        return bool(result.blocked_capabilities) and not result.is_active_rescue
