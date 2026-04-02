from typing import Any, Dict, List, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

class HazardClassifier:
    """
    ⚠️ Nexus 概率性危險預警 (AOS-P5.6)
    採用權重評分機制對指令進行「零信任」風險分類。
    """
    
    # 物理模式矩陣：模式 -> 基礎權重
    DANGEROUS_PATTERNS = {
        r"p?kill.*": 0.6,
        r"rm\s*[-rf]": 0.8,
        r"curl.*\|.*(bash|sh|zsh)": 0.9,
        r"wget.*\|.*(bash|sh|zsh)": 0.9,
        r"\>\s*/etc/": 0.7,
        r"sudo\s+": 0.5,
        r"chmod\s+777": 0.6
    }

    def hazard_score(self, cmd: str) -> float:
        """🎯 計算指令的綜合危險評分 (0.0 - 1.0)"""
        score = 0.0
        cmd_norm = cmd.strip().lower()
        
        for pattern, weight in self.DANGEROUS_PATTERNS.items():
            if re.search(pattern, cmd_norm):
                score += weight
                
        # 加權複雜度：指令越長越隱落，風險係數微增
        score += len(cmd.split()) * 0.02
        
        return min(score, 1.0)

    def classify(self, cmd: str) -> str:
        """⚖️ 分類指令安全級別"""
        score = self.hazard_score(cmd)
        
        if score >= 0.8:
            logger.error(f"🛑 [Hazard:BLOCKED] High risk score {score:.2f}: {cmd}")
            return "BLOCKED"
        elif score >= 0.5:
            logger.warning(f"⚠️ [Hazard:WARN] Moderate risk score {score:.2f}: {cmd}")
            return "WARN_HUMAN"
            
        return "SAFE"
