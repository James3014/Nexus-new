from abc import ABC, abstractmethod
from nexus.engine.contracts.verification import VerificationResult

class BaseVerifier(ABC):
    """
    🛡️ BaseVerifier: 驗證器基底類別
    所有驗證器都必須實作 verify 介面，並返回標準化的 VerificationResult。
    遵循 Single Responsibility 原則。
    """
    @abstractmethod
    def verify(self, candidate_patch: str, **kwargs) -> VerificationResult:
        pass
