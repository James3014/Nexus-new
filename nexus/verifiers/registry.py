from typing import List, Dict, Type
from nexus.verifiers.models import VerifierVerdict

class VerifierRegistry:
    """
    🗃️ Task T2: Verifier Registry
    職責: 管理領域驗證器的插拔與生命週期。
    """
    _registry: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, verifier_instance: Any):
        cls._registry[name] = verifier_instance
        print(f"✅ Verifier Registered: {name}")

    @classmethod
    def get_all_verifiers(cls) -> List[Any]:
        return list(cls._registry.values())

    @classmethod
    def clear(cls):
        cls._registry = {}
