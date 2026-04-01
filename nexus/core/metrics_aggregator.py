#!/usr/bin/env python3
import typing
import time

class MetricsAggregator:
    """
    📊 指標聚合器 (MetricsAggregator)
    負責將 PDRAC 各階段的執行數據、審計結果與元數據聚合為結晶化 Payloads內容及對等。
    """
    def __init__(self):
        pass

    def aggregate_crystallize_payload(self, 
                                   decision_id: str, 
                                   skill_id: str, 
                                   passed: bool, 
                                   gate_results: typing.List[dict],
                                   metadata: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        """
        將原始 Phase 數據聚合為標準 Outcome Payload內容及對等分析內容量。
        """
        total = len(gate_results)
        passed_count = sum(1 for r in gate_results if r.get("passed"))
        pass_rate = (passed_count / total * 100.0) if total > 0 else 0.0

        payload = {
            "decision_id": decision_id,
            "skill_id": skill_id,
            "timestamp": time.time(),
            "pass": passed,
            "metrics": {
                "pass_rate": pass_rate,
                "gate_passed": passed_count,
                "gate_total": total
            },
            "metadata": metadata,
            "gate_results": gate_results
        }
        
        return payload
