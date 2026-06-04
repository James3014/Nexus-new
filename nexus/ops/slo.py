
class SLOManager:
    def __init__(self):
        self.error_budget = 1.0 # 100% budget
    def update_from_drill(self, success: bool):
        if not success:
            self.error_budget *= 0.5 # 懲罰性減半
        return self.error_budget
    def get_max_rollout(self):
        return 0.1 * self.error_budget
