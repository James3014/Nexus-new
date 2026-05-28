"""
🛡️ Nexus L5.7 / v26.0 — Layer 3: Route Policy Evidence Contract (Evidence Plane)

職責：專職路由政策證據序列化。
- 將 execution phase 中的 route decision metadata、lane 應用結果與 rescue 判定，
  序列化至 evidence bundle 以作為可公開稽核之證據。
- 本模組不承擔任何 ledger 驗證責任（由 L4 負責）。
- 當 evidence bundle 缺少 route_execution_policy、缺少 rescue guard 理由、
  或 policy 與最終 winner source 不一致時，直接 100% Fail-closed 阻斷。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Route Policy Evidence Bundle dataclass
# ──────────────────────────────────────────────
@dataclass
class RoutePolicyEvidenceBundle:
    """
    L3 產出的路由政策證據 bundle。
    下游 (L4 / dashboard) 僅能消費此結構，不得繞過。
    """

    task_id: str
    route_execution_policy: Dict[str, Any]        # 路由決策 metadata + reason codes
    lane_applied: str                              # "light" | "hyper" | "blocked"
    rescue_guard: Optional[Dict[str, Any]]         # 如觸發 rescue 的詳細理由
    winner_source: str                             # 最終採用的 source（e.g. "model", "deterministic"）
    policy_winner_consistent: bool                 # policy 是否與 winner 一致
    evidence_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_public_audit_eligible: bool = False         # 是否可作為 public-safe 稽核證據
    block_reason: Optional[str] = None            # 若被阻斷，記錄原因
    metadata: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────
# 驗證結果 dataclass
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PolicyEvidenceValidationResult:
    """L3 policy evidence 驗證結果。"""

    is_eligible: bool       # 是否可作為 public-safe 稽核依據
    reason_code: str
    reason: str
    block_flags: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# L3 主契約類別
# ──────────────────────────────────────────────
class RoutePolicyEvidenceContract:
    """
    🛡️ L3 Evidence Plane — 路由政策證據序列化硬性契約。

    核心規則：
    1. route_execution_policy 必須存在且含有 reason_codes 列表，否則 Fail-closed。
    2. 若觸發 rescue，rescue_guard 必須包含明確理由，不得為空。
    3. policy 與 winner_source 一致性驗證：不一致直接 Fail-closed 阻斷。
    4. configured_but_blocked 的 reason codes 不得混入 active_rescue reason codes。
    5. 本模組不做 ledger 驗證，邊界到 evidence bundle 為止。
    """

    def serialize_route_evidence(
        self,
        task_id: str,
        lane_admission_result: Any,          # LaneAdmissionResult from L1
        winner_source: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> RoutePolicyEvidenceBundle:
        """
        將 L1 LaneAdmissionResult 序列化為 L3 evidence bundle。

        Args:
            task_id: 任務 ID。
            lane_admission_result: L1 LaneCapabilityContract.admit() 的返回值。
            winner_source: 最終採用的執行來源 ("model" | "deterministic_rescue" 等)。
            extra_metadata: 附加 metadata（可選）。

        Returns:
            RoutePolicyEvidenceBundle，含 policy_winner_consistent 判斷。
        """
        lane = getattr(lane_admission_result, "lane", "unknown")
        reason_codes = list(getattr(lane_admission_result, "reason_codes", []))
        rescue_triggered = getattr(lane_admission_result, "rescue_triggered", False)
        is_active_rescue = getattr(lane_admission_result, "is_active_rescue", False)
        rescue_reason = getattr(lane_admission_result, "rescue_reason", None)
        blocked_caps = list(getattr(lane_admission_result, "blocked_capabilities", []))

        # 建立 route_execution_policy
        route_execution_policy: Dict[str, Any] = {
            "reason_codes": reason_codes,
            "lane": lane,
            "rescue_triggered": rescue_triggered,
            "is_active_rescue": is_active_rescue,
            "blocked_capabilities": blocked_caps,
        }

        # 建立 rescue_guard
        rescue_guard: Optional[Dict[str, Any]] = None
        if rescue_triggered:
            rescue_guard = {
                "rescue_reason": rescue_reason or "unspecified",
                "is_active_rescue": is_active_rescue,
                "fallback_lane": lane,
            }

        # policy vs winner 一致性驗證
        policy_winner_consistent = self._check_policy_winner_consistency(
            lane=lane,
            winner_source=winner_source,
            reason_codes=reason_codes,
            rescue_triggered=rescue_triggered,
        )

        # 驗證 public audit eligibility
        validation = self.validate_evidence_eligibility(
            route_execution_policy=route_execution_policy,
            rescue_guard=rescue_guard,
            winner_source=winner_source,
            policy_winner_consistent=policy_winner_consistent,
        )

        block_reason = None if validation.is_eligible else validation.reason

        bundle = RoutePolicyEvidenceBundle(
            task_id=task_id,
            route_execution_policy=route_execution_policy,
            lane_applied=lane,
            rescue_guard=rescue_guard,
            winner_source=winner_source,
            policy_winner_consistent=policy_winner_consistent,
            is_public_audit_eligible=validation.is_eligible,
            block_reason=block_reason,
            metadata=extra_metadata or {},
        )

        if not validation.is_eligible:
            logger.warning(
                "🛡️ [L3] Evidence bundle BLOCKED (task=%s): %s | flags=%s",
                task_id, validation.reason, validation.block_flags,
            )
        else:
            logger.info("🛡️ [L3] Evidence bundle PUBLIC_AUDIT_ELIGIBLE (task=%s, lane=%s)", task_id, lane)

        return bundle

    def validate_evidence_eligibility(
        self,
        route_execution_policy: Dict[str, Any],
        rescue_guard: Optional[Dict[str, Any]],
        winner_source: str,
        policy_winner_consistent: bool,
    ) -> PolicyEvidenceValidationResult:
        """
        驗證 evidence bundle 是否可作為 public-safe 稽核依據。

        Fail-closed 條件：
        - route_execution_policy 缺失或 reason_codes 為空
        - rescue 觸發但 rescue_guard 為空或缺少理由
        - policy 與 winner_source 不一致
        """
        block_flags: List[str] = []

        # 條件 1: route_execution_policy 存在性
        if not route_execution_policy:
            block_flags.append("MISSING_ROUTE_EXECUTION_POLICY")

        reason_codes = route_execution_policy.get("reason_codes", []) if route_execution_policy else []
        if not reason_codes:
            block_flags.append("EMPTY_REASON_CODES")

        # 條件 2: rescue guard 完備性
        rescue_triggered = route_execution_policy.get("rescue_triggered", False) if route_execution_policy else False
        if rescue_triggered:
            if not rescue_guard:
                block_flags.append("RESCUE_TRIGGERED_BUT_GUARD_MISSING")
            elif not rescue_guard.get("rescue_reason") or rescue_guard.get("rescue_reason") == "unspecified":
                block_flags.append("RESCUE_GUARD_MISSING_REASON")

        # 條件 3: policy vs winner 一致性
        if not policy_winner_consistent:
            block_flags.append("POLICY_WINNER_INCONSISTENT")

        if block_flags:
            return PolicyEvidenceValidationResult(
                is_eligible=False,
                reason_code="EVIDENCE_BLOCKED",
                reason=f"Evidence bundle Fail-closed. Flags: {block_flags}",
                block_flags=block_flags,
            )

        return PolicyEvidenceValidationResult(
            is_eligible=True,
            reason_code="EVIDENCE_ELIGIBLE",
            reason="Route policy evidence bundle passes all L3 gates",
            block_flags=[],
        )

    def _check_policy_winner_consistency(
        self,
        lane: str,
        winner_source: str,
        reason_codes: List[str],
        rescue_triggered: bool,
    ) -> bool:
        """
        驗證 lane policy 與 winner_source 是否一致。

        Logic：
        - lane="light" + winner_source="model" → consistent
        - lane="hyper" + winner_source="model" → consistent
        - lane="light" + winner_source="deterministic_local" + no rescue → inconsistent
        - lane="blocked" + any winner → inconsistent（blocked 不應有 winner）
        """
        if lane == "blocked":
            logger.warning("🛡️ [L3] Lane is BLOCKED but winner_source='%s' detected — inconsistent", winner_source)
            return False

        # deterministic_local / pre_model 在 light lane 且未觸發 rescue → 違規
        non_model_sources = {"deterministic_local", "pre_model_shortcut", "planner_only", "local_only"}
        if winner_source in non_model_sources and lane == "light" and not rescue_triggered:
            # 必須有 cost_capped_capability_allows_verified_pre_model_rescue reason code
            if "cost_capped_capability_allows_verified_pre_model_rescue" not in reason_codes:
                logger.warning(
                    "🛡️ [L3] winner_source='%s' in light lane without proper rescue reason code → inconsistent",
                    winner_source,
                )
                return False

        return True
