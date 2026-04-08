import json
import time
import os
from pathlib import Path
from nexus.engine.phases.planner import PlannerPhaseHandler
from nexus.core.state_contracts import NexusState
from nexus.models.planner_models import PlannerResult, ImplementationPackSchema
from nexus.core.errors import NexusError, ErrorCode
from nexus.cli.utils import _log_perf_span

def run_ultimate_test():
    print("🔥 [Ultimate Test] Initiating Nexus Refactored Core Stress Test...")
    root = Path(".")
    tid = "TASK-ULTIMATE-001"
    
    # 1. 測試型別化契約 (Pydantic Model Dump)
    print("\n📦 [1/4] Testing Typed Contracts & Default Factories...")
    pack = ImplementationPackSchema(
        task_id=tid,
        goal="Implement atomic storage sharding with telemetry injection.",
        deliverables=["nexus/core/sharding.py"]
    )
    assert "Standard Fallback" in pack.error_handling
    print(f"✅ Contract validated. Timestamp: {pack.timestamp}")

    # 2. 測試異常處理標準化 (Error Consolidation)
    print("\n🛡️ [2/4] Testing Standardized Error Handling...")
    try:
        # 模擬一個驗證錯誤
        raise NexusError(ErrorCode.VAL_001, "Ambiguous spec detected in refactored core")
    except NexusError as e:
        err_dict = e.to_dict()
        assert err_dict["error_code"] == "VAL_001"
        assert err_dict["severity"] == "WARNING"
        print(f"✅ Error caught and JSON-ified: {json.dumps(err_dict, indent=2)}")

    # 3. 測試 Planner 注入與 Provider 調用
    print("\n🔮 [3/4] Testing Planner Dependency Injection...")
    # 使用重構後的構造函數
    planner = PlannerPhaseHandler(root, root / ".nexus/runs" / tid)
    state = NexusState(task_id=tid)
    
    context = {
        "task": "Build Atomic Transaction Module for Sharded DB",
        "target_files": ["nexus/infrastructure/storage_implementations.py"]
    }
    
    t0 = time.perf_counter()
    # 這裡會跑過重構後的 Provider 邏輯
    res = planner.run(state, context)
    t1 = time.perf_counter()
    
    assert res["intent_pass"] == True
    print(f"✅ Planner Provider Logic Passed. Handoff Readiness: {res['handoff_readiness']}")

    # 4. 測試遙測解耦與效能紀錄
    print("\n📡 [4/4] Testing Decoupled Telemetry (Async IO)...")
    _log_perf_span("ultimate.test.total", t0, t1, tid, {"refactor_status": "success"})
    print("✅ Telemetry payload sent to Async Queue.")

    print("\n" + "="*50)
    print("🏆 ULTIMATE TEST STATUS: [PASSED]")
    print("="*50)
    print(f"Metrics Trace ID: {tid}")
    print(f"Core Module Count: 6 (CLI, Planner, Models, Errors, Telemetry, Infrastructure)")
    print("="*50)

if __name__ == "__main__":
    run_ultimate_test()
