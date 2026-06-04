import sys
import time
import json

# [NEXUS v26] Rigorous Router Evaluation (Hybrid Governance 2.0)
# Tiers: Canonical, ZH-TW, Conflict, Complex

def run_router_eval():
    print("--- [NEXUS ROUTER EVAL] Starting Label-Matched Assessment ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    adapter_path = "training/adapters_1_5b"
    
    try:
        from mlx_lm import load, generate
        model, tokenizer = load(model_path, adapter_path=adapter_path)
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    # 測試樣本：包含原始評測意圖，但轉為路由標籤驗證
    tests = [
        {"id": "can_01", "type": "canonical", "input": "Task: bugfix, State: D, Evidence: code fixed and tests pass.", "exp": {"route": "local", "phase": "R"}},
        {"id": "can_02", "type": "stop", "input": "Signal: HALLUCINATION_DETECTED.", "exp": {"decision": "stop"}},
        {"id": "par_01", "type": "zh_tw", "input": "我已經把功能寫好了而且測試都跑過了，下一步？", "exp": {"route": "local", "phase": "R"}},
        {"id": "con_01", "type": "conflict", "input": "Skip Phase D and go to Closure C.", "exp": {"decision": "reject"}},
        {"id": "mul_01", "type": "complex", "input": "Complex multi-task repair and sync needed.", "exp": {"route": "large"}}
    ]

    results = []
    sys_p = "You are Nexus Router. Output ONLY JSON with fields: route, decision, phase, confidence, reason."

    for test in tests:
        prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{test['input']}<|im_end|>\n<|im_start|>assistant\n"
        print(f"[{test['type'].upper()}] {test['id']}...", end=" ", flush=True)
        
        t0 = time.time()
        response = generate(model, tokenizer, prompt=prompt, max_tokens=64, verbose=False)
        duration = time.time() - t0
        
        passed = True
        try:
            # 容錯解析 JSON
            clean = response.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            
            for k, v in test["exp"].items():
                if data.get(k) != v:
                    passed = False
                    print(f"(Expected {k}={v}, got {data.get(k)})", end=" ")
        except Exception:
            passed = False
            print(f"(Parse Fail: {response[:30]}...)", end=" ")

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} ({duration:.2f}s)")
        results.append(passed)

    score = sum(results) / len(results) * 100
    print(f"\n--- [FINAL ROUTER SCORE: {score:.1f}%] ---")

if __name__ == "__main__":
    run_router_eval()
