from typing import Dict, List, Any
from nexus.verifiers.packs.base import VerifierPack

class PackRegistry:
    """
    🗃️ Task T7: Pack Registry
    職責: 管理 Verifier Packs 的動態加載。
    """
    _packs: Dict[str, VerifierPack] = {}

    @classmethod
    def register(cls, pack: VerifierPack):
        cls._packs[pack.name] = pack
        print(f"📦 Pack Registered: {pack.name}")

    @classmethod
    def get_enabled_packs(cls, context_tags: List[str]) -> List[VerifierPack]:
        # 根據任務標籤決定啟用哪些 Packs
        enabled = []
        for pack in cls._packs.values():
            if any(tag in context_tags for tag in pack.domain_tags):
                enabled.append(pack)
        return enabled

    @classmethod
    def clear(cls):
        cls._packs = {}
