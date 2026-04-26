# Proxy to unified MemPalace in services to resolve TD-5
from nexus.services.mem_palace import MemPalace

class MemoryPalace(MemPalace):
    """實體化規約宮殿，負責 MUSE_PROTO.md 的運行時校驗 (Alias for backwards compatibility)."""
    def __init__(self, proto_path=None):
        super().__init__()
        self.proto_path = proto_path or self.project_root / "MUSE_PROTO.md"
        self.rules = ["ZERO-DEAL", "SSOT-GIT", "ARTIFACT-ONLY"]
