"""
🛡️ Nexus L5.7 / v26.0 — Layer 4: Public Telemetry Boundary Contract (Evidence Plane)

職責：專職 claimability 與 promotion boundary 判定。
- 集中收口 provider-token completeness（必須達 1.0）、wall-ledger conservation（殘差合格性）、
  warning/wall telemetry invalid、以及物理平面上的 observation-only 徹底隔離。
- Downstream 僅能消費 source promotion boundary，嚴防 shadow/experimental telemetry 偷渡。
- 明定硬性物理阻隔規則：shadow / experimental / observation-only 遙測僅能作為內部 RCA 改進指引，
  嚴禁被任何下游 dashboard、promotion review 或 gap report 作為 public-safe 數據來源消費。

此模組不承擔路由准入（L1）、receipt 因果（L2）或 route policy 序列化（L3）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Telemetry 來源分類
# ──────────────────────────────────────────────
OBSERVATION_ONLY_TELEMETRY_SOURCES: frozenset[str] = frozenset({
    "shadow",
    "experimental",
    "observation_only",
    "estimated",
    "synthetic",
    "zero_fill",
    "included_in_parent",          # wall-ledger 中的 parent timing（不獨立計算）
})

# 必須達到完整度的欄位
PROVIDER_TOKEN_REQUIRED_FIELDS: tuple[str, ...] = (
    "provider_token_completeness",  # 必須 == 1.0
    "wall_time_ms",
    "token_usage",
    "provider_costs",
    "overhead_ms",
)

# wall-ledger 殘差合格閾值（殘差比例不得超過此值）
WALL_LEDGER_RESIDUAL_TOLERANCE: float = 0.05   # 5%


# ──────────────────────────────────────────────
# Promotion Boundary 判定結果
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PromotionBoundaryResult:
    """L4 Public Telemetry Boundary 判定結果。"""

    promotion_status: str        # "SOURCE_PROMOTION_READY" | "BLOCKED" | "OBSERVATION_ONLY"
    is_public_claim_safe: bool   # 嚴格 False = 不得對外宣稱
    reason_code: str
    reason: str
    block_flags: List[str] = field(default_factory=list)
    telemetry_source_class: str = "unknown"   # "model_participated" | "observation_only" | "mixed"
    wall_ledger_residual_ratio: Optional[float] = None


# ──────────────────────────────────────────────
# L4 主契約類別
# ──────────────────────────────────────────────
class PublicTelemetryBoundaryContract:
    """
    🛡️ L4 Evidence Plane — Public Telemetry Boundary 硬性契約。

    核心規則：
    1. provider_token_completeness 必須 == 1.0，否則 Fail-closed。
    2. wall-ledger conservation 殘差比例不得超過 WALL_LEDGER_RESIDUAL_TOLERANCE。
    3. shadow / experimental / observation-only telemetry 嚴禁作為下游 public-safe 數據源。
    4. warning/wall telemetry invalid 標記存在時，立即 Fail-closed。
    5. is_public_claim_safe 永遠不得被外部覆蓋為 True（此屬性 read-only 合約）。
    """

    def __init__(
        self,
        residual_tolerance: float = WALL_LEDGER_RESIDUAL_TOLERANCE,
    ) -> None:
        self._residual_tolerance = residual_tolerance

    def evaluate_promotion_boundary(
        self,
        telemetry: Dict[str, Any],
        source_promotion_boundary: Optional[str] = None,
    ) -> PromotionBoundaryResult:
        """
        評估遙測資料是否可通過 source promotion boundary 進入 public-safe 消費。

        Args:
            telemetry: 包含所有遙測欄位的 dict。
            source_promotion_boundary: 上游聲明的 promotion boundary 狀態（可選）。

        Returns:
            PromotionBoundaryResult。

        Raises:
            ValueError: 若 public_claim_safe 被嘗試設為 True（硬性阻斷）。
        """
        block_flags: List[str] = []

        # 安全攔截：若有人嘗試在 telemetry 中設 public_claim_safe=True，立即 Fail-closed
        if telemetry.get("public_claim_safe") is True:
            msg = "[L4] CRITICAL: public_claim_safe=True is FORBIDDEN in telemetry input. This is a boundary violation."
            logger.error("🛡️ %s", msg)
            raise ValueError(msg)

        # ── Gate 1: Telemetry 來源分類 ──
        # Fail-closed: missing source is unavailable, never open-default measured
        from nexus.core.belief_contracts import _resolve_telemetry_source

        telemetry_source = _resolve_telemetry_source(telemetry if isinstance(telemetry, dict) else {})
        source_class = self._classify_telemetry_source(telemetry_source)
        if source_class == "observation_only":
            block_flags.append(f"OBSERVATION_ONLY_TELEMETRY_SOURCE:{telemetry_source}")
            logger.warning(
                "🛡️ [L4] Telemetry source '%s' is observation-only — blocked from public consumption", telemetry_source
            )

        # ── Gate 2: provider-token completeness ──
        token_completeness = float(telemetry.get("provider_token_completeness", 0.0))
        if token_completeness < 1.0:
            block_flags.append(f"PROVIDER_TOKEN_INCOMPLETE:{token_completeness:.3f}")
            logger.warning("🛡️ [L4] provider_token_completeness=%.3f < 1.0 — blocked", token_completeness)

        # ── Gate 3: 必填遙測欄位 ──
        missing_fields = [f for f in PROVIDER_TOKEN_REQUIRED_FIELDS if f not in telemetry]
        if missing_fields:
            block_flags.append(f"MISSING_TELEMETRY_FIELDS:{missing_fields}")

        # ── Gate 4: wall-ledger conservation 殘差 ──
        residual_ratio = self._compute_wall_ledger_residual(telemetry)
        if residual_ratio is not None and residual_ratio > self._residual_tolerance:
            block_flags.append(f"WALL_LEDGER_RESIDUAL_EXCEEDS_TOLERANCE:{residual_ratio:.4f}")
            logger.warning(
                "🛡️ [L4] wall-ledger residual ratio=%.4f > %.4f tolerance — blocked", residual_ratio, self._residual_tolerance
            )

        # ── Gate 5: warning/infra-invalid 旗標 ──
        if telemetry.get("has_infra_invalid", False):
            block_flags.append("INFRA_INVALID_FLAG_SET")
        if telemetry.get("gateway_token_outlier_reason") == "stats_outlier_possible_cumulative":
            block_flags.append("STATS_OUTLIER_CUMULATIVE_DETECTED")
        if telemetry.get("wall_time_ms", 1) <= 0:
            block_flags.append("WALL_TIME_ZERO_OR_NEGATIVE")
        if telemetry.get("token_usage", 1) <= 0 and telemetry.get("model_calls", 0) > 0:
            block_flags.append("TOKEN_USAGE_ZERO_WITH_MODEL_CALLS")

        # ── Gate 6: source_promotion_boundary 狀態一致性 ──
        if source_promotion_boundary and source_promotion_boundary not in (
            "SOURCE_PROMOTION_READY", "APPROVED", "VERIFIED"
        ):
            block_flags.append(f"SOURCE_PROMOTION_BOUNDARY_NOT_READY:{source_promotion_boundary}")

        # ── 最終裁定 ──
        if block_flags:
            return PromotionBoundaryResult(
                promotion_status="BLOCKED",
                is_public_claim_safe=False,
                reason_code="PROMOTION_BLOCKED",
                reason=f"Telemetry boundary gates failed. Flags: {block_flags}",
                block_flags=block_flags,
                telemetry_source_class=source_class,
                wall_ledger_residual_ratio=residual_ratio,
            )

        logger.info("🛡️ [L4] Telemetry boundary PASSED — SOURCE_PROMOTION_READY")
        return PromotionBoundaryResult(
            promotion_status="SOURCE_PROMOTION_READY",
            is_public_claim_safe=False,   # 永遠由下游結算，此層不主動 assert True
            reason_code="PROMOTION_ELIGIBLE",
            reason="All L4 telemetry boundary gates passed. Downstream may consume for promotion review.",
            block_flags=[],
            telemetry_source_class=source_class,
            wall_ledger_residual_ratio=residual_ratio,
        )

    def assert_downstream_cannot_bypass(self, bundle: Dict[str, Any]) -> None:
        """
        強制斷言下游 bundle 不得包含 observation-only 遙測作為 public-safe 數據源。
        供 dashboard / promotion review 消費前呼叫。

        Raises:
            ValueError: 若下游 bundle 包含任何 observation-only 來源的 public-safe 標記。
        """
        telemetry_sources = bundle.get("telemetry_sources", [])
        for src in telemetry_sources:
            if src in OBSERVATION_ONLY_TELEMETRY_SOURCES:
                msg = (
                    f"[L4] Downstream consumption BLOCKED: telemetry_source='{src}' is observation-only. "
                    f"It MUST NOT be used as public-safe data in dashboard, promotion review, or gap report."
                )
                logger.error("🛡️ %s", msg)
                raise ValueError(msg)

        # 確認 public_claim_safe 未被竄改
        if bundle.get("public_claim_safe") is True:
            msg = "[L4] CRITICAL: Downstream bundle has public_claim_safe=True — this is a physical boundary violation."
            logger.error("🛡️ %s", msg)
            raise ValueError(msg)

    def classify_wall_ledger_entry(self, entry: Dict[str, Any]) -> str:
        """
        分類 wall-ledger 條目的遙測類型，以精確區分 included-in-parent timing 與 zero-fill 指標。

        Returns:
            "measured" | "included_in_parent" | "zero_fill" | "observation_only"
        """
        from nexus.core.belief_contracts import _resolve_telemetry_source

        source = _resolve_telemetry_source(entry if isinstance(entry, dict) else {})
        if entry.get("telemetry_source") == "included_in_parent" or source == "included_in_parent":
            return "included_in_parent"
        if entry.get("telemetry_source") == "zero_fill" or source == "zero_fill":
            return "zero_fill"
        if source in OBSERVATION_ONLY_TELEMETRY_SOURCES or source in ("unavailable", "estimated", "unknown"):
            return "observation_only"
        wall_time = entry.get("wall_time_ms", -1)
        if wall_time == 0:
            return "zero_fill"
        return "measured"

    # ──────────────────────────────────────────
    # 內部工具方法
    # ──────────────────────────────────────────

    def evaluate_batch_promotion_boundary(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        PR2: Batch-level evidence aggregation — 包裝既有 row-level signals，不創新定義。

        從 runner row 的既有欄位計算 batch 級指標，供 evidence bundle 消費：
        - provider_token_completeness_rate: 包裝 `provider_token_measured` (已由 _row_has_measured_provider_tokens 判定)
        - wall_ledger_conserved_rate: 包裝既有 wall-ledger classification
        - telemetry_invalid_rate: 包裝 `has_infra_invalid` / `telemetry_invalid` row signals

        Returns:
            dict with keys: provider_token_completeness_rate, wall_ledger_conserved_rate,
                            telemetry_invalid_rate, eligible_n, observation_only_n, schema
        """
        eligible = [r for r in rows if bool(r.get("run_eligible", True))]
        n = len(eligible)
        if n == 0:
            return {
                "schema": "nexus_batch_promotion_boundary_v1",
                "eligible_n": 0,
                "provider_token_completeness_rate": None,
                "wall_ledger_conserved_rate": None,
                "telemetry_invalid_rate": None,
                "observation_only_n": 0,
            }

        # 1. provider_token_completeness_rate — 包裝 provider_token_measured row signal
        #    (即 _row_has_measured_provider_tokens 判定結果；runner 已將其寫入 row 級欄位)
        provider_complete = sum(
            1 for r in eligible
            if bool(r.get("provider_token_measured", False))
            and bool(r.get("token_reliable", True))
            and not bool(r.get("has_infra_invalid", False))
        )

        # 2. wall_ledger_conserved_rate — 包裝既有 wall-ledger classification
        #    conserved = row 不是 telemetry_invalid，且 wall-ledger 條目類型非 zero_fill/observation_only
        wall_ledger_conserved = sum(
            1 for r in eligible
            if not bool(r.get("telemetry_invalid", False))
            and self.classify_wall_ledger_entry(r) not in {"zero_fill", "observation_only"}
        )

        # 3. telemetry_invalid_rate — 包裝 has_infra_invalid + telemetry_invalid row signals
        telemetry_invalid = sum(
            1 for r in eligible
            if bool(r.get("has_infra_invalid", False)) or bool(r.get("telemetry_invalid", False))
        )

        # 4. observation_only_n — 包裝既有 OBSERVATION_ONLY_TELEMETRY_SOURCES 分類
        observation_only = sum(
            1 for r in eligible
            if self._classify_telemetry_source(str(r.get("telemetry_source", "measured"))) == "observation_only"
        )

        return {
            "schema": "nexus_batch_promotion_boundary_v1",
            "eligible_n": n,
            "provider_token_completeness_rate": round(provider_complete / n, 4),
            "wall_ledger_conserved_rate": round(wall_ledger_conserved / n, 4),
            "telemetry_invalid_rate": round(telemetry_invalid / n, 4),
            "observation_only_n": observation_only,
        }

    def _classify_telemetry_source(self, source: str) -> str:

        if source in OBSERVATION_ONLY_TELEMETRY_SOURCES:
            return "observation_only"
        if source in ("measured", "gateway", "provider_reported"):
            return "model_participated"
        return "unknown"

    def _compute_wall_ledger_residual(self, telemetry: Dict[str, Any]) -> Optional[float]:
        """
        計算 wall-ledger 殘差比例。
        殘差 = |wall_time_ms - (sum of child times + overhead_ms)| / wall_time_ms
        若資料不完整，返回 None。
        """
        wall_time = telemetry.get("wall_time_ms")
        overhead = telemetry.get("overhead_ms", 0)
        child_times = telemetry.get("child_wall_times_ms", [])

        if wall_time is None or wall_time <= 0:
            return None

        child_sum = sum(child_times) if isinstance(child_times, list) else 0
        ledger_sum = child_sum + overhead
        residual = abs(wall_time - ledger_sum) / wall_time
        return residual
