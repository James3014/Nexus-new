from typing import Any, Dict, List, Optional, Tuple
import logging
import json
import time
from nexus.core.event_bus import NexusEventBus

logger = logging.getLogger(__name__)

class AsyncFeedbackRouter:
    """🧬 Nexus v26.0 異步反饋路由 (Composio AO Dimension 3)
    
    具現化外部信號 (CI/GitHub Webhook) 與 trace_id 的動態路由。
    """

    def __init__(self, project_root):
        self.project_root = project_root
        self.event_bus = NexusEventBus()
        self.event_bus.configure(self.project_root)

    def handle_external_webhook(self, webhook_data: Dict[str, Any]):
        """處理 Mock Webhook 信號並注入路由"""
        payload = webhook_data.get("payload", {})
        trace_id = payload.get("trace_id")
        event_type = webhook_data.get("event_type", "ci_reaction")
        
        if not trace_id:
            logger.warning("⚠️ Webhook 缺失 trace_id，無法精位路由。")
            return False

        logger.info(f"⚡ [Reaction] Webhook received for Trace: {trace_id}")
        
        # 注入信號 (Dimension 3: 反應式自癒起點)
        signal = {
            "source": "github_webhook",
            "trace_id": trace_id,
            "status": payload.get("status"),
            "feedback": payload.get("comment", "No comment provided.")
        }
        
        self.event_bus.inject_signal(event_type, signal)
        logger.info(f"✅ [Reaction] Signal injected into Agent Trace Loop.")
        return True

    def simulate_ci_failure(self, trace_id: str):
        """模擬 CI 失敗信號的注入 (用於 A 階段壓力測試)"""
        mock_data = {
            "event_type": "ci_failed",
            "payload": {
                "trace_id": trace_id,
                "status": "failure",
                "comment": "Lint error detected in shard subtask."
            }
        }
        return self.handle_external_webhook(mock_data)
