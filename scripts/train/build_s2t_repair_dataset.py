#!/usr/bin/env python3
"""
🛠️ S2T Repair Dataset Builder
讀取影子評估中的 failures jsonl，融合原始 SFT 數據集，生成 v2 修復對比微調數據集。
"""
import os
import sys
import json
from pathlib import Path

# 允許的驗證器
ALLOWED_VERIFIERS = ["pytest", "claim_gate", "delivery_gate", "hidden_verifier"]

def main():
    failures_path = Path(".nexus/metrics/s2t_shadow_eval_failures.jsonl")
    sft_v1_path = Path(".nexus/training/s2t_3b_student_v1.jsonl")
    
    output_v2_path = Path(".nexus/training/s2t_3b_repair_v2.jsonl")
    output_card_path = Path(".nexus/training/s2t_3b_repair_v2_dataset_card.json")

    if not sft_v1_path.exists():
        print(f"❌ SFT v1 dataset not found: {sft_v1_path}")
        sys.exit(1)

    # 1. 讀取原始 35 筆資料
    sft_v1_rows = {}
    with open(sft_v1_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                sft_v1_rows[row["task_id"]] = row

    # 2. 讀取 33 筆失敗
    failures = []
    if failures_path.exists():
        with open(failures_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    failures.append(json.loads(line))
    else:
        print(f"⚠️ Warning: failures file not found: {failures_path}. Will use raw targets.")

    repair_rows = []
    failed_task_ids = set()

    # 3. 處理失敗，生成對比修復數據
    for fail in failures:
        task_id = fail.get("task_id")
        failed_task_ids.add(task_id)
        
        err_type = fail.get("error_type", "other")
        inputs = fail.get("input")
        pred = fail.get("prediction")
        correct_target = fail.get("correct_target")
        
        # 門禁與自適應糾正 correct_target
        if not correct_target:
            # Fallback
            correct_target = sft_v1_rows.get(task_id, {}).get("target", {})
            
        # 強制 4 個 key 存在性與正確性
        for key in ["selected_candidate_id", "selection_reason_codes", "required_verifier", "abstain_reason"]:
            if key not in correct_target:
                correct_target[key] = None if key != "selection_reason_codes" else []
                
        # 糾正 required_verifier enum
        if correct_target.get("required_verifier") not in ALLOWED_VERIFIERS:
            correct_target["required_verifier"] = None

        # 動態生成 Contract Reminder 提示
        if err_type == "missing_abstain_reason":
            reminder = "Reminder: When abstaining, you MUST output 'abstain_reason' field with a descriptive string value. Even if not abstaining, 'abstain_reason' key must exist and be null."
        elif err_type == "string_none_instead_of_null":
            reminder = "Reminder: Do NOT output string value 'none' for required_verifier. You MUST use null (None in Python) if no verifier is required."
        elif err_type == "freeform_verifier_name":
            reminder = f"Reminder: Do NOT output freeform verifier name. required_verifier MUST be null or one of {ALLOWED_VERIFIERS}."
        elif err_type == "missing_required_field":
            reminder = "Reminder: Every JSON output MUST strictly contain all 4 keys: selected_candidate_id, selection_reason_codes, required_verifier, abstain_reason."
        else:
            reminder = "Reminder: Maintain standard JSON schema compliance. Output strictly 4 keys without deviation."

        repair_rows.append({
            "task_id": task_id,
            "error_type": err_type,
            "input": inputs,
            "bad_prediction": pred,
            "correct_target": correct_target,
            "contract_reminder": reminder
        })

    # 4. 處理沒失敗的原始成功數據，作為正面 anchor
    for task_id, sft_row in sft_v1_rows.items():
        if task_id not in failed_task_ids:
            inputs = sft_row.get("input")
            correct_target = sft_row.get("target")
            
            # 強制 schema
            for key in ["selected_candidate_id", "selection_reason_codes", "required_verifier", "abstain_reason"]:
                if key not in correct_target:
                    correct_target[key] = None if key != "selection_reason_codes" else []
            if correct_target.get("required_verifier") not in ALLOWED_VERIFIERS:
                correct_target["required_verifier"] = None

            repair_rows.append({
                "task_id": task_id,
                "error_type": "none",
                "input": inputs,
                "bad_prediction": None,
                "correct_target": correct_target,
                "contract_reminder": "Reminder: Maintain standard JSON schema compliance."
            })

    # 5. 門禁驗證所有 row
    print("🛡️ Running build-time validation on repair dataset...")
    for idx, row in enumerate(repair_rows):
        target = row["correct_target"]
        
        # 1. 欄位數校驗
        for k in ["selected_candidate_id", "selection_reason_codes", "required_verifier", "abstain_reason"]:
            if k not in target:
                raise ValueError(f"Build Gate Fail: Missing key '{k}' in row {idx} correct_target")
                
        # 2. enum 校驗
        v = target["required_verifier"]
        if v is not None and v not in ALLOWED_VERIFIERS:
            raise ValueError(f"Build Gate Fail: Invalid verifier '{v}' in row {idx} correct_target")

    # 寫入 v2 repair dataset
    output_v2_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_v2_path, "w", encoding="utf-8") as f:
        for r in repair_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 寫入 dataset card
    card = {
        "dataset_name": "s2t_3b_repair_v2",
        "total_rows": len(repair_rows),
        "failed_rows_integrated": len(failed_task_ids),
        "success_anchors_integrated": len(repair_rows) - len(failed_task_ids),
        "schema_compliance_guarantee": "Strictly verified 4 keys and restricted enum verifier",
        "timestamp": 1781322220.0
    }
    with open(output_card_path, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False)

    print(f"🎉 Repair dataset v2 build complete: {output_v2_path} (Total: {len(repair_rows)} rows)")
    print(f"🎉 Dataset card saved to: {output_card_path}")

if __name__ == "__main__":
    main()
