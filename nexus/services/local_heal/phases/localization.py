from typing import Any
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.localizer import Localizer
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.context_budget import ContextBudgetManager

class LocalizationPhase(IPhase):
    """Phase 3: Localization (深度定位)"""
    def __init__(self, localizer: Localizer, budget_manager: ContextBudgetManager):
        self.localizer = localizer
        self.budget_manager = budget_manager

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.localized_files:
            return PhaseResult(success=True)

        rank_query = self.localizer.build_query(
            ctx.op.problem_statement,
            search_symbols=ctx.op.plan.get("search_symbols", []),
        )
        refine_query = self.localizer.build_query(
            ctx.op.problem_statement,
            search_symbols=ctx.op.plan.get("search_symbols", []),
            evidence=ctx.op.repro_evidence,
        )
        
        search_symbols = ctx.op.plan.get("search_symbols", [])
        ranked = self.localizer.rank_files(rank_query, ctx.op.repo_dir, search_symbols=search_symbols)
        
        for _, doc in ranked:
            doc["issue_desc"] = refine_query
            
        raw_files = self.localizer.extract_relevant_code(ranked, query=refine_query)
        ctx.op.localized_files = self.budget_manager.enforce_hard_limit(raw_files)
        
        if not ctx.op.localized_files:
            return PhaseResult(success=False, exit_layer="localization", error_reason="LOCALIZATION_EMPTY")
            
        return PhaseResult(success=True)
