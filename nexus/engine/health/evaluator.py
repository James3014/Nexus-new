from nexus.core.state_contracts import NexusState

class HealthEvaluator:
    def evaluate(self, state: NexusState, success: bool) -> float:
        m = state.health_metrics
        
        # 1. Test Pass Rate
        m.test_pass_rate = 1.0 if success else 0.0

        # 2. Error Rate (based on repair_attempts)
        attempts = state.metadata.get("repair_attempts", 0)
        m.error_rate = min(1.0, attempts / 5.0)

        budget = state.config.budget_token if hasattr(state.config, "budget_token") else 5000
        # Increased penalty: scale by 1.5x budget threshold
        m.token_efficiency = max(0.0, 1.0 - (state.total_token_usage / (budget * 1.5)))

        # 4. Drift Index
        m.drift_index = 0.0

        score = state.calculate_health()
        return score
