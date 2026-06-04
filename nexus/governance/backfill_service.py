from typing import Dict, Any, List, Optional
from nexus.telemetry.telemetry_models import TelemetryBundle
from nexus.replay.replay_artifact import ReplayArtifact

class BackfillService:
    """
    🛠️ Task: Governance Backfill Service
    職責: 將 v27/v28.0 的舊 Receipt 與 Memory 轉換為 v28.1 標準契約。
    對缺失指標標記為 BACKFILL_NEEDED，嚴禁假造 PASS。
    """
    
    @staticmethod
    def migrate_receipt(old_receipt: Dict[str, Any]) -> Dict[str, Any]:
        """
        遷移舊版 Receipt。
        """
        # 提取 Telemetry 事實
        raw_telemetry = old_receipt.get("telemetry", {})
        
        # 標準化為 TelemetryBundle (可能有缺失)
        bundle = TelemetryBundle(
            wall_time_ms=raw_telemetry.get("wall_time_ms"),
            token_usage=raw_telemetry.get("token_usage"),
            provider_costs=raw_telemetry.get("provider_costs"),
            overhead_ms=raw_telemetry.get("overhead_ms")
        )
        
        # 標記狀態
        status = "PASS" if old_receipt.get("allowed") else "FAIL"
        if not bundle.complete:
            status = "BACKFILL_NEEDED"
            
        return {
            "task_id": old_receipt.get("task_id", "unknown"),
            "status": status,
            "telemetry_bundle": bundle,
            "is_claimable": bundle.complete and status == "PASS",
            "version_migrated": "v28.1"
        }

    @staticmethod
    def migrate_memory_hit(old_hit: Dict[str, Any], default_version: int = 1) -> Dict[str, Any]:
        """
        將舊 Memory 注入版本邊界。
        """
        new_hit = old_hit.copy()
        if "state_version" not in new_hit:
            new_hit["state_version"] = default_version
        return new_hit
