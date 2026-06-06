from typing import Any, List, Tuple
from nexus.services.local_heal.interface import IPhase, PhaseResult
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer, LocalizationBundle
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.context_budget import ContextBudgetManager

class LocalizationPhase(IPhase):
    """Phase 3: Localization (深度定位 - 函式級精煉)"""
    def __init__(self, localizer: GranularMethodLocalizer, budget_manager: ContextBudgetManager):
        self.localizer = localizer
        self.budget_manager = budget_manager

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.localized_files:
            return PhaseResult(success=True)

        rank_query = self.localizer.build_query(
            ctx.op.problem_statement,
            search_symbols=ctx.op.plan.get("search_symbols", []),
        )
        
        # 1. 檔案級排序
        ranked = self.localizer.rank_files(
            rank_query, 
            ctx.op.repo_dir, 
            search_symbols=ctx.op.plan.get("search_symbols", [])
        )
        
        if not ranked:
            return PhaseResult(success=False, exit_layer="localization", error_reason="LOCALIZATION_NO_FILES_FOUND")

        # 2. 函式級精煉 (Surgical Slicing)
        bundles: List[LocalizationBundle] = []
        refine_query = self.localizer.build_query(
            ctx.op.problem_statement,
            search_symbols=ctx.op.plan.get("search_symbols", []),
            evidence=ctx.op.repro_evidence
        )
        
        for _, doc in ranked:
            bundle = self.localizer.localize(doc["path"], doc["content"], refine_query)
            bundles.append(bundle)
            
        # 3. 遙測與預算管理
        ctx.op.localized_files = []
        for bundle in bundles:
            ctx.op.localized_files.append((bundle.file_path, bundle.to_context_string()))
            
            # 記錄切片遙測
            if "telemetries" not in ctx.op.__dict__:
                 ctx.op.__dict__["telemetries"] = {}
            
            ctx.op.model_decisions.append({
                "phase": "localization",
                "file": bundle.file_path,
                "slice_mode": bundle.fallback_mode or "granular",
                "slice_reason": bundle.slice_reason,
                "confidence": bundle.confidence
            })

        ctx.op.localized_files = self.budget_manager.enforce_hard_limit(ctx.op.localized_files)
        
        if not ctx.op.localized_files:
            return PhaseResult(success=False, exit_layer="localization", error_reason="LOCALIZATION_EMPTY")
            
        return PhaseResult(success=True)
