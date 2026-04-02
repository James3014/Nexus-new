from typing import Any, Dict, List, Optional, Tuple
import logging
import json

logger = logging.getLogger(__name__)

class NexusNeuralAggregator:
    """語義上下文彙整器 (Neural Aggregator)
    
    實現 Automaton 的 Triage 邏輯，將 Agent 對話壓縮為精煉的狀態快照。
    數據真值轉向 Nexus 生產環境。
    """
    
    def __init__(self, token_budget: int = 1500):
        self.token_budget = token_budget

    def triage_summarize(self, events: List[Dict[str, Any]]) -> str:
        """執行物理 Triage 壓縮。
        
        邏輯：
        - Heartbeat/Progress: 僅計數 (Count)
        - Error/Blocked: 全量保留 (Full)
        - Result/Completed: 摘要保留 (Summary)
        """
        full_details = []
        heartbeat_count = 0
        summary_entries = []
        
        for event in events:
            kind = event.get("kind", "").lower()
            message = event.get("message", "")
            
            # 1. Triage Logic
            if any(p in kind for p in ["error", "failed", "blocked"]):
                full_details.append(f"- [CRITICAL] {kind}: {message}")
            elif any(p in kind for p in ["heartbeat", "alive", "ping"]):
                heartbeat_count += 1
            elif any(p in kind for p in ["completed", "done", "result"]):
                summary_entries.append(f"- [RESULT] {kind}: {message[:100]}...")
            else:
                heartbeat_count += 1 # Default to low noise
        
        # 2. Render Physical Snapshot
        lines = ["# Agent Context Snapshot (Hardened)"]
        if full_details:
            lines.append("\n## Critical Evidence:")
            lines.extend(full_details)
            
        if summary_entries:
            lines.append("\n## Key Deliverables:")
            lines.extend(summary_entries)
            
        if heartbeat_count > 0:
            lines.append(f"\n- [NOISE_REDUCED] Heartbeat updates: {heartbeat_count}")
            
        snapshot = "\n".join(lines)
        
        # 3. Budget Control
        if len(snapshot) > self.token_budget * 4:
            snapshot = snapshot[:self.token_budget * 4] + "\n[SNAPSHOT_TRUNCATED_FOR_BUDGET]"
            
        logger.info("context_aggregation_completed [%d_heartbeats_suppressed]", heartbeat_count)
        return snapshot
