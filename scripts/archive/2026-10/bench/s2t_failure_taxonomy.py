#!/usr/bin/env python3
"""
📊 S2T Failure Taxonomy Classifier & Analyzer
讀取 s2t_shadow_eval_failures.jsonl，對 3B 學生模型之幻覺進行二次精確分類，並生成結構化分析報告。
"""
import os
import sys
import json
from pathlib import Path

def main():
    failures_path = Path(".nexus/metrics/s2t_shadow_eval_failures.jsonl")
    report_json_path = Path(".nexus/metrics/s2t_failure_taxonomy_report.json")
    report_md_path = Path(output_file) if output_file else None

    if not failures_path.exists():
        print(f"❌ Failures file not found: {failures_path}")
        sys.exit(1)

    failures = []
    with open(failures_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                failures.append(json.loads(line))

    total_failures = len(failures)
    
    # 初始化分類計數
    taxonomy = {
        "missing_abstain_reason": 0,
        "string_none_instead_of_null": 0,
        "invalid_required_verifier": 0,
        "freeform_verifier_name": 0,
        "selected_candidate_not_in_candidates": 0,
        "missing_required_field": 0,
        "other": 0
    }

    categorized_failures = []

    for fail in failures:
        prediction = fail.get("prediction", {})
        err_msg = fail.get("error_msg", "")
        task_id = fail.get("task_id", "unknown")
        inputs = fail.get("input", {})
        target = fail.get("correct_target", {})
        
        # 預設使用預存的 error_type
        err_type = fail.get("error_type", "other")
        
        # 1. 檢查 missing required fields
        required_fields = ["selected_candidate_id", "selection_reason_codes", "required_verifier", "abstain_reason"]
        missing_fields = [f for f in required_fields if f not in prediction]
        if missing_fields:
            err_type = "missing_required_field"
        
        # 2. 檢查 selected candidate not in candidates
        elif "selected_candidate_id" in prediction:
            sel_id = prediction["selected_candidate_id"]
            candidate_ids = [c.get("id") for c in inputs.get("candidate_summaries", [])]
            if sel_id is not None and sel_id != "" and sel_id not in candidate_ids:
                err_type = "selected_candidate_not_in_candidates"
        
        # 如果還是 other，進行細化判定
        if err_type == "other":
            if "abstain_reason" in err_msg:
                err_type = "missing_abstain_reason"
            elif "required_verifier" in err_msg:
                val = prediction.get("required_verifier")
                if val == "none":
                    err_type = "string_none_instead_of_null"
                elif val in [
                    "cost", "cost_calculator", "cost_estimation", "cost_calculated", 
                    "re-evalute_candidates", "re-evalute_candidates_or_route", 
                    "verifier-check-candidate-costs", "re-eval_with_costs", 
                    "re-eval_with_human", "reconciliation", "revalidate_candidates", 
                    "cost_confirmation", "verify_candidate_exclusion_policies_and_calculate_costs"
                ]:
                    err_type = "freeform_verifier_name"
                else:
                    err_type = "invalid_required_verifier"

        if err_type not in taxonomy:
            err_type = "other"
            
        taxonomy[err_type] += 1
        categorized_failures.append({
            "task_id": task_id,
            "error_type": err_type,
            "error_msg": err_msg,
            "prediction": prediction,
            "correct_target": target
        })

    # 計算比例
    taxonomy_ratio = {k: v / total_failures for k, v in taxonomy.items()} if total_failures > 0 else {}

    # 生成 JSON report
    report_json = {
        "total_failures": total_failures,
        "taxonomy": taxonomy,
        "taxonomy_ratio": taxonomy_ratio,
        "failures": categorized_failures
    }

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_json, f, indent=2, ensure_ascii=False)

    # 生成 Markdown report
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# S2T 3B V1 Real Shadow Evaluation Failure Analysis\n\n")
        f.write(f"- **Analysis Date**: 2026-06-13\n")
        f.write(f"- **Total Failures**: {total_failures}\n\n")
        
        f.write("## Failure Taxonomy Distribution\n\n")
        f.write("| Error Type | Count | Ratio |\n")
        f.write("| --- | --- | --- |\n")
        for k, v in taxonomy.items():
            f.write(f"| `{k}` | {v} | {taxonomy_ratio.get(k, 0)*100:.1f}% |\n")
        f.write("\n")

        f.write("## Detailed Failure Cases\n\n")
        for idx, item in enumerate(categorized_failures):
            f.write(f"### Case {idx+1}: {item['task_id']}\n")
            f.write(f"- **Error Type**: `{item['error_type']}`\n")
            f.write(f"- **Error Message**: {item['error_msg']}\n")
            f.write(f"- **Prediction JSON**: `{json.dumps(item['prediction'])}`\n")
            f.write(f"- **Correct Target**: `{json.dumps(item['correct_target'])}`\n\n")

    print(f"🎉 Taxonomy complete. MD report saved to {report_md_path}")
    print(f"🎉 Taxonomy complete. JSON report saved to {report_json_path}")

if __name__ == "__main__":
    main()
