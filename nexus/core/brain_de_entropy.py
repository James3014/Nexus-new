import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class Message:
    """模擬訊息結構"""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def summary(self, length: int = 50) -> str:
        return self.content[:length].replace("\n", " ")

def prune_dialogue(history: List[Dict]) -> str:
    """
    🧬 P2 對話熵減 (v22 De-Entropy)
    壓縮最近 10 輪對話，優先保留物理失敗證據。
    """
    logger.info("✂️ [Entropy] Pruning context history (Target: 10 rounds)...")
    
    # 僅取最近 10 條訊息
    recent_history = history[-10:]
    summary = []
    
    for msg in recent_history:
        content = msg.get("content", "")
        role = msg.get("role", "user")
        
        # 物理保留失敗關鍵點
        if "FAIL" in content or "ERROR" in content:
            summary.append(f"[{role.upper()}:FAIL] {content[:100]}...")
        else:
            summary.append(f"[{role.upper()}] {content[:50]}...")
            
    # 壓縮率預估 > 70%
    result = "\n".join(summary)
    logger.info("✅ [Entropy] Pruned context size: %d characters.", len(result))
    return result
