#!/usr/bin/env python3
import typing
import time
import logging
import threading
from datetime import datetime, timezone

# 🛡️ Nexus v24.0 Hardened Metrics Aggregator (Swarm-Ready)
# [NEXUS CONFIG: FAIL-CLOSED AGGREGATION]
logger = logging.getLogger(__name__)

class MetricsAggregator:
    """
    📊 指標聚合器 (MetricsAggregator v24.0 Eternal)
    職責：在高併發環境下原子化收集並聚合 PDRAC 執行指標。
    
    [EVOLUTION LOG]:
    - Round 1-10: Thread-safety implementation with threading.Lock.
    - Round 11-20: Atomic buffer for Swarm-scale telemetry & Judicial summaries.
    """
    def __init__(self):
        self.version = "v24.0.eternal.hardened"
        self._lock = threading.Lock()
        self._buffer: typing.List[typing.Dict[str, typing.Any]] = [] 

    def stream_ingest(self, result: typing.Dict[str, typing.Any]):
        """🚀 原子化流式注入 (v24.0 Swarm Optimization)"""
        with self._lock:
            self._buffer.append(result)
            if len(self._buffer) > 1000:
                logger.warning("⚠️ [Aggregator] Buffer pressure high (>1000 entries).")

    def aggregate_crystallize_payload(self, 
                                   task_id: str, 
                                   skill_id: str, 
                                   passed: bool, 
                                   gate_results: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None,
                                   metadata: typing.Optional[typing.Dict[str, typing.Any]] = None,
                                   phase: str = "P") -> typing.Dict[str, typing.Any]:
        """
        將原始數據聚合為 v24.0 標準 Outcome Payload (Thread-Safe)。
        """
        # Ensure thread-safety during aggregation
        with self._lock:
            local_gate_results = (gate_results or []) + self._buffer
            self._buffer = [] # Atomic clear after harvest
            
        metadata = metadata or {}
        
        total = len(local_gate_results)
        passed_count = sum(1 for r in local_gate_results if r.get("passed") or r.get("pass"))
        pass_rate = (passed_count / total * 100.0) if total > 0 else 0.0
        
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        
        # 🧪 [v24.0 Evolution] Judicial-Aware Summary Generation
        summary = self._generate_judicial_summary(skill_id, passed, passed_count, total, phase, metadata)
        
        # 💎 結晶化：構建真值 Payload (v24.0 Schema)
        payload = {
            "timestamp_utc": timestamp_utc,
            "timestamp": time.time(),
            "task_id": task_id,
            "decision_id": task_id,
            "phase": phase,
            "skill_id": skill_id,
            "pass": passed,
            "passed": passed,
            "metrics": {
                "pass_rate": pass_rate,
                "gate_passed": passed_count,
                "gate_total": total,
                "aggregator_version": self.version,
                "concurrency_safe": True
            },
            "summary": summary,
            "metadata": metadata,
            "gate_results": local_gate_results
        }
        
        logger.info(f"💎 [MetricsAggregator:v24.0] Crystallized with Atomic Safety for {task_id}")
        return payload

    def _generate_judicial_summary(self, skill_id: str, passed: bool, passed_count: int, total: int, phase: str, metadata: dict) -> str:
        """生成具備司法指引意義的對等分析摘要"""
        status = "成功" if passed else "失敗"
        base_msg = f"技能 [{skill_id}] 於階段 [{phase}] 執行{status}。通過率: {passed_count}/{total}。"
        
        # 🧪 [Round 20] Inject Judicial Explanation if failed
        if not passed:
            reason = metadata.get("policy_violation") or metadata.get("last_audit_failure", "未知規約衝突")
            base_msg += f" ❌ 司法判定: POLICY_VIOLATION[{reason}]。建議啟動 Bayesian-Repair 梯度修復。"
            
        return base_msg
