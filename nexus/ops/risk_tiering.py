
from enum import Enum, auto
from nexus.problem.taxonomy import ProblemClass, Severity

class RiskTier(Enum):
    P0_ULTRA = auto()
    P1_HIGH = auto()
    P2_STANDARD = auto()
    P3_LOW = auto()

def get_risk_tier(problem_class: ProblemClass, severity: Severity) -> RiskTier:
    if problem_class == ProblemClass.PRODUCTION or severity == Severity.CRITICAL:
        return RiskTier.P0_ULTRA
    if problem_class == ProblemClass.SAFETY or severity == Severity.HIGH:
        return RiskTier.P1_HIGH
    return RiskTier.P2_STANDARD
