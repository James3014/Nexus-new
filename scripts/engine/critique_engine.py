#!/usr/bin/env python3
"""
🛡️ Nexus Anti-Rationalization Sensor (v23.8 Hardened)

Scans agent intent/plan text for lazy engineering excuses
and blocks execution with mandatory rebuttals.
"""
import re
import logging

logger = logging.getLogger(__name__)


class RationalizationError(Exception):
    """🚫 當偵測到 Agent 試圖行為合理化時拋出。"""
    pass


class CritiqueEngine:
    """🛡️ Nexus Anti-Rationalization Sensor (v23.8 Hardened)."""

    # 🕵️ 行為黑名單模式 (Phase 8 擴展)
    ANTI_RATIONAL = [
        r'skip.*tests?', r'skip.*testing', r'manual check',
        r'do later', r'not now',
        r'bookmark', r'later step',
        r'暫不測試', r'手動檢查',
        r'no tests? needed', r'will fix later', r'manual verif',
        r'改動太小.*不需要測試', r'CI 之後再補',
    ]

    def prescan(self, text: str):
        """🔍 掃描計畫或思考內容，攔截規避行為。"""
        if not text:
            return "✅ Intent Neutral"

        for pattern in self.ANTI_RATIONAL:
            if re.search(pattern, text, re.I):
                logger.error(
                    f"🛑 [Critique:BLOCKED] Anti-Rationalization triggered: '{pattern}'"
                )
                raise RationalizationError(
                    f"🚫 Anti-Rationalization detected: '{pattern}'\n"
                    "🚨 Nexus 鐵律: 禁止規避測試、標記 TODO 或採取人工驗證藉口。\n"
                    "💡 強制建議: 請先撰寫一個會 Failure 的測試案例，並立即進行物理修復。"
                )
        return "✅ Intent Clear"


# Singleton Instance
critique = CritiqueEngine()

if __name__ == "__main__":
    try:
        critique.prescan("I will skip the tests for now and fix it later.")
    except RationalizationError as e:
        print(f"Caught: {e}")
