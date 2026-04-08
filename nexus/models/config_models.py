from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional

class EnforceLevel(str, Enum):
    P0 = "p0"
    P1 = "p1"
    WARN = "warn"
    OFF = "off"

class GovernanceConfig(BaseModel):
    """🛡️ Nexus Governance Config (Typed)"""
    enforce_level: EnforceLevel = EnforceLevel.P0
    wiki_sync_mandatory: bool = True
    anti_reject_level: EnforceLevel = EnforceLevel.WARN
    allowed_domains: List[str] = Field(default_factory=lambda: ["core", "cli", "research"])

class SwarmConfig(BaseModel):
    """🐝 Swarm Cluster Config (Typed)"""
    manager_port: int = 9100
    worker_count: int = 4
    timeout_sec: int = 300
    compute_tier: str = "CLOUD"
