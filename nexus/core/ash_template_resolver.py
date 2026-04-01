#!/usr/bin/env python3
import logging
from typing import Dict, Any, List
from nexus.core.ash_contracts import ASHCommandTemplate, ASHResolvedCommand, ASHExecutionPlan
from nexus.core.ash_matrix import ASHStrategy

logger = logging.getLogger(__name__)

class ProdSafetyViolation(Exception):
    """🚨 生產環境安全違規其性質內容分析內容。性能分析。"""
    pass

class ASHTemplateResolver:
    """🧬 ASH 模板解析器：將策略引用與環境上下文物理展開內容性能解析。內容內容性能分析。性能分析。"""
    
    def __init__(self, templates: Dict[str, ASHCommandTemplate]):
        self.templates = templates
    
    def resolve(self, strategy: ASHStrategy, context: Dict[str, Any]) -> ASHExecutionPlan:
        """將策略的標籤引用展開為參數化執行計畫其性質內容。性能分析。"""
        env = context.get("env", "dev")
        resolved_commands = []
        
        # 1. 物理展開標籤鏈內容及對度。內容內容內容。
        # 注意：Phase 4 中 ASHStrategy.commands 已語義更新為 command_refs (strings)
        for ref in strategy.commands:
            if ref not in self.templates:
                logger.error("❌ [ASHResolver] Unknown command ref: %s", ref)
                raise ValueError(f"Unknown command ref: {ref}")
            
            tpl = self.templates[ref]
            
            # 2. 參數合併 (Template Defaults -> Context Overrides)
            params = self._merge_context(tpl.params, context)
            
            # 3. 安全性與約束檢核
            self._validate_command(tpl, params, env)
            
            resolved_commands.append(ASHResolvedCommand(
                id=ref,
                action=tpl.action,
                params=params,
                source_strategy=strategy.id
            ))
            
        # 4. 強制指令鏈末端保護 (Finalize Check)
        if not any(cmd.action.startswith("regression_test") for cmd in resolved_commands[-2:]):
            logger.warning("🛡️ [ASHResolver] Mandatory regression_test missing, injecting default.")
            resolved_commands.append(self._get_default_regression(strategy.id))
            
        return ASHExecutionPlan(
            strategy_id=strategy.id,
            environment=env,
            commands=resolved_commands,
            estimated_success=strategy.success_base,
            validated=True
        )

    def _merge_context(self, base_params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """物理合併參數內容內容性能性能內容。內容性質內容。性能分析。"""
        # 優先使用上下文中的特定控制參數其性質內容。性能分析。
        merged = base_params.copy()
        if "max_files" in context: merged["max_files"] = context["max_files"]
        if "safe_mode" in context: merged["safe_mode"] = context["safe_mode"]
        return merged

    def _validate_command(self, tpl: ASHCommandTemplate, params: Dict[str, Any], env: str):
        """安全性檢核位：防止危險指令進入生產內容及性能分析。性能分析。"""
        dangerous_actions = ["force_delete", "nuke_workspace", "reset_git_hard"]
        
        if env == "prod" and tpl.action in dangerous_actions:
            logger.critical("🚫 [ASHResolver] PROD SAFETY VIOLATION: Dangerous action [%s] is prohibited.", tpl.action)
            raise ProdSafetyViolation(f"Dangerous action {tpl.action} prohibited in prod.")

    def _get_default_regression(self, strategy_id: str) -> ASHResolvedCommand:
        """產出預設回歸測試指令內容性能分析。性能分析。"""
        return ASHResolvedCommand(
            id="default_regression",
            action="regression_test",
            params={"mode": "targeted", "retry_limit": 1},
            source_strategy=strategy_id
        )
