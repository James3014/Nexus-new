from typing import Dict

class ResearchPolicy:
    def __init__(self, fast_mode: bool = False):
        self.fast_mode = fast_mode
        self.trigger_keywords = ["SDK", "WebSocket", "API", "CLOUD", "AWS"]
        
    def should_research(self, decision: Dict, task_desc: str) -> bool:
        """根據決策、模式與任務內容判斷是否啟動 X-phase"""
        if self.fast_mode:
            return False
            
        if decision.get("external_needed"):
            return True
            
        # 關鍵字觸發 (v1.8 legacy alignment)
        for kw in self.trigger_keywords:
            if kw.upper() in task_desc.upper():
                return True
                
        return False
