import sys
import time

# [NEXUS v26] Anonymized Router Inference Test
# Focus: Zero-leakage classification logic.

def verify_anonymized():
    print("--- [NEXUS VERIFY] Anonymized Router Inference ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    adapter_path = "training/adapters_1_5b" # 已被匿名適配器覆蓋
    
    try:
        from mlx_lm import load, generate
        model, tokenizer = load(model_path, adapter_path=adapter_path)
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    sys_p = "NEXUS_ROUTER_V3: CLASSIFY INPUT TO CATEGORICAL TAGS."
    
    # 測試集
    tests = [
        {"input": "CMD_0", "expected": "R:0,D:0,C:0", "desc": "Success Transition"},
        {"input": "CMD_2", "expected": "R:0,D:2,C:1", "desc": "Illegal Attack"},
        {"input": "CMD_1", "expected": "R:1,D:1,C:0", "desc": "Escalation Repair"},
        {"input": "SIG_EMERGENCY", "expected": "R:0,D:3,C:2", "desc": "Emergency Stop"}
    ]

    for t in tests:
        prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{t['input']}<|im_end|>\n<|im_start|>assistant\n"
        print(f"[{t['desc']}] Input: {t['input']}...", end=" ", flush=True)
        
        t0 = time.time()
        response = generate(model, tokenizer, prompt=prompt, max_tokens=16, verbose=False)
        duration = time.time() - t0
        
        res = response.strip()
        status = "✅ PASS" if res == t["expected"] else f"❌ FAIL (Got: {res})"
        print(f"{status} ({duration:.2f}s)")

if __name__ == "__main__":
    verify_anonymized()
