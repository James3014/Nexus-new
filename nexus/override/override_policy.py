
class OverrideService:
    def request_override(self, user, reason):
        return {'status': 'AUDIT_LOGGED', 'id': 'ovr_123'}
