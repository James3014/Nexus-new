import re
import logging

logger = logging.getLogger(__name__)

class RationalizationError(Exception):
    """🚫 當偵測到 Agent 試圖行為合理化時拋出。"""
    pass

class CritiqueEngine:

    RESTRICTED_CLAIMS = [
        "solved", "fixed", "closure", "verified", "production-ready", 
        "industrial-grade", "100%", "bit-perfect"
    ]

    def detect_overclaim(self, response_text: str, evidence_bundle: dict = None):
        """🔍 掃描輸出中的過度承諾。"""
        if not response_text: return True
        
        found = [w for w in self.RESTRICTED_CLAIMS if w in response_text.lower()]
        if found:
            # 檢查證據是否達標 (簡化邏輯：無 EvidenceBundle 則報錯)
            if not evidence_bundle or evidence_bundle.get("confidence_level") != "HIGH":
                raise RationalizationError(f"🛑 Overclaim detected: {found}. High confidence evidence bundle required.")
        return True

    """🛡️ Nexus v25.5 Anti-Rationalization Sensor."""
    
    # 🕵️ 黑名單模式 (來自 v23.5 specs)
    ANTI_RATIONAL = [
        r'skip tests?', r'manual check', r'do later', r'not now',
        r'todo', r'bookmark', r'edge case', r'later step',
        r'暫不測試', r'手動檢查'
    ]

    def prescan(self, plan_text: str):
        """🔍 在執行前掃描計畫文本，攔截規避行為。"""
        if not plan_text:
            return "✅ Intent Neutral"
            
        for pattern in self.ANTI_RATIONAL:
            if re.search(pattern, plan_text, re.I):
                logger.error(f"🛑 [Critique:BLOCKED] Anti-Rationalization triggered: '{pattern}'")
                raise RationalizationError(
                    f"🚫 Anti-Rationalization detected: '{pattern}'\n"
                    "🚨 TDD 鐵律: 禁止規避測試或標記 TODO。請先寫 RED 測試並立即修復。"
                )
        return "✅ Intent Clear"

# Singleton Instance
critique = CritiqueEngine()
