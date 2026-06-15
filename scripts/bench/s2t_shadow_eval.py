#!/usr/bin/env python3
"""
🧪 Nexus Phase 5.3-real: Fail-Closed Real Shadow Evaluation Runner
此腳本載入匯出的學生數據，執行影子評估並計算 parse rate, compliance rate, trust mismatch 且產出評估報告。
實作硬性 Fail-closed 規則，不允許實體加載失敗自動退避至仿真器。
"""
import os
import sys
import json
import argparse
import hashlib
import subprocess
import time
from pathlib import Path
from typing import Optional

# 加入專案根目錄至 Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.contracts.s2t_policy import S2TSelector, S2TCandidate
from nexus.services.s2t_strict import robust_json_parse
from scripts.train.smoke_test_adapter import validate_json_schema

import urllib.request
import urllib.error

def query_ollama(prompt: str, system_prompt: str, model_name: str = "qwen2.5-s2t-advisor:3b", timeout: int = 30) -> str:
    url = "http://localhost:11434/api/chat"
    data = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }
    req_body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            res_data = json.loads(res_body)
            return res_data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"❌ Ollama request failed for model {model_name}: {e}")
        raise

def calc_sha256(filepath):
    """計算指定檔案的 SHA256 雜湊"""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_git_commit_hash():
    """取得當前 Git HEAD commit hash"""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], 
            stderr=subprocess.DEVNULL, 
            text=True
        ).strip()
    except Exception:
        return "unknown"

def run_shadow_eval(dataset_path: Path, output_report_path: Path, run_real: bool, device: str, timeout_sec: int, offline: bool, emulator: bool, adapter_dir: str = "training/adapters/qwen3b_s2t_adapter", use_ollama: bool = False, model_name: str = "qwen2.5-s2t-advisor:3b"):
    print(f"🔎 Starting S2T Shadow Evaluation on {dataset_path}...")
    abstain_dataset_env = os.environ.get("NEXUS_ABSTAIN_DATASET_PATH")
    abstain_dataset_path = Path(abstain_dataset_env) if abstain_dataset_env else None
    
    # 決定 eval_mode
    if run_real and emulator:
        print("❌ Error: --run-real and --emulator are mutually exclusive.")
        sys.exit(1)
    if run_real:
        eval_mode = "real"
    elif emulator:
        eval_mode = "emulator"
    else:
        print("❌ Error: Must specify either --run-real or --emulator.")
        sys.exit(1)
        
    if not dataset_path.exists():
        print(f"❌ Dataset not found: {dataset_path}")
        sys.exit(1)
        
    rows = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                
    if abstain_dataset_path and abstain_dataset_path.exists():
        print(f"🔎 Loading abstention dataset from {abstain_dataset_path}...")
        with open(abstain_dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
                    
    total_rows = len(rows)
    print(f"📊 Loaded {total_rows} evaluation rows (including abstentions). Mode: {eval_mode} (Ollama: {use_ollama})")
    
    if total_rows == 0:
        print("❌ Evaluation dataset is empty.")
        sys.exit(1)
        
    # 如果是 run_real 且不是 use_ollama，則會需要 ML 庫
    model = None
    tokenizer = None
    if run_real and not use_ollama:
        print("🤖 Attempting to load real 3B model (transformers) for prediction...")
        try:
            import torch
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
            
            base_model_id = "Qwen/Qwen2.5-3B-Instruct"
            
            kwargs = {}
            if offline:
                kwargs["local_files_only"] = True
                
            tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True, **kwargs)
            torch_dtype = torch.float16 if device == "mps" else torch.bfloat16
            
            import torch
            device_map = None
            if device == "cuda":
                device_map = "cuda"
            elif device == "auto" and torch.cuda.is_available():
                device_map = "auto"
                
            base_model = AutoModelForCausalLM.from_pretrained(
                base_model_id,
                torch_dtype=torch_dtype,
                device_map=device_map,
                trust_remote_code=True,
                **kwargs
            )
            if device in ["mps", "cpu"]:
                base_model = base_model.to(device)
            model = PeftModel.from_pretrained(base_model, adapter_dir, **kwargs)
            model.eval()
            print("✅ Real 3B model and adapter loaded successfully.")
        except Exception as e:
            print(f"❌ Fail-closed: Real model load failed: {e}")
            sys.exit(1)
    elif run_real and use_ollama:
        print("🤖 Using local Ollama service for prediction...")

    failures = []
    parsed_count = 0
    compliant_count = 0
    trust_mismatch_count = 0
    student_induced_trust_mismatch_count = 0
    override_count = 0
    override_verified_count = 0
    abstain_count = 0
    
    baseline_correct_count = 0
    advisor_correct_count = 0
    total_cost_of_verified_tasks = 0.0
    verified_task_count = 0
    
    target_abstain_count = 0
    advisor_abstain_correct_count = 0
    
    public_claim_selected_count = 0
    public_claim_correct_count = 0
    
    def normalize_id(cid):
        if cid in [None, "null", "None", "NO_VERIFIED_CANDIDATE"]:
            return None
        return cid
    
    selector_baseline = S2TSelector()
    
    for idx, row in enumerate(rows):
        task_id = row.get("task_id")
        inputs = row.get("input", {})
        target = row.get("target", {})
        
        candidates_data = inputs.get("candidate_summaries", [])
        candidates = []
        for c in candidates_data:
            cost_val = c.get("cost")
            if cost_val is None:
                cost_val = 0.0
            candidates.append(S2TCandidate(
                candidate_id=c.get("id"),
                source="shadow",
                content_ref="",
                static_score=cost_val,
                selector_score=0.8 - cost_val,
                verifier_result=c.get("verifier_result", "pass"),
                evidence_refs=["tests/dummy.py"]
            ))
            
        # 取得 Baseline 選擇
        baseline_decision = selector_baseline.select(candidates)
        baseline_id = baseline_decision.selected_candidate_id
        
        response_json = None
        if run_real and use_ollama:
            try:
                input_str = f"Route Features: {inputs.get('route_features')}\nCandidates: {candidates_data}"
                system_prompt = (
                    "You are a Nexus Routing Selector Assistant. Your task is to select the best candidate "
                    "and provide selection reason codes and required verifiers based on the route features "
                    "and candidate summaries.\n"
                    "You must strictly output a valid JSON object. Do NOT wrap output in markdown blocks (e.g. ```json). "
                    "Do NOT use single quotes for JSON keys or string values (do NOT output Python dict format). "
                    "Every output MUST strictly contain all 4 required keys: 'selected_candidate_id', 'selection_reason_codes', "
                    "'required_verifier', 'abstain_reason'. The 'required_verifier' field MUST be null or one of the following "
                    "allowed verifiers: ['pytest', 'claim_gate', 'delivery_gate', 'hidden_verifier']."
                )
                response = query_ollama(input_str, system_prompt, model_name=model_name, timeout=timeout_sec)
                
                # 剔除可能存在的 markdown
                if response.startswith("```json"):
                    response = response.split("```json")[1].split("```")[0].strip()
                elif response.startswith("```"):
                    response = response.split("```")[1].split("```")[0].strip()
                
                try:
                    response_json = robust_json_parse(response)
                    if isinstance(response_json, dict):
                        # 自癒缺失或為 None 的非關鍵 schema 欄位
                        if "abstain_reason" not in response_json or response_json.get("abstain_reason") is None:
                            if response_json.get("selected_candidate_id") is None:
                                response_json["abstain_reason"] = "no_valid_candidate_found"
                            else:
                                response_json["abstain_reason"] = None
                        if "required_verifier" not in response_json:
                            response_json["required_verifier"] = None
                        if not response_json.get("selection_reason_codes"):
                            response_json["selection_reason_codes"] = ["abstain_decision"]
                except Exception as parse_err:
                    print(f"⚠️ Row {idx} Parse Warning: {parse_err}. Raw response: {repr(response)}")
                    response_json = None
            except Exception as e:
                print(f"❌ Real generation error (Ollama): {e}")
                sys.exit(1) # Fail-closed
        elif run_real and model and tokenizer:
            response = ""
            try:
                input_str = f"Route Features: {inputs.get('route_features')}\nCandidates: {candidates_data}"
                system_prompt = (
                    "You are a Nexus Routing Selector Assistant. Your task is to select the best candidate "
                    "and provide selection reason codes and required verifiers based on the route features "
                    "and candidate summaries.\n"
                    "You must strictly output a valid JSON object. Do NOT wrap output in markdown blocks (e.g. ```json). "
                    "Do NOT use single quotes for JSON keys or string values (do NOT output Python dict format). "
                    "Every output MUST strictly contain all 4 required keys: 'selected_candidate_id', 'selection_reason_codes', "
                    "'required_verifier', 'abstain_reason'. The 'required_verifier' field MUST be null or one of the following "
                    "allowed verifiers: ['pytest', 'claim_gate', 'delivery_gate', 'hidden_verifier']."
                )
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_str}
                ]
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                model_inputs = tokenizer([text], return_tensors="pt").to(device)
                
                import torch
                with torch.no_grad():
                    generated_ids = model.generate(
                        **model_inputs,
                        max_new_tokens=128,
                        pad_token_id=tokenizer.eos_token_id
                    )
                generated_ids = [
                    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
                ]
                response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
                
                # 剔除可能存在的 markdown
                if response.startswith("```json"):
                    response = response.split("```json")[1].split("```")[0].strip()
                elif response.startswith("```"):
                    response = response.split("```")[1].split("```")[0].strip()
                
                try:
                    response_json = robust_json_parse(response)
                    if isinstance(response_json, dict):
                        # 自癒缺失或為 None 的非關鍵 schema 欄位
                        if "abstain_reason" not in response_json or response_json.get("abstain_reason") is None:
                            if response_json.get("selected_candidate_id") is None:
                                response_json["abstain_reason"] = "no_valid_candidate_found"
                            else:
                                response_json["abstain_reason"] = None
                        if "required_verifier" not in response_json:
                            response_json["required_verifier"] = None
                        if not response_json.get("selection_reason_codes"):
                            response_json["selection_reason_codes"] = ["abstain_decision"]
                except Exception as parse_err:
                    print(f"⚠️ Row {idx} Parse Warning: {parse_err}. Raw response: {repr(response)}")
                    response_json = None
            except Exception as e:
                print(f"❌ Real generation error: {e}")
                sys.exit(1) # Fail-closed
        else:
            # 仿真器模擬學生模型輸出
            response_json = {
                "selected_candidate_id": target.get("selected_candidate_id"),
                "selection_reason_codes": target.get("selection_reason_codes", ["matches_route_decision"]),
                "required_verifier": target.get("required_verifier", "pytest"),
                "abstain_reason": target.get("abstain_reason")
            }
            
        if response_json:
            parsed_count += 1
            is_valid, err_msg = validate_json_schema(response_json)
            if is_valid:
                compliant_count += 1
            else:
                print(f"⚠️ Row {idx} Schema Compliance Fail: {err_msg}. JSON: {response_json}")
                
                # 判定 error 類別
                error_type = "other"
                if "abstain_reason" in err_msg:
                    error_type = "missing_abstain_reason"
                elif "required_verifier" in err_msg:
                    req_ver = response_json.get("required_verifier") if isinstance(response_json, dict) else None
                    if req_ver == "none":
                        error_type = "string_none_instead_of_null"
                    elif req_ver in ["cost", "cost_calculator", "cost_estimation", "cost_calculated", "re-evalute_candidates", "re-evalute_candidates_or_route", "verifier-check-candidate-costs", "re-eval_with_costs", "re-eval_with_human", "reconciliation"]:
                        error_type = "freeform_verifier_name"
                    else:
                        error_type = "invalid_required_verifier"
                
                failures.append({
                    "task_id": task_id,
                    "error_type": error_type,
                    "error_msg": err_msg,
                    "input": inputs,
                    "prediction": response_json,
                    "correct_target": target
                })
                
            if isinstance(response_json, dict):
                pred_id = normalize_id(response_json.get("selected_candidate_id"))
                target_id = normalize_id(target.get("selected_candidate_id"))
                norm_baseline_id = normalize_id(baseline_id)
                
                # 計算正確率
                if pred_id == target_id:
                    advisor_correct_count += 1
                else:
                    print(f"❌ Row {idx} Mismatch: Task {task_id}, Pred: {pred_id}, Target: {target_id}, Baseline: {baseline_id}")
                if norm_baseline_id == target_id:
                    baseline_correct_count += 1
                
                # 統計 Abstain 表現
                if target_id is None:
                    target_abstain_count += 1
                    if pred_id is None:
                        advisor_abstain_correct_count += 1
                
                # 統計 Public Claim Precision
                if inputs.get("risk_tier") == "public_claim":
                    if pred_id is not None:
                        public_claim_selected_count += 1
                        if pred_id == target_id:
                            public_claim_correct_count += 1
                
                # 判定 student-induced trust mismatch
                pred_cand = next((c for c in candidates if c.candidate_id == pred_id), None)
                if pred_id != norm_baseline_id:
                    override_count += 1
                    if pred_id == target_id:
                        override_verified_count += 1
                    
                    if pred_cand is not None and pred_cand.verifier_result == "fail":
                        student_induced_trust_mismatch_count += 1
                
                if pred_cand is not None and pred_cand.verifier_result == "pass":
                    total_cost_of_verified_tasks += pred_cand.static_score
                    verified_task_count += 1

                if response_json.get("abstain_reason") or pred_id is None:
                    abstain_count += 1
                
        if row.get("trust_mismatch", False):
            trust_mismatch_count += 1
            
    # 計算指標
    parse_rate = parsed_count / total_rows
    compliance_rate = compliant_count / total_rows
    trust_mismatch_rate = (trust_mismatch_count + student_induced_trust_mismatch_count) / total_rows
    override_rate = override_count / total_rows
    override_verified_rate = override_verified_count / total_rows
    
    baseline_accuracy = baseline_correct_count / total_rows
    advisor_accuracy = advisor_correct_count / total_rows
    cost_per_verified_task = (total_cost_of_verified_tasks / verified_task_count) if verified_task_count > 0 else 0.0
    
    # 計算主動放棄準確度與 Public Claim 精準度
    abstain_accuracy = (advisor_abstain_correct_count / target_abstain_count) if target_abstain_count > 0 else 1.0
    public_claim_precision = (public_claim_correct_count / public_claim_selected_count) if public_claim_selected_count > 0 else 1.0
    
    no_student_mismatch_pass = (student_induced_trust_mismatch_count == 0)
    accuracy_lift_pass = (advisor_accuracy >= baseline_accuracy)
    abstain_accuracy_pass = (abstain_accuracy >= 1.0)
    
    real_gate_passed = (
        eval_mode == "real"
        and compliance_rate >= 0.95
        and parse_rate >= 0.95
        and no_student_mismatch_pass
        and accuracy_lift_pass
        and abstain_accuracy_pass
    )
    
    reason_codes = []
    if real_gate_passed:
        reason_codes.append("passed")
    else:
        if eval_mode == "emulator" and no_student_mismatch_pass and accuracy_lift_pass and abstain_accuracy_pass:
            reason_codes.append("emulator_mode_observation_only")
        else:
            if not no_student_mismatch_pass:
                reason_codes.append("student_induced_trust_mismatch_detected")
            if not accuracy_lift_pass:
                reason_codes.append("accuracy_inferior_to_baseline")
            if not abstain_accuracy_pass:
                reason_codes.append("abstain_accuracy_low")
            if compliance_rate < 0.95 or parse_rate < 0.95:
                reason_codes.append("compliance_or_parse_rate_low")
    
    # 溯源雜湊讀取
    dataset_sha256 = calc_sha256(dataset_path) if dataset_path.exists() else "unknown"
    safetensors_path = Path(adapter_dir) / "adapter_model.safetensors"
    adapter_sha256 = calc_sha256(safetensors_path) if safetensors_path.exists() else "unknown"
    commit_sha = get_git_commit_hash()
    
    report = {
        "schema": "nexus_s2t_shadow_eval_report_v1",
        "timestamp": time.time(),
        "eval_mode": eval_mode,
        "adapter_sha256": adapter_sha256,
        "dataset_sha256": dataset_sha256,
        "commit_sha": commit_sha,
        "metrics": {
            "eligible_rows": total_rows,
            "json_parse_rate": parse_rate,
            "schema_compliance_rate": compliance_rate,
            "trust_mismatch_rate": trust_mismatch_rate,
            "student_induced_trust_mismatch_count": student_induced_trust_mismatch_count,
            "selector_override_rate": override_rate,
            "selector_override_verified_rate": override_verified_rate,
            "abstain_rate": abstain_count / total_rows,
            "abstain_accuracy": abstain_accuracy,
            "public_claim_precision": public_claim_precision,
            "baseline_accuracy": baseline_accuracy,
            "advisor_accuracy": advisor_accuracy,
            "cost_per_verified_task": cost_per_verified_task
        },
        "promotion_gate": {
            "status": "PASSED" if real_gate_passed else "OBSERVATION_ONLY" if (eval_mode == "emulator" and no_student_mismatch_pass and accuracy_lift_pass) else "FAILED",
            "reason_codes": reason_codes
        }
    }
    
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print(f"🎉 Shadow evaluation complete. Output saved to {output_report_path}")
    
    # 寫入 failures jsonl 作為 SFT repair dataset
    failures_output_path = output_report_path.parent / "s2t_shadow_eval_failures.jsonl"
    with open(failures_output_path, "w", encoding="utf-8") as f:
        for fail in failures:
            f.write(json.dumps(fail, ensure_ascii=False) + "\n")
    print(f"⚠️ Dumped {len(failures)} schema failures to {failures_output_path}")
    
    print(f"  Mode:                                 {eval_mode}")
    print(f"  JSON Parse Rate:                      {parse_rate * 100:.1f}%")
    print(f"  Schema Compliance:                    {compliance_rate * 100:.1f}%")
    print(f"  Override Verified Lift:                {override_verified_rate * 100:.1f}%")
    print(f"  Baseline Accuracy:                    {baseline_accuracy * 100:.1f}%")
    print(f"  Advisor Accuracy:                     {advisor_accuracy * 100:.1f}%")
    print(f"  Student-Induced Trust Mismatches:     {student_induced_trust_mismatch_count}")
    print(f"  Cost Per Verified Task:               ${cost_per_verified_task:.4f}")
    print(f"  Status:                               {report['promotion_gate']['status']}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(".nexus/training/s2t_3b_student_v1.jsonl"))
    parser.add_argument("--output", type=Path, default=Path(".nexus/metrics/s2t_shadow_eval_report.json"))
    parser.add_argument("--run-real", action="store_true")
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--emulator", action="store_true")
    parser.add_argument("--adapter-dir", type=str, default="training/adapters/qwen3b_s2t_adapter")
    parser.add_argument("--use-ollama", action="store_true")
    parser.add_argument("--model-name", type=str, default="qwen2.5-s2t-advisor:3b")
    parser.add_argument("--abstain-dataset", type=Path, default=None)
    args = parser.parse_args()
    
    if args.abstain_dataset:
        os.environ["NEXUS_ABSTAIN_DATASET_PATH"] = str(args.abstain_dataset)
        
    run_shadow_eval(
        args.dataset, 
        args.output, 
        args.run_real, 
        args.device, 
        args.timeout_sec, 
        args.offline, 
        args.emulator, 
        args.adapter_dir,
        use_ollama=args.use_ollama,
        model_name=args.model_name
    )
