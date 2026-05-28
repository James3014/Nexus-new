#!/usr/bin/env python3
import json
import csv
import sys
import os
from pathlib import Path
from typing import Dict, Any, List

def classify_stratum(row: Dict[str, Any]) -> str:
    """把 shadow telemetry row 依照 route_strategy 或 task_kind 分類為 Low-risk, High-risk, Stress"""
    strategy = str(row.get("route_strategy", "")).lower()
    task_kind = str(row.get("task_kind", "")).lower()
    
    if "stress" in strategy or "stress" in task_kind:
        return "Stress"
    elif "hardened" in strategy or "high" in strategy or "security" in strategy:
        return "High-risk"
    else:
        return "Low-risk"

def analyze_compaction(input_file: Path, output_dir: Path):
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)
        
    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                # 篩選 compaction 的 diagnostics telemetry (帶有 shadow_compaction_ratio)
                if "shadow_compaction_ratio" in data:
                    records.append(data)
            except json.JSONDecodeError:
                continue
                
    if not records:
        print("⚠️ No shadow compaction telemetry records found.", file=sys.stderr)
        write_empty_reports(output_dir)
        return

    total_count = len(records)
    ratios = []
    original_tokens_sum = 0
    compacted_tokens_sum = 0
    schema_broken_count = 0
    missing_run_id_count = 0
    
    strata_stats = {
        "Low-risk": {"total": 0, "ratios": [], "orig": 0, "comp": 0, "schema_broken": 0},
        "High-risk": {"total": 0, "ratios": [], "orig": 0, "comp": 0, "schema_broken": 0},
        "Stress": {"total": 0, "ratios": [], "orig": 0, "comp": 0, "schema_broken": 0}
    }
    
    saving_details = []
    failed_schema_rows = []
    
    for idx, row in enumerate(records):
        ratio = row.get("shadow_compaction_ratio", 0.0)
        orig = row.get("shadow_original_tokens", 0)
        comp = row.get("shadow_compacted_tokens", 0)
        schema_preserved = row.get("shadow_schema_preserved", True)
        render_id = row.get("prompt_render_id", "render_unknown")
        run_id = row.get("run_id", "run_unknown")
        task_id = row.get("task_id", "task_unknown")
        task_kind = row.get("task_kind", "unknown")
        timestamp = row.get("timestamp", "")
        
        ratios.append(ratio)
        original_tokens_sum += orig
        compacted_tokens_sum += comp
        
        if not schema_preserved:
            schema_broken_count += 1
            
        if run_id == "run_unknown":
            missing_run_id_count += 1
            
        stratum = classify_stratum(row)
        strata_stats[stratum]["total"] += 1
        strata_stats[stratum]["ratios"].append(ratio)
        strata_stats[stratum]["orig"] += orig
        strata_stats[stratum]["comp"] += comp
        if not schema_preserved:
            strata_stats[stratum]["schema_broken"] += 1
            
        record_detail = {
            "index": idx + 1,
            "task_id": task_id,
            "run_id": run_id,
            "stratum": stratum,
            "task_kind": task_kind,
            "prompt_render_id": render_id,
            "shadow_compaction_ratio": ratio,
            "shadow_original_tokens": orig,
            "shadow_compacted_tokens": comp,
            "shadow_schema_preserved": "PRESERVED" if schema_preserved else "BROKEN_VIOLATION",
            "timestamp": timestamp
        }
        
        saving_details.append(record_detail)
        
        if not schema_preserved:
            failed_schema_rows.append(record_detail)

    # 統計彙整
    avg_ratio = round(sum(ratios) / total_count, 4) if total_count > 0 else 0.0
    med_ratio = round(sorted(ratios)[total_count // 2], 4) if total_count > 0 else 0.0
    max_ratio = max(ratios) if total_count > 0 else 0.0
    min_ratio = min(ratios) if total_count > 0 else 0.0
    
    total_saved_tokens = original_tokens_sum - compacted_tokens_sum
    overall_saving_rate = round(total_saved_tokens / original_tokens_sum, 4) if original_tokens_sum > 0 else 0.0
    
    summary = {
        "timestamp_analyzed": timestamp_now(),
        "total_records": total_count,
        "compaction_ratio_metrics": {
            "average": avg_ratio,
            "median": med_ratio,
            "max": max_ratio,
            "min": min_ratio
        },
        "token_savings_metrics": {
            "total_original_tokens": original_tokens_sum,
            "total_compacted_tokens": compacted_tokens_sum,
            "total_saved_tokens": total_saved_tokens,
            "overall_saving_rate": overall_saving_rate
        },
        "schema_preservation_violations_count": schema_broken_count,
        "data_quality_debt": {
            "missing_stable_run_id_count": missing_run_id_count,
            "missing_run_id_rate": round(missing_run_id_count / total_count, 4) if total_count > 0 else 0.0
        },
        "strata_breakdown": {
            s: {
                "total_samples": stats["total"],
                "avg_compaction_ratio": round(sum(stats["ratios"]) / stats["total"], 4) if stats["total"] > 0 else 0.0,
                "total_saved_tokens": stats["orig"] - stats["comp"],
                "saving_rate": round((stats["orig"] - stats["comp"]) / stats["orig"], 4) if stats["orig"] > 0 else 0.0,
                "schema_preservation_violations": stats["schema_broken"]
            }
            for s, stats in strata_stats.items()
        }
    }
    
    # 寫入 JSON summary
    summary_file = output_dir / "compaction_saving_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
        
    # 寫入所有 details CSV
    details_file = output_dir / "compaction_saving_details.csv"
    csv_headers = [
        "index", "task_id", "run_id", "stratum", "task_kind", "prompt_render_id",
        "shadow_compaction_ratio", "shadow_original_tokens", "shadow_compacted_tokens",
        "shadow_schema_preserved", "timestamp"
    ]
    with open(details_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(saving_details)
        
    # 寫入 failed_schema CSV (僅包含違反 schema 案例)
    failed_file = output_dir / "compaction_failed_schema.csv"
    with open(failed_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(failed_schema_rows)
        
    print(f"✅ Compaction analysis complete.")
    print(f"📊 Summary: {summary_file}")
    print(f"📝 Saving Details: {details_file}")
    print(f"⚠️ Failed Schema: {failed_file} (Violations: {schema_broken_count})")

def write_empty_reports(output_dir: Path):
    summary_file = output_dir / "compaction_saving_summary.json"
    details_file = output_dir / "compaction_saving_details.csv"
    failed_file = output_dir / "compaction_failed_schema.csv"
    
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp_analyzed": timestamp_now(),
            "total_records": 0,
            "compaction_ratio_metrics": {"average": 0.0, "median": 0.0, "max": 0.0, "min": 0.0},
            "token_savings_metrics": {"total_original_tokens": 0, "total_compacted_tokens": 0, "total_saved_tokens": 0, "overall_saving_rate": 0.0},
            "schema_preservation_violations_count": 0,
            "data_quality_debt": {"missing_stable_run_id_count": 0, "missing_run_id_rate": 0.0},
            "strata_breakdown": {}
        }, f, indent=4)
        
    for path in [details_file, failed_file]:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["No records found"])

def timestamp_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze compaction shadow telemetry")
    parser.add_argument("--input", type=str, default=".nexus/reports/shadow_telemetry.jsonl", help="Input JSONL path")
    parser.add_argument("--output-dir", type=str, default=".nexus/reports", help="Output directory")
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parents[2]
    input_path = project_root / args.input
    output_path = project_root / args.output_dir
    output_path.mkdir(parents=True, exist_ok=True)
    
    analyze_compaction(input_path, output_path)
