#!/usr/bin/env python3
import typing
import time
import logging
from datetime import datetime, timezone

# [Nexus v23.1 Optimization] Hardened Metrics Aggregator v22.Evolution
logger = logging.getLogger(__name__)

class MetricsAggregator:
    """
    📊 指標聚合器 (MetricsAggregator) v22.Evolution
    職責：將 PDRAC 各階段的執行數據、審計結果與元數據，聚合為結晶化的 Outcome Payload。
    遵循 v22 永恆演化契約 (L5.7 Truth)。
    """
    def __init__(self):
        self.version = "v22.optimized.evolution"

    def aggregate_crystallize_payload(self, 
                                   task_id: str, 
                                   skill_id: str, 
                                   passed: bool, 
                                   gate_results: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
                                   metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
                                   phase: str = "P") -> typing.Dict[str, typing.Any]:
        """
        將原始 Phase 數據聚合為標準 Outcome Payload (符合 v22 契約)。
        
        優化點：
        - 契約對齊：包含 v22 必備欄位 (timestamp_utc, phase, phantom_blocked 等)。
        - 穩健性：自動從 gate_results 提取真值。
        - 靈活性：支持自定義 phase。
        """
        gate_results = gate_results or []
        metadata = metadata or {}
        
        total = len(gate_results)
        passed_count = sum(1 for r in gate_results if r.get("passed") or r.get("pass"))
        pass_rate = (passed_count / total * 100.0) if total > 0 else 0.0
        
        # 🛡️ v22 契約欄位對位
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        
        # 從 metadata 或 gate_results 中提取高級訊號
        phantom_blocked = metadata.get("phantom_blocked", False)
        regression_pass_rate = metadata.get("regression_pass_rate", pass_rate)
        self_heal_retry_count = metadata.get("self_heal_retry_count", 0)
        proof_present = metadata.get("proof_present", True if gate_results else False)
        repair_success = metadata.get("repair_success", passed)
        retry_count = metadata.get("retry_count", 0)
        pattern_reuse = metadata.get("pattern_reuse", 0.0)
        next_run_hit = metadata.get("next_run_hit", 0.0)
        
        # 💎 結晶化：構建真值 Payload (v22 Schema)
        payload = {
            "timestamp_utc": timestamp_utc,
            "timestamp": time.time(), # Legacy support
            "task_id": task_id,
            "decision_id": task_id, # Linkage
            "phase": phase,
            "skill_id": skill_id,
            "pass": passed,
            "fail": not passed,
            "passed": passed, # Backward compatibility
            "phantom_blocked": phantom_blocked,
            "regression_pass_rate": regression_pass_rate,
            "self_heal_retry_count": self_heal_retry_count,
            "proof_present": proof_present,
            "repair_success": repair_success,
            "retry_count": retry_count,
            "pattern_reuse": pattern_reuse,
            "next_run_hit": next_run_hit,
            "metrics": {
                "pass_rate": pass_rate,
                "gate_passed": passed_count,
                "gate_total": total,
                "aggregator_version": self.version
            },
            "summary": self._generate_summary(skill_id, passed, passed_count, total, phase),
            "metadata": metadata,
            "gate_results": gate_results
        }
        
        logger.info(f"💎 [MetricsAggregator] v22 Crystallized for {task_id} (Phase: {phase}, Pass: {passed})")
        return payload

    def _generate_summary(self, skill_id: str, passed: bool, passed_count: int, total: int, phase: str) -> str:
        """生成對等分析摘要內容 (Traditional Chinese supported)"""
        status = "成功" if passed else "失敗"
        return f"技能 [{skill_id}] 於階段 [{phase}] 執行{status}。閘門通過率: {passed_count}/{total}。"
