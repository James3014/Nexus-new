import sys
import time

# [NEXUS v26] 1:1 Aligned Router Evaluation (Audit Fix)
# Focus: Testing EXACTLY what was trained in MLX_DATA_ROUTER_V3_ANONYMIZED

def run_aligned_eval():
    print("--- [NEXUS ALIGNED EVAL] Testing 1:1 Distribution Match ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    adapter_path = "training/adapters_1_5b"
    
    try:
        from mlx_lm import load, generate
        model, tokenizer = load(model_path, adapter_path=adapter_path)
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    # 必須與 train.jsonl 的 CMD_x 和 R:x,D:x 格式完全一致
    tests = [
        {"id": "can_01", "input": "CMD_0", "expected": "R:0,D:0,C:0", "desc": "Success (CMD_0)"},
        {"id": "can_02", "input": "CMD_3", "expected": "R:0,D:0,C:0", "desc": "Strategy (CMD_3)"},
        {"id": "con_01", "input": "CMD_2", "expected": "R:0,D:2,C:1", "desc": "Attack (CMD_2)"},
        {"id": "mul_01", "input": "CMD_1", "expected": "R:1,D:1,C:0", "desc": "Repair (CMD_1)"},
        {"id": "stop_01", "input": "SIG_EMERGENCY", "expected": "R:0,D:3,C:2", "desc": "Stop (SIG)"}
    ]

    sys_p = "NEXUS_ROUTER_V3: CLASSIFY INPUT TO CATEGORICAL TAGS."
    results = []

    for t in tests:
        prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{t['input']}<|im_end|>\n<|im_start|>assistant\n"
        print(f"[{t['desc']}] Testing...", end=" ", flush=True)
        
        t0 = time.time()
        response = generate(model, tokenizer, prompt=prompt, max_tokens=16, verbose=False)
        res = response.strip()
        
        passed = (res == t["expected"])
        status = "✅ PASS" if passed else f"❌ FAIL (Got: {res})"
        print(f"{status} ({time.time()-t0:.2f}s)")
        results.append(passed)

    score = sum(results) / len(results) * 100
    print(f"\n--- [FINAL ALIGNED SCORE: {score:.1f}%] ---")

if __name__ == "__main__":
    run_aligned_eval()
