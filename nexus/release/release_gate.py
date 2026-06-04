
class ReleaseGate:
    def can_promote(self, decision, metrics):
        return metrics.get('error_rate', 1.0) < decision.max_rollout
