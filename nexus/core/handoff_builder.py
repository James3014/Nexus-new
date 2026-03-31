from datetime import datetime, timezone
from typing import List, Dict, Any

class HandoffBuilder:
    """
    📋 Nexus 任務交接建立器 (AOS-P5.3)
    負責將主代理的意圖與權限邊界封裝為子代理可理解的 Handoff JSON。
    """
    
    def build(self, task: str, scope: List[str], phase: str = "P", parent_id: str = "") -> Dict[str, Any]:
        """建立標準化的 Handoff Payload"""
        return {
            "version": "v22.handoff",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent_id": parent_id,
            "task": task,
            "scope": scope,
            "enforced_phase": phase,
            "constraints": {
                "direct_commit": False,
                "governance_required": True,
                "isolation_level": "WORKTREE"
            }
        }
