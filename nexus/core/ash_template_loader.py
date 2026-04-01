#!/usr/bin/env python3
import yaml
import logging
from pathlib import Path
from typing import Dict, Any
from nexus.core.ash_contracts import ASHCommandTemplate

logger = logging.getLogger(__name__)

class ASHTemplateLoader:
    """📂 ASH 模板載入器：處理 YAML 定義內容性能及對位分析內容及其性內容。性能分析。"""
    
    @staticmethod
    def load(project_root: str) -> Dict[str, ASHCommandTemplate]:
        path = Path(project_root) / ".nexus" / "ash_templates.yaml"
        
        if not path.exists():
            logger.warning("⚠️ [ASHTemplateLoader] Missing %s, using minimal built-ins.", path)
            return ASHTemplateLoader.get_builtin_templates()
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            templates = {}
            for t_id, spec in data.get("templates", {}).items():
                templates[t_id] = ASHCommandTemplate(
                    id=t_id,
                    action=spec.get("action", t_id),
                    params=spec.get("params", {}),
                    constraints=spec.get("constraints", {})
                )
            
            logger.info("📡 [ASHTemplateLoader] Loaded %d templates from %s", len(templates), path)
            return templates
            
        except Exception as e:
            logger.error("❌ [ASHTemplateLoader] Failed to load templates: %s", e)
            return ASHTemplateLoader.get_builtin_templates()

    @staticmethod
    def get_builtin_templates() -> Dict[str, ASHCommandTemplate]:
        """內建基準模板庫其性質內容及底位回退分析。性能分析。"""
        return {
            "patch": ASHCommandTemplate("patch", "apply_patch"),
            "search": ASHCommandTemplate("search", "search_lessons"),
            "verify": ASHCommandTemplate("verify", "regression_test")
        }
