from typing import List, Dict, Any
from nexus.engine.contracts.execution import ExecutionPhase, ExecutionBudgetProfile, DeferredCheckSpec
import time

class ExecutionBudgetPolicy:
    """
    🛡️ ExecutionBudgetPolicy: 執行預算政策
    管理同步執行與延後執行的邊界，防止黑盒超時。
    """
    def __init__(self, profile_name: str = "core20"):
        self.profile_name = profile_name
        self.profiles = {
            "smoke": ExecutionBudgetProfile("smoke", {ExecutionPhase.VERIFY_HEAVY: 0.0}, 60.0),
            "core20": ExecutionBudgetProfile("core20", {ExecutionPhase.VERIFY_HEAVY: 0.0}, 180.0),
            "full_regression": ExecutionBudgetProfile("full_regression", {ExecutionPhase.VERIFY_HEAVY: 120.0}, 600.0)
        }

    def get_budget(self) -> ExecutionBudgetProfile:
        return self.profiles.get(self.profile_name, self.profiles["core20"])

    def should_defer(self, phase: ExecutionPhase) -> bool:
        budget = self.get_budget()
        return budget.phase_budgets.get(phase, -1.0) == 0.0

class DeferredVerificationQueue:
    """
    🛡️ DeferredVerificationQueue: 延後驗證隊列
    接收被預算政策標記為延後的重型檢查，確保主流程不被阻塞。
    """
    def __init__(self):
        self.queue: List[DeferredCheckSpec] = []

    def enqueue(self, check_id: str, verifier_type: str, payload_hash: str):
        spec = DeferredCheckSpec(
            check_id=check_id,
            verifier_type=verifier_type,
            payload_hash=payload_hash,
            enqueued_at=time.time()
        )
        self.queue.append(spec)

    def get_pending(self) -> List[DeferredCheckSpec]:
        return self.queue
