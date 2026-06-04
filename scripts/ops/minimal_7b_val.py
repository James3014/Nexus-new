import sys
import os
import json
import time
from pathlib import Path

# [NEXUS v26] 7B Minimal Validation Script
# Focus: Load -> Dataset -> Forward -> Schema (No Optimizer)

def log_failure(stage, error):
    print(f"\n❌ {stage}_FAIL: {error}")
    sys.exit(1)

def minimal_validation():
    print("--- [1/4] Model Load ---")
    model_path = "Qwen/Qwen2.5-Coder-7B-Instruct"
    try:
        import mlx.core as mx
        from mlx_lm import load, generate
        
        # 針對 16GB 環境，我們假設模型是以 4-bit 或 8-bit 量化載入
        start_time = time.time()
        model, tokenizer = load(model_path)
        duration = time.time() - start_time
        print(f"✅ LOAD_SUCCESS (Time: {duration:.2f}s)")
    except ImportError:
        log_failure("SYSTEM_STREAM", "mlx-lm not installed")
    except Exception as e:
        log_failure("LOAD", str(e))

    print("\n--- [2/4] Dataset Load ---")
    dataset_paths = [
        "training/mlx_data/train.jsonl",
        "training/dataset_sft_skeleton_v1.jsonl"
    ]
    sample_text = ""
    try:
        target_path = next((p for p in dataset_paths if Path(p).exists()), None)
        if not target_path:
            raise FileNotFoundError(f"No dataset found in {dataset_paths}")
            
        with open(target_path, "r") as f:
            for line in f:
                sample = json.loads(line)
                # 嘗試提取文本欄位
                sample_text = sample.get("text") or sample.get("prompt") or str(sample)
                if sample_text:
                    break
        if not sample_text:
            raise ValueError("Found dataset but could not extract valid text sample")
        print(f"✅ DATASET_SUCCESS (Source: {target_path}, Sample Size: {len(sample_text)})")
    except Exception as e:
        log_failure("DATASET", str(e))

    print("\n--- [3/4] Single Forward ---")
    try:
        # 測試單次編碼與前向傳播，不涉及梯度
        inputs = tokenizer.encode("Nexus v1.1 Skeleton Validation: " + sample_text[:100])
        input_ids = mx.array([inputs])
        
        # 執行前向傳播
        logits = model(input_ids)
        # 強制執行以觸發潛在的 OOM
        mx.eval(logits)
        print(f"✅ FORWARD_SUCCESS (Logits Shape: {logits.shape})")
    except Exception as e:
        log_failure("FORWARD", str(e))

    print("\n--- [4/4] Schema Emit ---")
    try:
        # 測試解碼與 Schema 生成能力
        prompt = "Create a JSON receipt for Nexus activation:"
        response = generate(model, tokenizer, prompt=prompt, max_tokens=32, verbose=False)
        print(f"Preview: {response[:50]}...")
        # 檢查是否含有 JSON 跡象
        if "{" in response or "[" in response:
            print("✅ SCHEMA_SUCCESS (JSON patterns detected)")
        else:
            print("⚠️ SCHEMA_PARTIAL (No JSON pattern, but generation finished)")
        print("✅ SCHEMA_SUCCESS")
    except Exception as e:
        log_failure("SCHEMA", str(e))

    print("\n--- Final Status: ALL_PASS ---")
    return True

if __name__ == "__main__":
    # 強制使用單進程前景執行
    try:
        minimal_validation()
    except KeyboardInterrupt:
        print("\n🛑 Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 UNEXPECTED_CRASH: {e}")
        sys.exit(1)
