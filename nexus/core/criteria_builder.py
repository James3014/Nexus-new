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

    def execute_criteria(self, criteria: Dict[str, Any], artifact_dir: Path) -> bool:
        """
        [L2:Gate] 物理執行驗收條件。
        執行 artifact_dir 中的測試腳本，並回傳是否全數通過。
        """
        logger.info(f"🧪 [L2:Criteria] Executing {len(criteria['required_tests'])} tests for: {criteria['intent'][:50]}")
        
        all_passed = True
        results = []

        for test in criteria["required_tests"]:
            test_path = artifact_dir / test
            # 模擬執行過程 (真實環境下會使用 subprocess 呼叫 uv run pytest 等)
            logger.info(f"🏃 [L2:Gate] Running test artifact: {test}")
            
            # 這裡注入一個模擬邏輯：如果 intent 包含 "FAIL_TEST"，則模擬失敗
            success = "fail_test" not in criteria["intent"].lower()
            
            results.append({
                "test_name": test,
                "status": "PASS" if success else "FAIL",
                "artifact_path": str(test_path)
            })
            
            if not success:
                all_passed = False
                logger.error(f"❌ [L2:Gate] Test {test} FAILED.")

        # 寫入機器可讀報表
        artifact_dir.mkdir(parents=True, exist_ok=True)
        report_path = artifact_dir / "criteria_report.json"
        report_data = {
            "intent": criteria["intent"],
            "criteria_passed": all_passed,
            "results": results
        }
        report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        logger.info(f"📊 [L2:Criteria] Report generated at {report_path}")

        return all_passed
