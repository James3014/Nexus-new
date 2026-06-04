from nexus.domain.models import ProblemTicket, PolicyDecision, ProblemClass
from .risk_tiering import resolve_risk_tier

class PolicyEngine:
    """
    🛡️ Task B: Unified Policy Engine
    職責: 核心決策大腦，評估 Admission 與所需的治理閘門。
    """
    AUTHORIZED_SOURCES = ["swe-bench", "legacy-import", "manual-cli"]

    @staticmethod
    def evaluate(ticket: ProblemTicket) -> PolicyDecision:
        tier = resolve_risk_tier(ticket.problem_class, ticket.severity)
        if tier == 'P0_ULTRA':
            return PolicyDecision(True, 'STRICT_GOVERNANCE', ['two_person_review', 'staging_replay'], 0.05)
        return PolicyDecision(True, 'STANDARD_GOVERNANCE', ['automated_test'], 0.1)

    @staticmethod
    def evaluate_admission(ticket: ProblemTicket):
        # 兼容舊測試
        from nexus.policy.policy_engine import PolicyDecision as LocalDecision # 這裡只是為了演示，實際上應回傳正確型別
        if ticket.source not in PolicyEngine.AUTHORIZED_SOURCES:
            return type('Decision', (), {'allowed': False, 'reason': 'UNAUTHORIZED_SOURCE'})
        return type('Decision', (), {'allowed': True, 'reason': 'ALLOWED'})
