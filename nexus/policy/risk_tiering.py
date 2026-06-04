
from nexus.domain.models import ProblemClass, Severity
def resolve_risk_tier(p_class, severity):
    if p_class == ProblemClass.PRODUCTION or severity == Severity.CRITICAL: return 'P0_ULTRA'
    return 'P1_HIGH' if severity == Severity.HIGH else 'P2_STANDARD'
