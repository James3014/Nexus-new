from typing import List, Set
import os

class CanaryGuard:
    """
    🐥 Task: Observation-only & Canary (Rollout)
    職責: 實施受控發佈，限制只有 Allowlist 中的 Domain 才能執行自動晉升。
    """
    def __init__(self, allowlist: Set[str] = None):
        self.allowlist = allowlist or {"astropy", "django"} # 預設安全域

    def is_authorized(self, domain_id: str) -> bool:
        """檢查該 Domain 是否獲得自治授權"""
        return domain_id in self.allowlist

    def is_observation_mode(self) -> bool:
        """檢查是否處於『只觀測、不放行』模式"""
        return os.environ.get("NEXUS_GOVERNANCE_MODE") == "OBSERVATION"
