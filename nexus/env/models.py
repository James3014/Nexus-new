from dataclasses import dataclass
from typing import List, Optional, Literal

EnvVerdictKind = Literal["ALLOW", "SOFT_BLOCK", "HARD_BLOCK", "NEEDS_REPAIR"]

@dataclass(frozen=True)
class EnvVerdict:
    """[NEXUS v26.1] 環境探測裁決 DTO"""
    kind: EnvVerdictKind
    reason: str
    repair_hints: List[str]
    can_auto_heal: bool = False

@dataclass(frozen=True)
class EnvSnapshot:
    """[NEXUS v26.1] 環境快照"""
    python_version: str
    installed_packages: List[str]
    env_vars: List[str]
