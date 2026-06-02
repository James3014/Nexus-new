from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, List, Optional


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalScope(str, Enum):
    DESIGN = "design"
    OUTLINE = "outline"
    EXECUTION = "execution"


@dataclass(frozen=True)
class AlignmentApprovalReceipt:
    """團隊對齊審核收據"""
    schema_version: str = "alignment_approval_receipt.v1"
    task_id: str = ""
    scope: ApprovalScope = ApprovalScope.DESIGN
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_id: str = "unknown"
    comment: str = ""
    handoff_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.value
        data["status"] = self.status.value
        return data


class AlignmentGate:
    """Stage 5: 團隊對齊閘口，負責前置設計與大綱的審核攔截"""

    def check_readiness(self, context: dict[str, Any], required_scope: ApprovalScope) -> tuple[bool, str]:
        """判定任務是否已準備好進入下一階段"""
        
        # 尋找對應 scope 的收據
        receipts = context.get("approval_receipts", [])
        scope_receipt = next((r for r in receipts if r.get("scope") == required_scope.value), None)
        
        if not scope_receipt:
            return False, f"{required_scope.name}_APPROVAL_REQUIRED: No formal approval found"
            
        if scope_receipt.get("status") == ApprovalStatus.REJECTED.value:
            return False, f"REVIEW_REJECTED: {required_scope.name} review was rejected. Rationale: {scope_receipt.get('comment')}"
            
        if scope_receipt.get("status") != ApprovalStatus.APPROVED.value:
            return False, f"{required_scope.name}_APPROVAL_PENDING: Waiting for team alignment"

        return True, ""

    def generate_handoff_summary(self, context: dict[str, Any]) -> dict[str, Any]:
        """產出團隊對齊摘要 (Handoff Bundle)"""
        return {
            "task_id": context.get("instance_id"),
            "design_sealed": any(r.get("scope") == "design" and r.get("status") == "approved" for r in context.get("approval_receipts", [])),
            "outline_sealed": any(r.get("scope") == "outline" and r.get("status") == "approved" for r in context.get("approval_receipts", [])),
            "budget_status": context.get("budget_status", "low_pressure"),
            "risk_mitigation": context.get("mitigation_plans", [])
        }
