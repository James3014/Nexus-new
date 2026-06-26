#!/usr/bin/env python3
import os
import logging
import copy
from pathlib import Path
from typing import Dict, Any, Optional, Set

try:
    import yaml
except ImportError:
    yaml = None

from nexus.core.gate_evaluator import AcceptancePolicy

logger = logging.getLogger(__name__)


class PolicyLoader:
    """
    📂 政策載入器 (PolicyLoader v24.0 Eternal)
    
    [EVOLUTION LOG]:
    - Round 1-5: Base static merge implementation.
    - Round 6-12: Deep-Reconcile algorithm with copy.deepcopy.
    - Round 13-20: Circular reference protection & Atomic fallback.
    """
    
    @staticmethod
    def _deep_reconcile(base: Dict[str, Any], override: Dict[str, Any], _visited: Optional[Set[int]] = None) -> Dict[str, Any]:
        """
        🛡️ MUSE-DEEP-RECONCILE (v24.0 Hardened)
        支持高維遞迴對齊與循環引用偵測。
        """
        _visited = _visited or set()
        base_id = id(base)
        if base_id in _visited:
            logger.warning("⚠️ [PolicyLoader] Circular reference detected, breaking recursion.")
            return copy.deepcopy(base)
        _visited.add(base_id)
        
        result = copy.deepcopy(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = PolicyLoader._deep_reconcile(result[k], v, _visited)
            else:
                result[k] = copy.deepcopy(v)
        return result

    @staticmethod
    def _validate_schema(data: Dict[str, Any]) -> bool:
        """✅ Schema 硬性校驗 (AOS-131.5)"""
        required_blocks = ["gates", "health"]
        for block in required_blocks:
            if block not in data or not isinstance(data[block], dict):
                logger.debug("⚠️ [PolicyLoader] Missing or invalid block: %s", block)
                return False
        return True

    @staticmethod
    def load(project_root: str, env: str = "dev") -> AcceptancePolicy:
        """
        🔗 層級式載入 (Round 20 Converged):
        支援原子級屬性保護與環境自癒。
        """
        path = Path(project_root) / ".nexus" / "governance_policy.yaml"
        
        if not path.exists():
            return AcceptancePolicy.default()
            
        try:
            if yaml is None:
                raise ImportError("PyYAML not installed")
            with path.open("r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}
                
            base_config = raw_data.get("default", {})
            env_overrides = raw_data.get("environments", {}).get(env, {})
            
            # 🧪 [Round 20] 貝葉斯極致演化：執行深層對齊與校驗
            merged_payload = PolicyLoader._deep_reconcile(base_config, env_overrides)
            
            if not PolicyLoader._validate_schema(merged_payload):
                logger.warning("⚠️ [PolicyLoader] Schema validation failed for env: %s. Using default.", env)
                return AcceptancePolicy.default()
            
            return AcceptancePolicy.from_dict(merged_payload)
                
        except (ImportError, Exception) as e:
            logger.error("⚙️ [PolicyLoader] YAML Terminal Parse Error: %s", e)
            return AcceptancePolicy.default()
