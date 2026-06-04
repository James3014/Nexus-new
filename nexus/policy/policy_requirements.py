
from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class PolicyRequirements:
    mode: str # readonly, sandbox, live
    approval_gates: List[str]
    max_rollout_fraction: float
