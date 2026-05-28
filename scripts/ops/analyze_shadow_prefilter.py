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

def analyze_prefilter(input_file: Path, output_dir: Path):
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
                # 篩選 prefilter 的 diagnostics telemetry (帶有 shadow_prefilter_verdict)
                if "shadow_prefilter_verdict" in data:
                    records.append(data)
            except json.JSONDecodeError:
                continue
                
    if not records:
        print("⚠️ No shadow prefilter telemetry records found.", file=sys.stderr)
        # 寫入空的 JSON summary 和 CSV details
        write_empty_reports(output_dir)
        return

    # 計算統計量
    total_count = len(records)
    agreement_count = 0
    high_risk_leaks = 0
    missing_run_id_count = 0
    
    # Stratum stats
    strata_stats = {
        "Low-risk": {"total": 0, "agreement": 0, "high_risk_leaks": 0},
        "High-risk": {"total": 0, "agreement": 0, "high_risk_leaks": 0},
        "Stress": {"total": 0, "agreement": 0, "high_risk_leaks": 0}
    }
    
    csv_rows = []
    
    for idx, row in enumerate(records):
        verdict = row.get("shadow_prefilter_verdict", "run")
        confidence = row.get("shadow_confidence", 0.0)
        savings = row.get("shadow_estimated_savings_ms", 0.0)
        final_verifier = row.get("final_verifier_result", True)
        run_id = row.get("run_id", "run_unknown")
        task_id = row.get("task_id", "task_unknown")
        task_kind = row.get("task_kind", "unknown")
        route = row.get("route", "unknown")
        timestamp = row.get("timestamp", "")
        
        # 判定 agreement
        # Agreement: 當 verdict == "skip" 時，final_verifier 應該為 True (代表安全 skip)；
        # 當 verdict == "run" 時，不論 verifier 成功與否均算符合 execution-ready
        is_agreed = True
        if verdict == "skip" and not final_verifier:
            is_agreed = False
            high_risk_leaks += 1
            
        if is_agreed:
            agreement_count += 1
            
        if run_id == "run_unknown":
            missing_run_id_count += 1
            
        # Classify stratum
        stratum = classify_stratum(row)
        strata_stats[stratum]["total"] += 1
        if is_agreed:
            strata_stats[stratum]["agreement"] += 1
        if verdict == "skip" and not final_verifier:
            strata_stats[stratum]["high_risk_leaks"] += 1
            
        # Append to CSV row
        csv_rows.append({
            "index": idx + 1,
            "task_id": task_id,
            "run_id": run_id,
            "stratum": stratum,
            "task_kind": task_kind,
            "route": route,
            "shadow_verdict": verdict,
            "shadow_confidence": confidence,
            "shadow_savings_ms": savings,
            "final_verifier_result": final_verifier,
            "agreement_status": "AGREED" if is_agreed else "DISAGREED_HIGH_RISK_LEAK",
            "timestamp": timestamp
        })

    overall_agreement_rate = round(agreement_count / total_count, 4) if total_count > 0 else 1.0
    
    # 產出 summary
    summary = {
        "timestamp_analyzed": timestamp_now(),
        "total_records": total_count,
        "overall_agreement_rate": overall_agreement_rate,
        "high_risk_leaks_count": high_risk_leaks,
        "data_quality_debt": {
            "missing_stable_run_id_count": missing_run_id_count,
            "missing_run_id_rate": round(missing_run_id_count / total_count, 4) if total_count > 0 else 0.0
        },
        "strata_breakdown": {
            s: {
                "total_samples": stats["total"],
                "agreement_rate": round(stats["agreement"] / stats["total"], 4) if stats["total"] > 0 else 1.0,
                "high_risk_leaks": stats["high_risk_leaks"]
            }
            for s, stats in strata_stats.items()
        }
    }
    
    # 寫入 JSON summary
    summary_file = output_dir / "prefilter_agreement_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)
        
    # 寫入 CSV details
    details_file = output_dir / "prefilter_agreement_details.csv"
    csv_headers = [
        "index", "task_id", "run_id", "stratum", "task_kind", "route",
        "shadow_verdict", "shadow_confidence", "shadow_savings_ms",
        "final_verifier_result", "agreement_status", "timestamp"
    ]
    with open(details_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()
        writer.writerows(csv_rows)
        
    print(f"✅ Prefilter analysis complete.")
    print(f"📊 Summary: {summary_file}")
    print(f"📝 Details: {details_file}")

def write_empty_reports(output_dir: Path):
    summary_file = output_dir / "prefilter_agreement_summary.json"
    details_file = output_dir / "prefilter_agreement_details.csv"
    
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp_analyzed": timestamp_now(),
            "total_records": 0,
            "overall_agreement_rate": 1.0,
            "high_risk_leaks_count": 0,
            "data_quality_debt": {"missing_stable_run_id_count": 0, "missing_run_id_rate": 0.0},
            "strata_breakdown": {}
        }, f, indent=4)
        
    with open(details_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["No records found"])

def timestamp_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze prefilter shadow telemetry")
    parser.add_argument("--input", type=str, default=".nexus/reports/shadow_telemetry.jsonl", help="Input JSONL path")
    parser.add_argument("--output-dir", type=str, default=".nexus/reports", help="Output directory")
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parents[2]
    input_path = project_root / args.input
    output_path = project_root / args.output_dir
    output_path.mkdir(parents=True, exist_ok=True)
    
    analyze_prefilter(input_path, output_path)
