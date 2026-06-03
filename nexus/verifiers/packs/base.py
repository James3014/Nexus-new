from abc import ABC, abstractmethod
from typing import List, Dict, Any
from nexus.verifiers.contracts import VerifierVerdict

class VerifierPack(ABC):
    """
    📦 Task T7: Verifier Pack Interface
    職責: 定義一組驗證器的邏輯集合。
    """
    @property
    @abstractmethod
    def name(self) -> str: pass

    @property
    @abstractmethod
    def domain_tags(self) -> List[str]: pass

    @abstractmethod
    def evaluate_all(self, candidate_id: str, patch: str) -> List[VerifierVerdict]:
        pass
