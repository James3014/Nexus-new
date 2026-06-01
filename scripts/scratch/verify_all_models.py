
import sys
from pathlib import Path
import json
import urllib.request
import os

# 確保能 import nexus 模組
sys.path.append(str(Path.cwd()))

# 複用 pipeline 中的邏輯，但直接測試所有端點
from benchmarking.swebench_lite.swe_local_heal import nexus_local_generate

MODELS_TO_TEST = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "gemma-4-e4b",
    "qwen3.5-9b"
]

def verify_models():
    print("🧪 [Nexus Model Verify] Starting full pool verification...")
    results = {}
    
    for model in MODELS_TO_TEST:
        print(f"\n🚀 Testing model: {model}")
        try:
            resp = nexus_local_generate(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say 'TEST_PASSED' if you can read this.",
                model=model,
                timeout=30
            )
            print(f"  ✅ SUCCESS: {resp.strip()}")
            results[model] = "PASSED"
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            results[model] = f"FAILED: {str(e)[:50]}"
            
    print("\n--- Final Scorecard ---")
    for model, status in results.items():
        print(f"{model}: {status}")

if __name__ == "__main__":
    verify_models()
