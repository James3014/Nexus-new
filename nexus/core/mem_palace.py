import os
from pathlib import Path

class MemoryPalace:
    """實體化規約宮殿，負責 MUSE_PROTO.md 的運行時校驗。"""
    def __init__(self, proto_path: Path = Path("MUSE_PROTO.md")):
        self.proto_path = proto_path
        self.rules = ["ZERO-DEAL", "SSOT-GIT", "ARTIFACT-ONLY"]

    def audit_action(self, phase: str, action: str) -> bool:
        """執行規約審計。"""
        # 模擬審計：禁止在 D 階段沒有證據的行動
        if phase == "D" and "evidence" not in action.lower():
            return False
        return True
