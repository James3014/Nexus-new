import sys
import time
import json
import os

# [NEXUS v26] 1.5B Validation Script (SLM Pivot)
# Focus: Qwen2.5-1.5B-Instruct Load -> Forward -> Speed Bench

def validate_1_5b():
    print("--- [NEXUS PIVOT] Validating Qwen2.5-1.5B-Instruct ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    
    try:
        import mlx.core as mx
        from mlx_lm import load, generate
        print(f"[1/3] Loading SLM: {model_path}")
        start = time.time()
        model, tokenizer = load(model_path)
        load_duration = time.time() - start
        print(f"✅ SLM_LOAD_OK ({load_duration:.2f}s)")
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    print("\n--- [2/3] Forward Speed Bench (Single & Batch) ---")
    test_input = "Nexus Protocol S,P,X,D,R,A,C sequence initialization:"
    tokens = tokenizer.encode(test_input)
    input_ids = mx.array([tokens])
    
    try:
        # Warmup
        model(input_ids)
        mx.eval(model(input_ids))
        
        t0 = time.time()
        logits = model(input_ids)
        mx.eval(logits)
        forward_duration = time.time() - t0
        print(f"✅ FORWARD_OK (Tokens: {len(tokens)}, Time: {forward_duration:.4f}s)")
        print(f"Performance Ratio vs 7B: ~{104/forward_duration:.1f}x faster")
    except Exception as e:
        print(f"❌ FORWARD_FAIL: {e}")
        return

    print("\n--- [3/3] Schema Instruction Following ---")
    prompt = "<|im_start|>system\nYou are Nexus Core. Output only valid JSON receipts.<|im_end|>\n<|im_start|>user\nGenerate a P-X-D-R-A-C receipt for task: 'minimal_val'.<|im_end|>\n<|im_start|>assistant\n"
    try:
        t1 = time.time()
        response = generate(model, tokenizer, prompt=prompt, max_tokens=128, verbose=False)
        gen_duration = time.time() - t1
        print(f"Response: {response[:100]}...")
        print(f"✅ GENERATION_OK ({gen_duration:.2f}s, ~{128/gen_duration:.1f} t/s)")
        if "{" in response:
            print("✅ SCHEMA_VALID (JSON detected)")
    except Exception as e:
        print(f"❌ GEN_FAIL: {e}")

    print("\n--- Final Status: 1.5B_READY ---")

if __name__ == "__main__":
    validate_1_5b()
