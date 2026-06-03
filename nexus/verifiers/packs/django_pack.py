from typing import List, Dict
from nexus.verifiers.contracts import VerifierVerdict
from nexus.verifiers.domain.name_sanity import NameSanityVerifier
from nexus.verifiers.domain.django_semantic import DjangoSemanticVerifier
from nexus.verifiers.packs.base import VerifierPack

class DjangoPack(VerifierPack):
    """
    🎸 Task T9: Django Domain Pack
    職責: 封裝 Django 專屬的語義與命名驗證規則。
    """
    @property
    def name(self): return "django_pack"

    @property
    def domain_tags(self): return ["django", "web", "orm"]

    def evaluate_all(self, candidate_id: str, patch: str) -> List[VerifierVerdict]:
        return [
            NameSanityVerifier.evaluate(candidate_id, patch),
            DjangoSemanticVerifier.evaluate(candidate_id, patch)
        ]
