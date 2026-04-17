#!/usr/bin/env python3
"""
🧬 Nexus L2 Acceptance Criteria Builder
負責根據任務意圖自動生成量身打造的驗收 Artifact (測試腳本與性能指標)。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger("nexus.criteria")

class CriteriaBuilder:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def build_custom_criteria(self, tactical_intent: str) -> Dict[str, Any]:
        """
        根據意圖生成非通用的驗收條件。
        """
        intent_lower = tactical_intent.lower()
        criteria = {
            "intent": tactical_intent,
            "required_tests": ["standard_acceptance"],
            "performance_goals": {},
            "forbidden_patterns": []
        }

        # 1. 針對高性能意圖
        if any(kw in intent_lower for kw in ["performance", "optimize", "fast", "latency"]):
            criteria["required_tests"].append("latency_benchmark.py")
            criteria["performance_goals"]["max_latency_ms"] = 200
            logger.info("⚡ [L2:Criteria] High-performance intent detected. Adding benchmark gate.")

        # 2. 針對安全性意圖
        if any(kw in intent_lower for kw in ["auth", "security", "bft", "credential"]):
            criteria["required_tests"].append("security_audit_scan.py")
            criteria["forbidden_patterns"].append("hardcoded_secrets")
            logger.info("🛡️ [L2:Criteria] Security-sensitive intent detected. Adding security gate.")

        return criteria

    def materialize_test_scripts(self, criteria: Dict[str, Any], target_dir: Path):
        """
        將驗收條件轉化為真實的物理測試檔案 (Artifacts)。
        """
        target_dir.mkdir(parents=True, exist_ok=True)
        for test in criteria["required_tests"]:
            test_path = target_dir / test

            if not test_path.exists():
                # 這裡模擬生成測試骨架
                content = f"# Auto-generated Artifact for: {criteria['intent']}\nimport sys\nprint('Running {test}...')"
                test_path.write_text(content, encoding="utf-8")
                logger.info(f"🧪 [L2:Criteria] Materialized Artifact: {test}")
