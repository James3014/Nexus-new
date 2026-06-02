from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class RouteDecision:
    """[NEXUS v2.5.1] Published Interface: Route Decision DTO"""
    flow: str
    lite_preferred: bool
    reason: str
    version: str = "1.0"

@dataclass(frozen=True)
class CostClassification:
    """[NEXUS v2.5.1] Published Interface: Cost Evidence DTO"""
    profile: str
    clean_evidence: bool
    version: str = "1.0"

@dataclass(frozen=True)
class ChainAssembly:
    """[NEXUS v2.5.1] Published Interface: Capability Chain DTO"""
    core: List[str]
    optional: List[str]
    version: str = "1.0"
