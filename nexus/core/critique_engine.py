import re
import logging
from typing import Dict
from nexus.governance.hallucination_guard import HallucinationGuard

logger = logging.getLogger(__name__)

class RationalizationError(Exception):
    """🚫 當偵測到 Agent 試圖行為合理化時拋出。"""
    pass

class CritiqueEngine:
    def __init__(self):
        self.hallucination_guard = HallucinationGuard()

    def final_review(self, response_text: str, evidence_bundle: Dict) -> str:
        """最終審核 + 幻覺標註"""
        # [NEW: A-1] Counter-Claim retrieval
        try:
            from nexus.research.learn_mode import LearnModeService
            from pathlib import Path
            root = Path(evidence_bundle.get("project_root", ".")) if evidence_bundle else Path(".")
            svc = LearnModeService(root)
            repair_sum = evidence_bundle.get("repair_summary", response_text[:200]) if evidence_bundle else response_text[:200]
            counter_claims = svc.ask(
                topic="known-failures", 
                question=f"problems with {repair_sum}",
                top_k=3
            )
            if counter_claims.get("citations"):
                if evidence_bundle is not None:
                    evidence_bundle["counter_claims"] = [c["claim"] for c in counter_claims["citations"]]
                logger.warning(f"Counter claims found: {[c['claim'] for c in counter_claims['citations']]}")
        except Exception as e:
            logger.debug(f"A-1 counter claim failed: {e}")

        # 1. 執行過度宣稱攔截
        self.detect_overclaim(response_text, evidence_bundle)
        
        # 2. 產生幻覺指數標註
        self.hallucination_guard.analyze(response_text, evidence_bundle)
        hallucination_note = self.hallucination_guard.render()
        
        # 3. 根據分數阻斷
        if self.hallucination_guard.score > 5:
            raise RationalizationError(f"幻覺指數過高: {hallucination_note}")
        
        return f"{response_text}\n{hallucination_note}"

    def anti_rationalization_preflight(self, claim: str, evidence: dict):
        """🛡️ 高風險結論前的強制物理自省。"""
        questions = [
            "Which invariant still might fail?",
            "Is the current evidence sufficient to REFUTE my own claim?",
            "Have I mistaken a narrative summary for a physical test?"
        ]
        if evidence.get("confidence_level") == "HIGH":
            # 檢查 known_gaps
            if not evidence.get("known_gaps"):
                raise RationalizationError("🚨 High confidence claim MUST include known_gaps to prevent rationalization.")
        return questions


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
