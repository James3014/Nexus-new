import sys
import time
import json
from pathlib import Path

# [NEXUS v26] Rigorous 4-Tier Evaluation for 1.5B + LoRA
# Tiers: Canonical, Paraphrase, Conflict, Multi-step

def run_eval():
    print("--- [NEXUS RIGOROUS EVAL] Starting 4-Tier Assessment ---")
    model_path = "Qwen/Qwen2.5-1.5B-Instruct"
    adapter_path = "training/adapters_1_5b"
    eval_file = "training/nexus_eval_v1.jsonl"
    
    try:
        from mlx_lm import load, generate
        model, tokenizer = load(model_path, adapter_path=adapter_path)
    except Exception as e:
        print(f"❌ LOAD_FAIL: {e}")
        sys.exit(1)

    results = {"canonical": [], "paraphrase": [], "conflict": [], "multi_step": []}
    
    with open(eval_file, "r") as f:
        for line in f:
            test = json.loads(line)
            t_id = test["id"]
            t_type = test["type"]
            prompt = f"<|im_start|>system\nYou are Nexus Decision Head. Output minimal decision JSON.<|im_end|>\n<|im_start|>user\n{test['input']}<|im_end|>\n<|im_start|>assistant\n"
            
            print(f"[{t_type.upper()}] Running {t_id}...", end=" ", flush=True)
            t0 = time.time()
            response = generate(model, tokenizer, prompt=prompt, max_tokens=128, verbose=False)
            duration = time.time() - t0
            
            print(f"Raw: {response.strip()}") # 增加打印
            
            # 決策頭驗證邏輯
            passed = True
            try:
                # 預期輸出現在是純 JSON
                clean_response = response.strip()
                if "```json" in clean_response:
                    clean_response = clean_response.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_response:
                    clean_response = clean_response.split("```")[1].strip()
                
                data = json.loads(clean_response)
                
                if t_type == "canonical" or t_type == "paraphrase":
                    if data.get("next") != test.get("expected_phase") and test.get("expected_phase") != "any":
                        passed = False
                elif t_type == "conflict":
                    if data.get("decision") != "reject":
                        passed = False
                elif t_type == "multi_step":
                    if data.get("intent") not in ["repair", "transition"]:
                        passed = False
            except Exception:
                passed = False
            
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} ({duration:.2f}s)")
            results[t_type].append(passed)

    print("\n--- [EVAL SUMMARY] ---")
    for t_type, res in results.items():
        score = sum(res) / len(res) * 100 if res else 0
        print(f"{t_type.capitalize()}: {score:.1f}% ({sum(res)}/{len(res)})")

if __name__ == "__main__":
    run_eval()
