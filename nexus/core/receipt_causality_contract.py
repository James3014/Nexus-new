"""
🛡️ Nexus L5.7 / v26.0 — Layer 2: Receipt Causality Contract (Execution Plane)

職責：專職收據因果守恆驗證。
- 強制校驗 hardened receipt contract 六大核心欄位（executor_id, gate_passed, invoked,
  distinct_roles, evidence_refs, semantic_evidence_complete）。
- 強制 receipt-lite 必須等價補齊 expected capability receipts（backfill 完備性）。
- 嚴密阻斷 planner-only、observation-only、local-only 結果偷渡成 model-required public row。

此模組不承擔路由准入（L1 負責）也不承擔 ledger 驗證（L4 負責）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Hardened Receipt 六大核心必填欄位
# ──────────────────────────────────────────────
HARDENED_RECEIPT_REQUIRED_FIELDS: tuple[str, ...] = (
    "executor_id",
    "gate_passed",
    "invoked",
    "distinct_roles",
    "evidence_refs",
    "semantic_evidence_complete",
)

# 在此出現的 expected capabilities 均需要對應的 backfill receipt
EXPECTED_CAPABILITY_BACKFILL_REQUIRED: frozenset[str] = frozenset({
    "mempalace_gate",
    "claim_gate",
    "artifact_gate",
    "ultra_review",
    "learning_closure",
})

# 以下類型的 execution source 若出現，代表偷渡風險（smuggling）
SMUGGLING_RISK_SOURCES: frozenset[str] = frozenset({
    "planner_only",
    "observation_only",
    "local_only",
    "deterministic_local",
    "pre_model_shortcut",
})


# ──────────────────────────────────────────────
# 驗證結果 dataclass
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class CausalityValidationResult:
    """L2 收據因果驗證結果。"""

    is_valid: bool
    reason_code: str
    reason: str
    missing_fields: List[str] = field(default_factory=list)
    backfill_gaps: List[str] = field(default_factory=list)
    smuggling_detected: bool = False
    smuggling_source: Optional[str] = None


# ──────────────────────────────────────────────
# L2 主契約類別
# ──────────────────────────────────────────────
class ReceiptCausalityContract:
    """
    🛡️ L2 Execution Plane — Receipt 因果完備性硬性契約。

    核心規則：
    1. 任何 receipt（包括 receipt-lite）必須完整包含六大核心欄位，缺一拋出 ValueError。
    2. expected capability receipts 必須 100% backfill 完備；缺口不得放行。
    3. planner-only / observation-only / local-only 結果嚴禁作為 model-required public row 偷渡。
    4. 此模組不承擔 ledger 驗證，壁壘邊界到 evidence_refs 為止。
    """

    def __init__(
        self,
        required_fields: Optional[tuple] = None,
        backfill_caps: Optional[frozenset] = None,
    ) -> None:
        self._required_fields = required_fields or HARDENED_RECEIPT_REQUIRED_FIELDS
        self._backfill_caps = backfill_caps or EXPECTED_CAPABILITY_BACKFILL_REQUIRED

    def validate_receipt(self, receipt: Dict[str, Any]) -> CausalityValidationResult:
        """
        校驗單一 receipt 的因果完備性。

        Args:
            receipt: 任意形式的 receipt dict（含 receipt-lite）。

        Returns:
            CausalityValidationResult，is_valid=False 代表嚴重違規。

        Raises:
            ValueError: 若六大核心欄位缺失時（fail-closed 硬性阻斷）。
        """
        missing = [f for f in self._required_fields if f not in receipt]
        if missing:
            msg = f"[L2] Hardened receipt contract violated: missing fields {missing}"
            logger.error("🛡️ %s", msg)
            raise ValueError(msg)

        # 偷渡來源檢測
        execution_source = receipt.get("execution_source", "")
        smuggling = execution_source in SMUGGLING_RISK_SOURCES
        if smuggling:
            msg = (
                f"[L2] Smuggling detected: execution_source='{execution_source}' "
                f"is planner/observation/local-only and MUST NOT be promoted to model-required public row."
            )
            logger.error("🛡️ %s", msg)
            raise ValueError(msg)

        # gate_passed 必須為 True 才算通過
        if not receipt.get("gate_passed"):
            return CausalityValidationResult(
                is_valid=False,
                reason_code="GATE_NOT_PASSED",
                reason="Receipt gate_passed is False or missing — causality contract not satisfied",
            )

        # invoked 必須為 True
        if not receipt.get("invoked"):
            return CausalityValidationResult(
                is_valid=False,
                reason_code="NOT_INVOKED",
                reason="Receipt invoked=False — capability was not actually executed",
            )

        # semantic_evidence_complete 必須為 True
        if not receipt.get("semantic_evidence_complete"):
            return CausalityValidationResult(
                is_valid=False,
                reason_code="SEMANTIC_EVIDENCE_INCOMPLETE",
                reason="semantic_evidence_complete=False — receipt cannot be claimed as complete",
            )

        logger.debug("🛡️ [L2] Receipt causality OK: executor_id=%s", receipt.get("executor_id"))
        return CausalityValidationResult(
            is_valid=True,
            reason_code="CAUSALITY_OK",
            reason="All hardened receipt fields present and causality satisfied",
        )

    def validate_backfill_completeness(
        self,
        receipts: List[Dict[str, Any]],
        expected_capabilities: List[str],
    ) -> CausalityValidationResult:
        """
        驗證 expected capability receipts 的 backfill 完備性。

        Args:
            receipts: 已產出的所有 receipt 列表。
            expected_capabilities: 任務聲明需要的能力列表。

        Returns:
            CausalityValidationResult，backfill_gaps 非空代表缺口存在。

        Raises:
            ValueError: 若任何 backfill_required cap 缺少對應 receipt（fail-closed）。
        """
        required_backfill = [c for c in expected_capabilities if c in self._backfill_caps]
        if not required_backfill:
            return CausalityValidationResult(
                is_valid=True,
                reason_code="BACKFILL_NOT_REQUIRED",
                reason="No expected capabilities require backfill receipts",
            )

        # 提取已有 receipts 中覆蓋的能力名稱
        covered = set()
        for r in receipts:
            ev_refs = r.get("evidence_refs", [])
            for ref in ev_refs:
                covered.add(str(ref).split(":")[0])  # 取 "cap_name:detail" 的前段
            cap_name = r.get("capability_name") or r.get("executor_id", "")
            if cap_name:
                covered.add(cap_name)

        gaps = [cap for cap in required_backfill if cap not in covered]
        if gaps:
            msg = f"[L2] Expected capability backfill INCOMPLETE: missing receipts for {gaps}"
            logger.error("🛡️ %s", msg)
            raise ValueError(msg)

        return CausalityValidationResult(
            is_valid=True,
            reason_code="BACKFILL_COMPLETE",
            reason=f"All required expected capability receipts backfilled: {required_backfill}",
        )

    def check_smuggling(self, execution_source: str, is_model_required_row: bool) -> CausalityValidationResult:
        """
        獨立偷渡防線：檢查 execution_source 是否試圖偷渡至 model-required public row。

        Args:
            execution_source: 執行來源標識符。
            is_model_required_row: 是否被標記為 model-required。

        Returns:
            CausalityValidationResult。

        Raises:
            ValueError: 若偷渡成立（fail-closed）。
        """
        if execution_source in SMUGGLING_RISK_SOURCES and is_model_required_row:
            msg = (
                f"[L2] Smuggling BLOCKED: '{execution_source}' cannot be promoted to model-required public row. "
                f"This result is planner/observation/local-only and must remain in observation plane."
            )
            logger.error("🛡️ %s", msg)
            raise ValueError(msg)

        if execution_source in SMUGGLING_RISK_SOURCES:
            return CausalityValidationResult(
                is_valid=False,
                reason_code="OBSERVATION_ONLY",
                reason=f"execution_source='{execution_source}' is observation-only, cannot be public-safe",
                smuggling_detected=False,
                smuggling_source=execution_source,
            )

        return CausalityValidationResult(
            is_valid=True,
            reason_code="SOURCE_CLEAN",
            reason=f"execution_source='{execution_source}' is model-participated, causality intact",
        )
