import logging
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CIHealer:
    """
    🩹 Nexus CI 自癒器 (Composio P2)
    攔截 CI 失敗日誌，自動定位錯誤並發動修復循環。
    """
    
    def __init__(self, workspace_root: str):
        self.workspace = workspace_root

    def extract_error(self, log_content: str) -> Optional[str]:
        """🎯 從日誌中提取 Traceback 或錯誤摘要"""
        # 簡單正則提取 Python 錯誤類型
        match = re.search(r'(AttributeError|NameError|TypeError|SyntaxError): .*', log_content)
        if match:
            return match.group(0)
        return "Unknown CI Failure"

    def on_ci_fail(self, ci_log: str) -> Dict[str, Any]:
        """🎯 自癒攔截點：重啟修復階段"""
        error = self.extract_error(ci_log)
        logger.warning(f"🩹 [CIHealer] Detected failure: {error}. Launching Phase R (Repair)...")
        
        # 實體修復循環真值 (模擬重啟 Repair 階段)
        return {
            "status": "SELF_HEAL_TRIGGERED",
            "detected_error": error,
            "next_step": "Phase.R_HOTFIX"
        }
