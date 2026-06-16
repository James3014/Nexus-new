from typing import Any, List, Tuple
from nexus.services.local_heal.interface import IPhase, PhaseResult, LocalizationInput, LocalizationOutput
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer, LocalizationBundle
from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.context_budget import ContextBudgetManager

class LocalizationPhase(IPhase):
    """Phase 3: Localization (深度定位 - 函式級精煉)"""
    def __init__(self, localizer: GranularMethodLocalizer, budget_manager: ContextBudgetManager):
        self.localizer = localizer
        self.budget_manager = budget_manager

    def run(self, input_data: LocalizationInput) -> LocalizationOutput:
        """Stateless TDD-ready execution logic."""
        from nexus.services.local_heal.interface import LocalizedFile
        search_symbols = input_data.plan.search_symbols if input_data.plan else []
        
        # build_query 相容保護：舊測試 mock 可能沒有此方法
        if hasattr(self.localizer, "build_query"):
            rank_query = self.localizer.build_query(
                input_data.problem_statement,
                search_symbols=search_symbols,
                evidence=input_data.repro_evidence
            )
        else:
            rank_query = input_data.problem_statement
        
        # 1. 檔案級排序
        ranked = self.localizer.rank_files(
            rank_query, 
            input_data.repo_dir, 
            search_symbols=search_symbols
        )
        
        if not ranked:
            return LocalizationOutput(
                success=False,
                localized_files=[],
                model_decisions=[],
                error_reason="LOCALIZATION_NO_FILES_FOUND"
            )

        # refine_query 相容保護
        if hasattr(self.localizer, "build_query"):
            refine_query = self.localizer.build_query(
                input_data.problem_statement,
                search_symbols=search_symbols,
                evidence=input_data.repro_evidence
            )
        else:
            refine_query = input_data.problem_statement

        # 2. 舊版單測 monkeypatch 相容轉發
        if hasattr(self.localizer, "extract_relevant_code"):
            results = self.localizer.extract_relevant_code(ranked, refine_query)
            loc_files = [LocalizedFile(path=r[0], content=r[1]) for r in results]
            return LocalizationOutput(
                success=True,
                localized_files=loc_files,
                model_decisions=[]
            )

        # 3. 函式級精煉 (Surgical Slicing)
        bundles: List[LocalizationBundle] = []
        for _, doc in ranked:
            bundle = self.localizer.localize(doc["path"], doc["content"], refine_query)
            bundles.append(bundle)
            
        localized_files = []
        model_decisions = []
        for bundle in bundles:
            localized_files.append(LocalizedFile(
                path=bundle.file_path, 
                content=bundle.build_context(),
                relevance_score=bundle.confidence
            ))
            model_decisions.append({
                "phase": "localization",
                "file": bundle.file_path,
                "slice_mode": bundle.fallback_mode or "granular",
                "slice_reason": bundle.slice_reason,
                "confidence": bundle.confidence
            })

        # 4. 預算限制 (暫時保持舊接口相容，轉換為 tuple 再轉回)
        # TODO: Update budget_manager to handle LocalizedFile objects
        loc_tuples = [(f.path, f.content) for f in localized_files]
        fitted_tuples = self.budget_manager.enforce_hard_limit(loc_tuples)
        
        fitted_files = []
        for path, content in fitted_tuples:
            # Re-associate with scores if needed
            fitted_files.append(LocalizedFile(path=path, content=content))
        
        if not fitted_files:
            return LocalizationOutput(
                success=False,
                localized_files=[],
                model_decisions=model_decisions,
                error_reason="LOCALIZATION_EMPTY"
            )
            
        return LocalizationOutput(
            success=True,
            localized_files=fitted_files,
            model_decisions=model_decisions
        )

    def execute(self, ctx: HealContext) -> PhaseResult:
        if ctx.op.localized_files:
            return PhaseResult(success=True)

        input_data = LocalizationInput(
            problem_statement=ctx.op.problem_statement,
            repro_evidence=ctx.op.repro_evidence,
            repo_dir=ctx.op.repo_dir,
            plan=ctx.op.plan
        )

        output = self.run(input_data)
        
        ctx.op.localized_files = output.localized_files
        ctx.op.model_decisions.extend(output.model_decisions)
        
        if not output.success:
            return PhaseResult(success=False, exit_layer="localization", failure_reason=output.failure_reason)

        return PhaseResult(success=True)
