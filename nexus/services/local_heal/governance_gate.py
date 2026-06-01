from typing import Any
from nexus.services.local_heal.context import HealContext

class GovernanceGate:
    """🛡️ Nexus Governance Gate (Accountability Enforcement)"""
    
    @staticmethod
    def audit(ctx: HealContext) -> None:
        """
        審計當前管線執行的「層級對齊」與「原因對齊」。
        """
        # 1. 判定實際原因家族 (Actual Reason Family)
        actual_reason = str(getattr(ctx.op, "failure_reason", "") or "")
        
        if getattr(ctx.op, "solve_eligible", False):
            ctx.gov.actual_reason_family = "SOLVED"
        elif "ENV_" in actual_reason or "ENVIRONMENT" in actual_reason or "ImportError" in actual_reason:
            ctx.gov.actual_reason_family = "env_noise"
        elif "ALREADY_FIXED" in actual_reason:
            ctx.gov.actual_reason_family = "already_fixed"
        elif "TIMEOUT" in actual_reason or "OOM" in actual_reason:
            ctx.gov.actual_reason_family = "infra_limit"
        else:
            ctx.gov.actual_reason_family = "unknown"
            
        # 2. 判定對齊狀態
        ctx.gov.stop_layer_matched = (ctx.gov.gate_exit == ctx.gov.expected_stop_layer)
        ctx.gov.family_matched = (ctx.gov.actual_reason_family == ctx.gov.expected_reason_family)
