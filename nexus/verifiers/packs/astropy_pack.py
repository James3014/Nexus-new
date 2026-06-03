from typing import List, Dict
from nexus.verifiers.contracts import VerifierVerdict, EvidenceRef
from nexus.verifiers.domain.name_sanity import NameSanityVerifier
from nexus.verifiers.domain.inheritance import DeepInheritanceVerifier
from nexus.verifiers.packs.base import VerifierPack

class AstropyPack(VerifierPack):
    """
    🌌 Task T8: Astropy Domain Pack
    職責: 封裝所有與 Astropy 相關的物理驗證規則。
    """
    @property
    def name(self): return "astropy_pack"

    @property
    def domain_tags(self): return ["astropy", "science", "ffi"]

    def evaluate_all(self, candidate_id: str, patch: str) -> List[VerifierVerdict]:
        # 同時執行多個內置驗證器
        return [
            NameSanityVerifier.evaluate(candidate_id, patch),
            DeepInheritanceVerifier.evaluate(candidate_id, patch)
        ]
