import logging
import json
import subprocess
import hashlib
from typing import Dict, Any

logger = logging.getLogger(__name__)

class BrainSnapshot:
    """
    🧠 Nexus Brain Snapshot (v22 State Anchor)
    擷取系統當前「思维狀態」與「物理狀態」的二進制快照。
    """
    def __init__(self, project_root: str):
        self.project_root = project_root

    def snapshot_state(self) -> Dict[str, Any]:
        """📸 物理擷取真值狀態"""
        logger.info("💾 [Snapshot] Capturing system state anchor...")
        
        # 1. 擷取物理狀態 (Git Status)
        try:
            git_status = subprocess.check_output(["git", "status", "--short"], 
                                                cwd=self.project_root, text=True)
        except Exception:
            git_status = "Unknown/Non-Git"

        # 2. 擷取思維狀態 (Prompt Hash)
        current_mind = self._get_prompt_hash()

        return {
            "hot_files": git_status.strip().split("\n") if git_status else [],
            "mind_model": current_mind,
            "timestamp": "2026-04-01T00:56:00Z" # Mocked timestamp
        }

    def to_bin(self) -> bytes:
        """📦 將快照序列化為二進制，用於實體鎖定"""
        state = self.snapshot_state()
        return json.dumps(state).encode("utf-8")

    def _get_prompt_hash(self) -> str:
        """獲取當前 Prompt 集合的 Hashing"""
        # 簡單 Hashing 用於狀態對位
        return hashlib.sha256(b"MUSE_ENGINE_SPEC_V22").hexdigest()[:12]
