import sys
import time
import json

# [NEXUS v26] Rigorous Router Evaluation v3.0 (Minified Strict Enums)
# Tiers: Canonical, ZH-TW, Conflict, Complex

def run_router_eval_v3():
    print("--- [NEXUS ROUTER EVAL v3] Starting Minified Assessment ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    adapter_path = "training/adapters_1_5b"
    
    try:
        from mlx_lm import load, generate
        model, tokenizer = load(model_path, adapter_path=adapter_path)
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    # 測試樣本：使用最小語義輸入
    tests = [
        {"id": "can_01", "type": "canonical", "input": "EV:D_OK", "exp": {"r": "LOCAL", "p": "R"}},
        {"id": "can_02", "type": "stop", "input": "SIG:HALLUCINATION", "exp": {"d": "STOP"}},
        {"id": "par_01", "type": "zh_tw", "input": "ZH:DONE:D", "exp": {"r": "LOCAL", "p": "R"}},
        {"id": "con_01", "type": "conflict", "input": "SKIP_TO:C", "exp": {"d": "REJECT"}},
        {"id": "mul_01", "type": "complex", "input": "COMPLEX_REPAIR_SYNC", "exp": {"r": "LARGE"}}
    ]

    results = []
    sys_p = "Nexus Router: Input -> Strict Enum JSON."

    for test in tests:
        prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{test['input']}<|im_end|>\n<|im_start|>assistant\n"
        print(f"[{test['type'].upper()}] {test['id']}...", end=" ", flush=True)
        
        t0 = time.time()
        response = generate(model, tokenizer, prompt=prompt, max_tokens=64, verbose=False)
        duration = time.time() - t0
        
        raw_res = response.strip()
        print(f"Raw: {raw_res}", end=" ")
        
        passed = True
        try:
            # 容錯解析 JSON
            clean = raw_res.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            
            for k, v in test["exp"].items():
                if data.get(k) != v:
                    passed = False
                    print(f"(Err: {k} expected {v}, got {data.get(k)})", end=" ")
        except Exception:
            passed = False
            print(f"(Parse Fail)", end=" ")

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} ({duration:.2f}s)")
        results.append(passed)

    score = sum(results) / len(results) * 100
    print(f"\n--- [FINAL ROUTER v3 SCORE: {score:.1f}%] ---")

if __name__ == "__main__":
    run_router_eval_v3()
