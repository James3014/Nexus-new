import sys
import time
import json
import os

# [NEXUS v26] 7B Forward-Only Stress Test (Minimal)
# No Optimizer, No training loop, Gradient testing of input length.

def diag_forward():
    print("--- [NEXUS DIAGNOSTIC] Initiating Forward-Only Probe ---")
    model_path = "Qwen/Qwen2.5-Coder-7B-Instruct"
    
    try:
        import mlx.core as mx
        from mlx_lm import load
        print(f"[1/3] Loading model: {model_path}")
        start = time.time()
        model, tokenizer = load(model_path)
        print(f"✅ MODEL_LOAD_OK ({time.time()-start:.2f}s)")
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    # 測試不同長度的輸入，找出記憶體/算子臨界點
    test_lengths = [1, 10, 50, 200, 512]
    
    print("\n--- [2/3] Forward Gradient Test ---")
    for length in test_lengths:
        try:
            sample_input = "Nexus " * length
            tokens = tokenizer.encode(sample_input)
            input_ids = mx.array([tokens])
            
            print(f"Testing length: {len(tokens)} tokens...", end=" ", flush=True)
            t0 = time.time()
            
            # Forward pass
            logits = model(input_ids)
            mx.eval(logits) # Force computation
            
            print(f"✅ PASS ({time.time()-t0:.4f}s)")
        except Exception as e:
            print(f"❌ FORWARD_FAIL (Len: {len(tokens)}): {e}")
            print("\n判定: MEMORY_PRESSURE or SYSTEM_STREAM_FAIL")
            return

    print("\n--- [3/3] Diagnostic Conclusion ---")
    print("ALL FORWARD TESTS PASSED. Bottleneck might be in Batching, Optimizer, or LoRA logic.")
    print("STATUS: LOCAL_7B_FORWARD_CAPABLE")

if __name__ == "__main__":
    diag_forward()
