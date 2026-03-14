import json
from core.state_contracts import NexusIssue, TaskConfig
from core.queue_manager import QueueManager
from core.factory_router import FactoryRouter
import time

def run_stress_test():
    qm = QueueManager()
    router = FactoryRouter(".", max_workers=10) # 壓力測試設為 10
    
    print("🎢 [StressTest] Generating 10 mock issues...")
    for i in range(1, 11):
        priority = 0 if i <= 2 else 1 # 前兩個設為 Hotfix
        issue = NexusIssue(
            task_id=f"stress-test-{i:03d}",
            goal=f"Batch processing simulation for task {i}",
            domain="frontend" if i % 2 == 0 else "backend",
            priority=priority,
            config=TaskConfig(budget_token=1000 * i)
        )
        qm.enqueue(issue)
    
    print("🚀 [StressTest] Dispatching issues via FactoryRouter...")
    # 執行 5 輪分發 (每次分發可啟動多個任務直到滿載)
    for _ in range(5):
        router.dispatch_next()
        time.sleep(1)

if __name__ == "__main__":
    run_stress_test()
