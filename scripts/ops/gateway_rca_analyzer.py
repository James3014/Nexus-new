#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

def analyze_gateway_telemetry(jsonl_path: str | Path, bins: List[int] = None) -> Dict[str, Any]:
    src = Path(jsonl_path)
    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {jsonl_path}")

    if bins is None:
        bins = [1000, 5000, 10000]
    else:
        bins = sorted(bins)

    # Format values for bucket keys
    def format_val(val: int) -> str:
        if val >= 1000 and val % 1000 == 0:
            return f"{val // 1000}k"
        return str(val)

    # Generate bucket keys dynamically
    bucket_keys: List[str] = []
    for i, b in enumerate(bins):
        if i == 0:
            bucket_keys.append(f"0-{format_val(b)}")
        else:
            bucket_keys.append(f"{format_val(bins[i-1])}-{format_val(b)}")
    bucket_keys.append(f"{format_val(bins[-1])}+")

    # Initialize buckets with parser tracking
    buckets: Dict[str, Dict[str, Any]] = {
        key: {
            "count": 0,
            "total_sec": 0.0,
            "provider_wait_sec": 0.0,
            "parse_sec": 0.0,
            "timeouts": 0
        }
        for key in bucket_keys
    }

    rows: List[Dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                rows.append(json.loads(line_str))
            except json.JSONDecodeError:
                pass

    total_rows = len(rows)
    gateway_calls = 0
    timeouts = 0
    total_total_sec = 0.0
    total_provider_wait_sec = 0.0
    total_parse_sec = 0.0
    total_chars = 0

    for row in rows:
        total_sec = float(row.get("gateway_total_sec") or row.get("gateway_process_sec") or 0.0)
        provider_wait = float(row.get("gateway_provider_wait_sec") or row.get("gateway_process_sec") or 0.0)
        parse_sec = float(row.get("gateway_parse_sec") or 0.0)
        chars = int(row.get("gateway_total_chars") or 0)
        
        status = str(row.get("status") or "").upper()
        error_category = str(row.get("error_category") or "").lower()
        is_timeout = (error_category == "timeout") or ("timeout" in str(row.get("summary") or "").lower())

        if chars > 0 or total_sec > 0.0:
            gateway_calls += 1
            total_total_sec += total_sec
            total_provider_wait_sec += provider_wait
            total_parse_sec += parse_sec
            total_chars += chars
            
            if is_timeout:
                timeouts += 1

            # Determine dynamic bucket
            b_key = bucket_keys[-1]
            for i, b in enumerate(bins):
                if chars < b:
                    b_key = bucket_keys[i]
                    break
                
            buckets[b_key]["count"] += 1
            buckets[b_key]["total_sec"] += total_sec
            buckets[b_key]["provider_wait_sec"] += provider_wait
            buckets[b_key]["parse_sec"] += parse_sec
            if is_timeout:
                buckets[b_key]["timeouts"] += 1

    # Aggregations
    avg_total_sec = total_total_sec / gateway_calls if gateway_calls > 0 else 0.0
    avg_provider_wait = total_provider_wait_sec / gateway_calls if gateway_calls > 0 else 0.0
    avg_parse_sec = total_parse_sec / gateway_calls if gateway_calls > 0 else 0.0
    avg_chars = total_chars / gateway_calls if gateway_calls > 0 else 0.0
    
    total_gateway_overhead = total_total_sec - total_provider_wait_sec
    provider_wait_ratio = total_provider_wait_sec / total_total_sec if total_total_sec > 0 else 0.0
    gateway_overhead_ratio = total_gateway_overhead / total_total_sec if total_total_sec > 0 else 0.0

    report = {
        "metadata": {
            "source_file": str(src.resolve()),
            "total_rows": total_rows,
            "gateway_calls": gateway_calls,
            "total_timeouts": timeouts,
            "configured_bins": bins
        },
        "averages": {
            "avg_latency_sec": round(avg_total_sec, 4),
            "avg_provider_wait_sec": round(avg_provider_wait, 4),
            "avg_parse_sec": round(avg_parse_sec, 4),
            "avg_payload_chars": round(avg_chars, 1),
        },
        "shares": {
            "provider_wait_share": round(provider_wait_ratio, 4),
            "gateway_overhead_share": round(gateway_overhead_ratio, 4),
            "timeout_share_of_gateway": round(timeouts / gateway_calls if gateway_calls > 0 else 0.0, 4),
        },
        "buckets": buckets
    }
    return report

def generate_markdown_report(report: Dict[str, Any]) -> str:
    meta = report["metadata"]
    averages = report["averages"]
    shares = report["shares"]
    buckets = report["buckets"]
    
    md = []
    md.append("# Gateway Payload & Latency Root Cause Analysis (RCA)")
    md.append("")
    md.append("> [!NOTE]")
    md.append("> 本報表屬 observation-only，僅供治理、時延分拆與成本分析觀測，不作為 public claim 或門禁判定依據。")
    md.append("")
    md.append("## 📊 概覽與元數據 (Overview & Metadata)")
    md.append(f"- **來源檔案**: `{meta['source_file']}`")
    md.append(f"- **總行數**: `{meta['total_rows']}`")
    md.append(f"- **實體 Gateway 呼叫數**: `{meta['gateway_calls']}`")
    md.append(f"- **總超時次數 (Gateway Timeouts)**: `{meta['total_timeouts']}`")
    md.append(f"- **分桶閾值配置 (Calibrated Bins)**: `{meta['configured_bins']}`")
    md.append("")
    md.append("## ⏱️ 平均時延與負載 (Averages)")
    md.append(f"- **平均總時延 (Avg Latency)**: `{averages['avg_latency_sec']}s`")
    md.append(f"- **平均 Provider 等待時延 (Avg Provider Wait)**: `{averages['avg_provider_wait_sec']}s`")
    md.append(f"- **平均 JSON 解析與 Battlesuit 建立時延 (Avg Parse/Setup)**: `{averages['avg_parse_sec']}s`")
    md.append(f"- **平均 Payload 長度 (Avg Payload Chars)**: `{averages['avg_payload_chars']} chars`")
    md.append("")
    md.append("## 🎯 時延拆分佔比 (Latency Breakdown Shares)")
    md.append(f"- **Provider 等待時間佔比 (Provider Wait Share)**: `{shares['provider_wait_share'] * 100:.2f}%`")
    md.append(f"- **Gateway 內部開銷佔比 (Gateway Overhead Share)**: `{shares['gateway_overhead_share'] * 100:.2f}%`")
    md.append(f"- **超時佔比 (Timeout Share of Gateway Calls)**: `{shares['timeout_share_of_gateway'] * 100:.2f}%`")
    md.append("")
    md.append("## 📦 負載大小分組分析 (Payload Size Buckets with Parse Overhead)")
    md.append("| Payload Bucket | Call Count | Avg Latency (s) | Avg Provider Wait (s) | Avg Parse/Setup (s) | Timeouts |")
    md.append("| --- | --- | --- | --- | --- | --- |")
    
    for b_key, b_data in buckets.items():
        count = b_data["count"]
        avg_lat = b_data["total_sec"] / count if count > 0 else 0.0
        avg_wait = b_data["provider_wait_sec"] / count if count > 0 else 0.0
        avg_parse = b_data["parse_sec"] / count if count > 0 else 0.0
        md.append(f"| {b_key} | {count} | {avg_lat:.4f}s | {avg_wait:.4f}s | {avg_parse:.4f}s | {b_data['timeouts']} |")
        
    return "\n".join(md)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 gateway_rca_analyzer.py <path_to_jsonl> [bin1,bin2,...]")
        sys.exit(1)
        
    custom_bins = None
    if len(sys.argv) > 2:
        try:
            custom_bins = [int(x) for x in sys.argv[2].split(",")]
        except ValueError:
            print("Error: Bins must be comma-separated integers.")
            sys.exit(1)

    try:
        report_data = analyze_gateway_telemetry(sys.argv[1], bins=custom_bins)
        print(generate_markdown_report(report_data))
    except Exception as e:
        print(f"Error executing analyzer: {e}")
        sys.exit(1)
