from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Tuple
"""
R04: Reviewer 策略模式 (Strategy Pattern)。

將 GatewayReviewLoop 的業務邏輯抽離為獨立策略類別：
- CodeReviewStrategy：處理代碼修改類任務的審核
- ConversationReviewStrategy：處理對話上下文的審核
- ReviewerFactory：根據 mode 動態掛載對應策略
"""

import json
import logging
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    pass  # 避免循環 import，reviewer 實例以 Any 傳入

from nexus.core.review_status import ReviewStatusNormalizer
from nexus.core.phantom_detect import detect_inconclusive_success

logger = logging.getLogger(__name__)


from nexus.core.protocols import ReviewerProtocol

class ReviewStrategy(ABC):
    """抽象審核策略介面。所有策略必須實作 execute()。"""

    @abstractmethod
    def execute(self, reviewer: ReviewerProtocol, manual_files: Optional[list] = None) -> Dict[str, Any]:
        """
        執行審核流程。

        Args:
            reviewer: GatewayReviewLoop 實例（持有 llm/git/linter 等服務依賴）
            manual_files: 手動指定的審核目標檔案列表（可選）

        Returns:
            標準化的 ReviewResult dict，至少包含 `status` 與 `summary` 欄位
        """
        ...


class CodeReviewStrategy(ReviewStrategy):
    """
    代碼審核策略（原 GatewayReviewLoop._audit_code）。

    負責：
      1. 取得 diff / 手動指定檔案
      2. 呼叫 linter 掃描
      3. 呼叫 LLM 進行代碼審核
      4. 應用 Patch（如已啟用）
      5. Phantom Guard 防護
    """

    def execute(self, reviewer: Any, manual_files: Optional[list] = None) -> Dict[str, Any]:
        """執行代碼審核，返回標準化 ReviewResult。"""
        files, diff_text = self._get_files_and_diff(reviewer, manual_files)
        
        if not files and not diff_text.strip():
            return reviewer._build_review_result(
                status="APPROVED",
                summary="No changes found in scope."
            )

        code_files = [f for f in files if f.endswith(".py")]
        
        # Linter 掃描
        linter_json = reviewer.linter.scan(code_files)

        # P0 Trigger：核心檔案變更時升級模式
        if any("core/" in f for f in code_files) and reviewer.execution_mode == "developer":
            reviewer.set_execution_mode("agent-shield", "P0_core_file_change")

        # LLM 審核
        prompt = reviewer.persona_hint + f"\nReview task: {reviewer.task}"
        data, raw_output = reviewer.llm.ask(prompt, diff_text)
        reviewer._record_tokens(data)

        status, success = ReviewStatusNormalizer.normalize(data.get("status", "FAIL"))
        patch_generated = bool(data.get("patch_generated", False))
        patch_apply_success = False
        no_change_reason = data.get("no_change_reason", "")
        proof_type = ""
        proof_value = ""

        # 應用 Patch
        if patch_generated and reviewer.apply_patch:
            patch_apply_success = bool(reviewer.patcher.apply(data.get("violations", [])))
            if patch_apply_success:
                proof_type, proof_value = reviewer._collect_physical_proof(files)

        # Phantom Guard
        phantom_reason = detect_inconclusive_success(
            status=status,
            patch_generated=patch_generated,
            patch_apply_success=patch_apply_success if patch_generated else False,
            no_change_reason=no_change_reason,
            proof_type=proof_type,
            proof_value=proof_value,
        )

        if success:
            if phantom_reason:
                return reviewer._build_review_result(
                    status="RECOVERABLE_BLOCK",
                    summary=f"Rejected: {phantom_reason}",
                    patch_generated=patch_generated,
                    patch_apply_success=patch_apply_success,
                    no_change_reason=no_change_reason,
                    proof_type=proof_type,
                    proof_value=proof_value,
                )
            return reviewer._build_review_result(
                status=status,
                summary=data.get("summary"),
                patch_generated=patch_generated,
                patch_apply_success=patch_apply_success,
                no_change_reason=no_change_reason,
                proof_type=proof_type,
                proof_value=proof_value,
            )

        audit_metadata = data.get("audit_metadata", {})
        return_target_phase = audit_metadata.get("return_target_phase", "D")
        # Only an explicit REJECTED response is terminal. FAIL/FAILED/unknown
        # are repairable reviewer blocks and must not gain disposition authority.
        terminal_rejection = str(data.get("status", "")).strip().upper() in {
            "REJECTED", "REJECTED_WITH_REASON"
        }
        return reviewer._build_review_result(
            status="REJECTED" if terminal_rejection else "RECOVERABLE_BLOCK",
            summary=data.get("summary"),
            violations=data.get("violations"),
            patch_generated=patch_generated,
            patch_apply_success=patch_apply_success,
            no_change_reason=no_change_reason,
            proof_type=proof_type,
            proof_value=proof_value,
            audit_metadata=audit_metadata,
            return_target_phase=return_target_phase,
            retryable=not terminal_rejection,
            next_action="none" if terminal_rejection else "REVISE",
        )

    def _get_files_and_diff(self, reviewer: Any, manual_files: Optional[list]) -> tuple:
        """取得審核的檔案列表與 diff 文字。"""
        if manual_files:
            code_files = [str(Path(f).absolute()) for f in manual_files if Path(f).is_file()]
            return code_files, "Manual Review Mode"
        files, diff_text = reviewer.git.get_changes(reviewer.scope, reviewer.base_ref)
        return files, diff_text


class ConversationReviewStrategy(ReviewStrategy):
    """
    對話上下文審核策略（原 GatewayReviewLoop._audit_conversation）。

    負責：
      1. 透過 ContextHub 進行前置路由決策（skip/light/full）
      2. 組裝壓縮對話 Pack
      3. 呼叫 LLM 進行語義一致性審核
    """

    def execute(self, reviewer: Any, manual_files: Optional[list] = None) -> Dict[str, Any]:
        """執行對話邏輯審核，返回標準化 ReviewResult。"""
        pre_decision = reviewer.context_hub.make_pre_routing_decision(reviewer.task)
        audit_level = pre_decision.get("audit_level", "full")

        if audit_level == "skip":
            return reviewer._build_review_result(
                status="SKIPPED_QUOTA",
                summary="Minimal risk: no new facts or constraints, skipping audit.",
                audit_metadata={"audit_profile": "conversation", "audit_level": "skip"},
            )

        conv_pack = reviewer.context_hub.assemble_conversation_pack(audit_mode=True)
        prompt = self._build_prompt(reviewer, audit_level, conv_pack)

        diff_placeholder = "[CONVERSATION_AUDIT: No code diff]"
        data, raw_output = reviewer.llm.ask(prompt, diff_placeholder)
        reviewer._record_tokens(data)

        status, success = ReviewStatusNormalizer.normalize(data.get("status", "FAIL"))

        if success:
            return reviewer._build_review_result(
                status=status,
                summary=data.get("summary"),
                audit_metadata={"audit_profile": "conversation", "audit_level": audit_level},
            )

        terminal_rejection = str(data.get("status", "")).strip().upper() in {
            "REJECTED", "REJECTED_WITH_REASON"
        }
        return reviewer._build_review_result(
            status="REJECTED" if terminal_rejection else "RECOVERABLE_BLOCK",
            summary=data.get("summary", "Conversation audit failed"),
            audit_flags=data.get("audit_flags", []),
            return_target_phase=data.get("return_target_phase", "D"),
            audit_metadata={
                "audit_profile": "conversation",
                "audit_level": audit_level,
                "missing_constraints": data.get("missing_constraints", []),
                "assumption_gaps": data.get("assumption_gaps", []),
            },
            retryable=not terminal_rejection,
            next_action="none" if terminal_rejection else "REVISE",
        )

    def _build_prompt(self, reviewer: Any, audit_level: str, conv_pack: dict) -> str:
        """構建對話審核提示詞。"""
        prompt = reviewer.persona_hint
        prompt += f"\nAudit Level: {audit_level}"
        prompt += f"\nTask: {reviewer.task}"
        prompt += f"\n\n--- CONVERSATION STATE ---\n{json.dumps(conv_pack, indent=2)}"
        prompt += "\n\n--- AUDIT RULES ---"
        prompt += "\n1. [Context Coverage] Does the response cover all 'confirmed_constraints'?"
        prompt += "\n2. [Correction Compliance] Does it violate any 'user_corrections'?"
        prompt += "\n3. [Assumption Gap] If 'unresolved_points' exist, does it force a final conclusion?"
        prompt += "\n4. [Research Gate] If 'needs_research=True', was X phase skipped?"
        prompt += "\n5. [Goal Alignment] Is the response aligned with 'user_goal'?"
        if audit_level == "light":
            prompt += "\n\n[LIGHT AUDIT] Only check rules 1 and 2. Skip 3-5."
        return prompt


class ReviewerFactory:
    """
    R04: 根據 execution_mode 動態選擇並實例化審核策略。

    擴充新模式時，只需在 _STRATEGIES 加入對應映射即可。
    """

    _STRATEGIES: Dict[str, type] = {
        "conversation": ConversationReviewStrategy,
        "developer":    CodeReviewStrategy,
        "safe-commit":  CodeReviewStrategy,
        "agent-shield": CodeReviewStrategy,
        "audit":        CodeReviewStrategy,
    }

    @classmethod
    def create(cls, mode: str) -> ReviewStrategy:
        """根據 mode 建立對應的審核策略實例。"""
        strategy_cls = cls._STRATEGIES.get(mode, CodeReviewStrategy)
        logger.debug("ReviewerFactory: mode=%s → %s", mode, strategy_cls.__name__)
        return strategy_cls()
