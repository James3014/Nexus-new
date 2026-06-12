#!/usr/bin/env python3
"""
🧪 Nexus Phase 4.5: Qwen2.5-3B-Instruct Adapter Integrity & Smoke Test Tool
此腳本用於本地對 fine-tuned LoRA adapter 進行完整性校驗與 JSON Schema 合規性測試。
"""

import os
import sys
import json
import hashlib
import argparse
import re
from pathlib import Path

# 允許的驗證器類型 Enum
ALLOWED_VERIFIERS = ["pytest", "claim_gate", "delivery_gate", "hidden_verifier"]

# 系統 Prompt，引導 3B 學生模型輸出結構化決策
SYSTEM_PROMPT = (
    "You are a Nexus Routing Selector Assistant. Your task is to select the best candidate "
    "and provide selection reason codes and required verifiers based on the route features "
    "and candidate summaries. You must strictly output the target JSON."
)

# 測試用樣本 prompts (S2T JSON 格式)
TEST_PROMPTS = [
    {
        "input": {
            "risk_tier": "medium",
            "route_features": {},
            "candidate_summaries": [
                {"id": "cand-fail-0", "cost": None},
                {"id": "cand-pass-0", "cost": None}
            ],
            "budget": {}
        }
    },
    {
        "input": {
            "risk_tier": "medium",
            "route_features": {},
            "candidate_summaries": [
                {"id": "cand-fail-1", "cost": None},
                {"id": "cand-pass-1", "cost": None}
            ],
            "budget": {}
        }
    },
    {
        "input": {
            "risk_tier": "medium",
            "route_features": {},
            "candidate_summaries": [
                {"id": "cand-fail-2", "cost": None},
                {"id": "cand-pass-2", "cost": None}
            ],
            "budget": {}
        }
    },
    {
        "input": {
            "risk_tier": "medium",
            "route_features": {},
            "candidate_summaries": [
                {"id": "cand-fail-3", "cost": None},
                {"id": "cand-pass-3", "cost": None}
            ],
            "budget": {}
        }
    },
    {
        "input": {
            "risk_tier": "medium",
            "route_features": {},
            "candidate_summaries": [
                {"id": "cand-fail-4", "cost": None},
                {"id": "cand-pass-4", "cost": None}
            ],
            "budget": {}
        }
    }
]

def calculate_sha256(filepath):
    """計算指定檔案的 SHA256 雜湊值"""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_git_commit_hash():
    """取得當前的 Git commit HEAD 雜湊"""
    import subprocess
    try:
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], 
            stderr=subprocess.DEVNULL, 
            text=True
        ).strip()
        return commit_hash
    except Exception:
        return "unknown"

def write_manifest(adapter_dir, manifest_path):
    """計算並寫出適配器的結構化 Manifest JSON 檔案"""
    print(f"📝 Generating Adapter Manifest to {manifest_path}...")
    
    config_path = os.path.join(adapter_dir, "adapter_config.json")
    if not os.path.exists(config_path):
        print(f"❌ Cannot write manifest: adapter_config.json not found in {adapter_dir}")
        return False
        
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    required_files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "README.md"
    ]
    
    files_data = {}
    for fn in required_files:
        fp = os.path.join(adapter_dir, fn)
        if not os.path.exists(fp):
            print(f"❌ Cannot write manifest: required file {fn} is missing.")
            return False
        size = os.path.getsize(fp)
        sha256 = calculate_sha256(fp)
        files_data[fn] = {
            "size": size,
            "sha256": sha256
        }
        
    manifest = {
        "adapter_dir": adapter_dir,
        "base_model_name_or_path": config.get("base_model_name_or_path"),
        "peft_type": config.get("peft_type"),
        "r": config.get("r"),
        "target_modules": config.get("target_modules"),
        "training_data_hash": "sim_dataset_smoke_fixture",
        "commit_hash": get_git_commit_hash(),
        "files": files_data
    }
    
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        
    print(f"🎉 Manifest successfully written to {manifest_path}")
    return True

def verify_manifest(adapter_dir, manifest_path):
    """載入 manifest 並驗證適配器檔案、設定以及 Git 軌跡"""
    print(f"🛡️ Verifying adapter using Manifest: {manifest_path}")
    if not os.path.exists(manifest_path):
        print(f"❌ Manifest file not found: {manifest_path}")
        return False
        
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"❌ Failed to parse manifest JSON: {e}")
        return False
        
    base_model = manifest.get("base_model_name_or_path")
    peft_type = manifest.get("peft_type")
    r = manifest.get("r")
    target_modules = manifest.get("target_modules", [])
    
    if base_model != "Qwen/Qwen2.5-3B-Instruct":
        print(f"❌ Manifest Base Model Mismatch: {base_model}")
        return False
    if peft_type != "LORA":
        print(f"❌ Manifest PEFT Type Mismatch: {peft_type}")
        return False
    if r != 16:
        print(f"❌ Manifest rank r Mismatch: {r}")
        return False
        
    required_projections = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    missing_modules = [m for m in required_projections if m not in target_modules]
    if missing_modules:
        print(f"❌ Manifest Target Modules missing required projections: {missing_modules}")
        return False
        
    files_data = manifest.get("files", {})
    if not files_data:
        print("❌ Manifest contains no files data.")
        return False
        
    for fn, meta in files_data.items():
        fp = os.path.join(adapter_dir, fn)
        if not os.path.exists(fp):
            print(f"❌ File missing from disk: {fn}")
            return False
            
        expected_size = meta.get("size")
        expected_sha256 = meta.get("sha256")
        
        actual_size = os.path.getsize(fp)
        if actual_size != expected_size:
            print(f"❌ File size mismatch for {fn}: Expected {expected_size}, got {actual_size}")
            return False
            
        actual_sha256 = calculate_sha256(fp)
        if actual_sha256 != expected_sha256:
            print(f"❌ File SHA-256 mismatch for {fn}!")
            print(f"  Expected: {expected_sha256}")
            print(f"  Actual:   {actual_sha256}")
            return False
            
        print(f"✅ {fn} checked: size and SHA-256 match.")
        
    current_commit = get_git_commit_hash()
    manifest_commit = manifest.get("commit_hash", "unknown")
    print(f"🔎 Provenance Git Commit Check:")
    print(f"  Current HEAD Commit: {current_commit}")
    print(f"  Manifest Commit:     {manifest_commit}")
    if current_commit != manifest_commit:
        print("⚠️ Warning: Current Git HEAD does not match the commit that generated this manifest.")
    else:
        print("✅ Git provenance commit MATCH.")
        
    print("🎉 Manifest-based Integrity Check PASSED.")
    return True


def validate_json_schema(data):
    """嚴格校驗輸出 JSON 是否符合 S2T 決策 Schema"""
    if not isinstance(data, dict):
        return False, "Output must be a JSON object"
    
    # 1. 驗證 selected_candidate_id (str 或 null)
    if "selected_candidate_id" not in data:
        return False, "Missing 'selected_candidate_id'"
    val = data["selected_candidate_id"]
    if val is not None and not isinstance(val, str):
        return False, f"'selected_candidate_id' must be string or null, got {type(val)}"

    # 2. 驗證 selection_reason_codes (non-empty list of strings)
    if "selection_reason_codes" not in data:
        return False, "Missing 'selection_reason_codes'"
    codes = data["selection_reason_codes"]
    if not isinstance(codes, list):
        return False, "'selection_reason_codes' must be a list"
    if len(codes) == 0:
        return False, "'selection_reason_codes' list cannot be empty"
    for code in codes:
        if not isinstance(code, str):
            return False, f"Reason codes must be strings, got {type(code)}"

    # 3. 驗證 required_verifier (allowed enum)
    if "required_verifier" not in data:
        return False, "Missing 'required_verifier'"
    verifier = data["required_verifier"]
    if verifier is not None:
        if not isinstance(verifier, str):
            return False, f"'required_verifier' must be string or null, got {type(verifier)}"
        if verifier not in ALLOWED_VERIFIERS:
            return False, f"Invalid 'required_verifier': '{verifier}'. Must be one of {ALLOWED_VERIFIERS}"
        if verifier.lower() == "success":
            return False, "Outputting 'success' as verifier decision is strictly forbidden"

    # 4. 驗證 abstain_reason (str 或 null)
    if "abstain_reason" not in data:
        return False, "Missing 'abstain_reason'"
    abstain = data["abstain_reason"]
    if abstain is not None and not isinstance(abstain, str):
        return False, f"'abstain_reason' must be string or null, got {type(abstain)}"

    return True, "Valid"

def run_mock_integrity(adapter_dir, verify_report_path=None):
    """Mock 模式：驗證檔案存在性、設定與雜湊值"""
    print("🛡️ Running Mock Integrity Check...")
    
    required_files = [
        "adapter_config.json",
        "adapter_model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "README.md"
    ]
    
    # 1. 檔案存在性與大小校驗
    missing_files = []
    empty_files = []
    calculated_hashes = {}
    
    for filename in required_files:
        path = os.path.join(adapter_dir, filename)
        if not os.path.exists(path):
            missing_files.append(filename)
        else:
            size = os.path.getsize(path)
            if size == 0:
                empty_files.append(filename)
            calculated_hashes[filename] = calculate_sha256(path)
            
    if missing_files:
        print(f"❌ Missing files in adapter directory: {missing_files}")
        return False
    if empty_files:
        print(f"❌ Empty files found in adapter directory: {empty_files}")
        return False
        
    print("✅ All required adapter files present and non-empty.")
    
    # 2. adapter_config.json 設定校驗
    config_path = os.path.join(adapter_dir, "adapter_config.json")
    with open(config_path, 'r') as f:
        config = json.load(f)
        
    base_model = config.get("base_model_name_or_path")
    peft_type = config.get("peft_type")
    r = config.get("r")
    target_modules = config.get("target_modules", [])
    
    if base_model != "Qwen/Qwen2.5-3B-Instruct":
        print(f"❌ Incorrect base model: {base_model}. Expected Qwen/Qwen2.5-3B-Instruct.")
        return False
    if peft_type != "LORA":
        print(f"❌ Incorrect PEFT type: {peft_type}. Expected LORA.")
        return False
    if r != 16:
        print(f"❌ Incorrect LoRA rank r: {r}. Expected 16.")
        return False
        
    required_projections = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    missing_modules = [m for m in required_projections if m not in target_modules]
    if missing_modules:
        print(f"❌ Missing target modules: {missing_modules}")
        return False
        
    print("✅ adapter_config.json settings match specifications (Qwen2.5-3B, LoRA r=16).")
    
    # 3. 雙向 Checksum 校驗
    if verify_report_path:
        print(f"🔎 Verifying checksums against report: {verify_report_path}")
        if not os.path.exists(verify_report_path):
            print(f"❌ Report file not found: {verify_report_path}")
            return False
            
        with open(verify_report_path, 'r') as r_file:
            report_content = r_file.read()
            
        for fn, expected_hash in calculated_hashes.items():
            # 在報告中尋找該檔案名稱及其對應的 sha256 雜湊
            pattern = re.compile(rf"([a-f0-9]{{64}})\s+.*{fn}")
            match = pattern.search(report_content)
            if not match:
                # 嘗試另一種 Markdown 表格/文字匹配格式
                pattern = re.compile(rf"{fn}.*?`([a-f0-9]{{64}})`")
                match = pattern.search(report_content)
                
            if match:
                report_hash = match.group(1)
                if report_hash != expected_hash:
                    print(f"❌ Hash mismatch for {fn}!")
                    print(f"  Calculated: {expected_hash}")
                    print(f"  In Report:  {report_hash}")
                    return False
                else:
                    print(f"✅ Hash MATCH for {fn}: {expected_hash[:8]}...")
            else:
                print(f"❌ Could not find expected hash for {fn} in the report.")
                return False
                
    return True

def run_physical_smoke(adapter_dir, device, max_tokens, offline, timeout_sec=None):
    """實體加載測試：載入 base model + LoRA 並測試產物格式"""
    print("🚀 Running Physical Load Smoke Test...")
    
    import signal
    if timeout_sec and timeout_sec > 0:
        def handler(signum, frame):
            raise TimeoutError(f"Physical smoke test execution timed out after {timeout_sec} seconds")
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout_sec)
        print(f"⏱️ Timeout set to {timeout_sec} seconds.")

    try:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
        except ImportError:
            print("❌ ML Libraries (torch, transformers, peft) not installed. Cannot run physical smoke.")
            return False

        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
            print(f"ℹ️ Dynamically selected device: '{device}'")

        # 本地只使用快取，不聯網下載
        kwargs = {}
        if offline:
            print("ℹ️ Offline mode active. Only local Hugging Face cache will be used.")
            kwargs["local_files_only"] = True
            
        base_model_id = "Qwen/Qwen2.5-3B-Instruct"
        
        print(f"🤖 Loading tokenizer for {base_model_id}...")
        try:
            tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True, **kwargs)
        except Exception as e:
            print(f"❌ Failed to load tokenizer locally (is model cached?): {e}")
            return False
            
        print(f"💾 Loading base model {base_model_id} on device '{device}'...")
        
        # 依據 device 使用對應精度
        torch_dtype = torch.float16 if device in ["cuda", "mps"] else torch.float32
        
        try:
            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                torch_dtype=torch_dtype,
                device_map=device if device != "mps" else None,
                trust_remote_code=True,
                **kwargs
            )
            if device == "mps":
                base_model = base_model.to("mps")
        except Exception as e:
            print(f"❌ Failed to load base model (is model cached?): {e}")
            return False
            
        print(f"⚡ Loading PEFT adapter from {adapter_dir}...")
        try:
            model = PeftModel.from_pretrained(base_model, adapter_dir, **kwargs)
            model.eval()
        except Exception as e:
            print(f"❌ Failed to merge adapter weights: {e}")
            return False
            
        print("✅ Model loaded successfully. Starting prompt generation smoke...")
        
        parsed_count = 0
        compliant_count = 0
        total_prompts = len(TEST_PROMPTS)
        
        for idx, sample in enumerate(TEST_PROMPTS):
            input_str = f"Route Features: {sample['input']['route_features']}\nCandidates: {sample['input']['candidate_summaries']}"
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": input_str}
            ]
            
            # 使用 Qwen ChatML template 格式化
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            model_inputs = tokenizer([text], return_tensors="pt").to(device)
            
            print(f"\n--- [Prompt {idx+1}/{total_prompts}] ---")
            try:
                with torch.no_grad():
                    generated_ids = model.generate(
                        **model_inputs,
                        max_new_tokens=max_tokens,
                        pad_token_id=tokenizer.eos_token_id
                    )
                # 取得輸出文本
                generated_ids = [
                    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
                ]
                response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
                print(f"Raw Output:\n{response}")
                
                # 1. 嘗試 parse JSON
                try:
                    # 剔除可能存在的 markdown tags
                    clean_response = response.strip()
                    if clean_response.startswith("```json"):
                        clean_response = clean_response.split("```json")[1].split("```")[0].strip()
                    elif clean_response.startswith("```"):
                        clean_response = clean_response.split("```")[1].split("```")[0].strip()
                        
                    parsed_json = json.loads(clean_response)
                    parsed_count += 1
                    
                    # 2. 驗證 schema 合規性
                    is_valid, reason = validate_json_schema(parsed_json)
                    if is_valid:
                        compliant_count += 1
                        print("✅ Schema Verdict: COMPLIANT")
                    else:
                        print(f"❌ Schema Verdict: NON-COMPLIANT (Reason: {reason})")
                except json.JSONDecodeError as je:
                    print(f"❌ Failed to parse output as JSON: {je}")
            except Exception as ge:
                print(f"❌ Generation error: {ge}")
                
        print("\n=========================================")
        print(f"📊 Smoke Test Summary (Physical Mode)")
        print(f"JSON Parse Rate:       {parsed_count}/{total_prompts} ({parsed_count/total_prompts * 100:.1f}%)")
        print(f"Schema Compliance:     {compliant_count}/{total_prompts} ({compliant_count/total_prompts * 100:.1f}%)")
        print("=========================================")
        
        if compliant_count == total_prompts:
            return True
        else:
            print("⚠️ Warning: Not all generations were schema-compliant.")
            return False
    except TimeoutError as te:
        print(f"❌ {te}")
        return False
    finally:
        if timeout_sec and timeout_sec > 0:
            signal.alarm(0)

def main():
    parser = argparse.ArgumentParser(description="Nexus 3B Student Adapter Integrity and Smoke Test Runner")
    parser.add_argument("--adapter_dir", type=str, default="training/adapters/qwen3b_s2t_adapter")
    parser.add_argument("--run-real", action="store_true", help="Run physical loading and token generation.")
    parser.add_argument("--device", type=str, default="auto", choices=["auto", "cpu", "cuda", "mps"], help="Device to use for real run.")
    parser.add_argument("--max-new-tokens", type=int, default=128, help="Max output tokens for generation.")
    parser.add_argument("--offline", action="store_true", help="Only use local caches, do not hit HF network.")
    parser.add_argument("--timeout-sec", type=int, default=None, help="Strict timeout in seconds for physical smoke test.")
    parser.add_argument("--write-report-checksums", action="store_true", help="Print checksums in markdown format for copying to report.")
    parser.add_argument("--verify-report", type=str, default="docs/reports/QWEN3B_S2T_ADAPTER_INTEGRITY_AND_SMOKE_2026-06-12.md", help="Path to report markdown to verify adapter hash against.")
    parser.add_argument("--write-manifest", type=str, default=None, help="Write structural adapter manifest to path.")
    parser.add_argument("--verify-manifest", type=str, default=None, help="Path to structural adapter manifest to verify against.")
    args = parser.parse_args()
    
    adapter_path = args.adapter_dir
    
    # 1. 輸出 Checksums
    if args.write_report_checksums:
        print("📝 SHA256 Checksums for Report:")
        for fn in os.listdir(adapter_path):
            fp = os.path.join(adapter_path, fn)
            if os.path.isfile(fp):
                h = calculate_sha256(fp)
                print(f"| `{fn}` | `{h}` |")
        return

    # 2. 產出 Manifest 模式
    if args.write_manifest:
        success = write_manifest(adapter_path, args.write_manifest)
        if not success:
            sys.exit(1)
        return

    # 3. 驗證 Manifest 模式
    if args.verify_manifest:
        manifest_success = verify_manifest(adapter_path, args.verify_manifest)
        if not manifest_success:
            print("❌ Manifest Verification FAILED.")
            sys.exit(1)
    else:
        # 4. 預設 Mock 完整性驗證 (使用 Report)
        mock_success = run_mock_integrity(adapter_path, verify_report_path=args.verify_report)
        if not mock_success:
            print("❌ Mock Integrity Check FAILED.")
            sys.exit(1)
        print("🎉 Mock Integrity Check PASSED.")
    
    # 5. 執行實體加載 (可選)
    if args.run_real:
        physical_success = run_physical_smoke(adapter_path, args.device, args.max_new_tokens, args.offline, timeout_sec=args.timeout_sec)
        if not physical_success:
            print("❌ Physical load smoke test FAILED.")
            sys.exit(1)
        print("🎉 Physical load smoke test PASSED.")
    else:
        print("ℹ️ Physical load smoke test skipped (Use --run-real to execute).")

if __name__ == "__main__":
    main()
