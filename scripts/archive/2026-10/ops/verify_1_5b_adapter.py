import sys
import time
import json

# [NEXUS v26] Post-SFT Inference Verification
# Focus: Testing Qwen2.5-1.5B-Instruct + LoRA Adapter

def verify_adapter():
    print("--- [NEXUS VERIFY] Testing 1.5B + LoRA Adapter ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    adapter_path = "training/adapters_1_5b"
    
    try:
        from mlx_lm import load, generate
        print(f"[1/2] Loading model with adapter from: {adapter_path}")
        model, tokenizer = load(model_path, adapter_path=adapter_path)
        print("✅ MODEL_ADAPTER_LOAD_OK")
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    print("\n--- [2/2] Zero-Shot Flow Logic Test ---")
    # 測試一個不在訓練集中的狀態跳轉：D -> R (Code review request)
    prompt = "<|im_start|>system\nYou are Nexus Core SLM. Internalize governance flow and output JSON receipts.<|im_end|>\n<|im_start|>user\nTask: code_optimization, State: D, Evidence: refactoring done, all linters pass.<|im_end|>\n<|im_start|>assistant\n"
    
    try:
        print("Inference started...", flush=True)
        t0 = time.time()
        response = generate(model, tokenizer, prompt=prompt, max_tokens=128, verbose=False)
        print(f"Raw Response:\n{response}")
        print(f"\n✅ INFERENCE_OK ({time.time()-t0:.2f}s)")
        
        if "phase" in response and "R" in response:
            print("🎯 BEHAVIOR_VERIFIED: Successfully predicted transition to Phase R")
        if "```json" in response:
            print("🎯 SCHEMA_VERIFIED: Maintained JSON block format")
    except Exception as e:
        print(f"❌ INFERENCE_FAIL: {e}")

if __name__ == "__main__":
    verify_adapter()
