
import sys
from pathlib import Path

# 確保能 import nexus 模組
sys.path.append(str(Path.cwd()))

from nexus.engine.local_model_policy import LocalModelPolicy

def test_routing():
    print("🧪 [Nexus Route Test] Starting multi-model dispatch verification...")
    
    # 測試案例 1: Astropy (代數推理需求)
    astropy_ctx = {
        "reasoning_mode": "ALGEBRAIC",
        "file_count": 5
    }
    res1 = LocalModelPolicy.select_model(task_type="swe_repair", phase="patch", context=astropy_ctx)
    print(f"\nScenario 1: Astropy (Algebraic Fix)")
    print(f"  → Expected: {LocalModelPolicy.OLLAMA_14B}")
    print(f"  → Actual  : {res1['model']}")
    print(f"  → Reason  : {res1['reason_code']}")
    assert res1['model'] == LocalModelPolicy.OLLAMA_14B

    # 測試案例 2: Concurrency (直覺修復需求)
    concurrency_ctx = {
        "reasoning_mode": "INTUITIVE",
        "file_count": 1
    }
    res2 = LocalModelPolicy.select_model(task_type="swe_repair", phase="patch", context=concurrency_ctx)
    print(f"\nScenario 2: Concurrency (Intuitive Patch)")
    print(f"  → Expected: {LocalModelPolicy.LMS_GEMMA}")
    print(f"  → Actual  : {res2['model']}")
    print(f"  → Reason  : {res2['reason_code']}")
    assert res2['model'] == LocalModelPolicy.LMS_GEMMA

    # 測試案例 3: Scaffolding (搜尋階段)
    res3 = LocalModelPolicy.select_model(task_type="swe_repair", phase="planning", context=astropy_ctx)
    print(f"\nScenario 3: Any Task (Scaffolding/Planning)")
    print(f"  → Expected: {LocalModelPolicy.OLLAMA_7B}")
    print(f"  → Actual  : {res3['model']}")
    print(f"  → Reason  : {res3['reason_code']}")
    assert res3['model'] == LocalModelPolicy.OLLAMA_7B

    print("\n✅ [Nexus Route Test] All routing assertions PASSED.")

if __name__ == "__main__":
    test_routing()
