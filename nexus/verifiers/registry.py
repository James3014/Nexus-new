from typing import List, Dict, Any, Optional

class VerifierRegistry:
    """
    🗃️ Task T6: Verifier Registry (v26.4)
    職責: 支援外掛註冊、領域標籤 (domain tags)、與生命週期管理。
    """
    _registry: Dict[str, Any] = {}
    _domain_map: Dict[str, List[str]] = {}

    @classmethod
    def register(cls, name: str, verifier_instance: Any, domains: Optional[List[str]] = None):
        cls._registry[name] = verifier_instance
        if domains:
            for d in domains:
                if d not in cls._domain_map:
                    cls._domain_map[d] = []
                cls._domain_map[d].append(name)
        print(f"✅ Verifier Registered: {name} (Domains: {domains})")

    @classmethod
    def get_all_verifiers(cls) -> List[Any]:
        # 回傳依照註冊順序的驗證器
        return list(cls._registry.values())
        
    @classmethod
    def get_verifiers_by_domain(cls, domain: str) -> List[Any]:
        names = cls._domain_map.get(domain, [])
        return [cls._registry[n] for n in names]

    @classmethod
    def clear(cls):
        cls._registry = {}
        cls._domain_map = {}
