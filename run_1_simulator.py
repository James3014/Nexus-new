import json
from pathlib import Path
from scripts.ops.soul_palace_engine import SoulPalaceEngine
from scripts.ops.brain_loop_closure import BrainLoopClosure

def run_1():
    root = Path(".").resolve()
    palace = SoulPalaceEngine(root)
    
    # 模擬 Run 1 源事件
    source_event = {
        "task_id": "RUN-1-WEATHER",
        "action": "implement_io",
        "decision": "Use async/await with 5s timeout",
        "reasoning": "Standardizing high-performance I/O across Nexus."
    }
    with open("run_1_source_event.json", "w") as f:
        json.dump(source_event, f, indent=2)
    
    # 提取並存入 Belief 與 Artifact
    palace.store_knowledge("belief", "All external I/O MUST use async mode with mandatory timeout.", layer=1)
    # 建立 Belief ID 固定為 B-RULE-001 用於測試
    with open(".nexusknowledge/beliefs.jsonl", "r") as f:
        lines = f.readlines()
    last_belief = json.loads(lines[-1])
    last_belief["id"] = "B-RULE-001"
    with open(".nexusknowledge/beliefs.jsonl", "w") as f:
        f.write(json.dumps(last_belief) + "\n")
        
    palace.store_knowledge("artifact", "WeatherService implementation pattern (Async/Timeout)", layer=2)
    
    # 建立依賴邊
    with open(".nexusknowledge/dependency_edges.jsonl", "a") as f:
        f.write(json.dumps({"from_id": "B-RULE-001", "to_id": last_belief["id"].replace("B","A"), "type": "supports"}) + "\n")

    # 執行 Ingest & Vectorization
    closure = BrainLoopClosure(root)
    closure.execute_closure()
    print("✅ Run 1: Belief B-RULE-001 crystallized and indexed.")

if __name__ == "__main__":
    run_1()
