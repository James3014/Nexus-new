import json
from pathlib import Path
from collections import Counter
import argparse

def analyze_benchmarks(file_path: Path):
    if not file_path.exists():
        print(f"Error: {file_path} not found.")
        return

    stats = {
        "total_rows": 0,
        "failure_reasons": Counter(),
        "stop_layers": Counter(),
        "diagnostics": {
            "refusals": 0,
            "empty_responses": 0,
            "syntax_fails": 0,
            "search_mismatches": 0
        },
        "costs": {
            "total_wall_time": 0.0,
            "total_retries": 0
        }
    }

    with open(file_path, "r") as f:
        for line in f:
            row = json.loads(line)
            stats["total_rows"] += 1
            
            receipt_path = row.get("receipt_path")
            if not receipt_path or not Path(receipt_path).exists():
                continue
                
            receipt = json.loads(Path(receipt_path).read_text())
            metrics = receipt.get("eval_metrics", {})
            diag = metrics.get("diagnostics", {})
            
            # Taxonomy Analysis
            stats["failure_reasons"][metrics.get("failure_class", "unknown")] += 1
            stats["stop_layers"][metrics.get("gate_exit", "unknown")] += 1
            
            # Diagnostic Analysis
            if diag.get("refusal_detected"): stats["diagnostics"]["refusals"] += 1
            if diag.get("empty_response"): stats["diagnostics"]["empty_responses"] += 1
            if not metrics.get("syntax_gate_passed"): stats["diagnostics"]["syntax_fails"] += 1
            if "SEARCH_MISMATCH" in receipt.get("failure_reason", ""): 
                stats["diagnostics"]["search_mismatches"] += 1
                
            # Cost Analysis
            stats["costs"]["total_wall_time"] += metrics.get("wall_time_sec_measured", 0.0)
            stats["costs"]["total_retries"] += metrics.get("retry_count", 0)

    # Output Results
    print("\n" + "="*40)
    print("🛡️  NEXUS PHASE 4 OFFLINE AUDIT REPORT")
    print("="*40)
    print(f"Total Rows Analyzed: {stats['total_rows']}")
    print("\n--- [STOP LAYER DISTRIBUTION] ---")
    for layer, count in stats["stop_layers"].items():
        print(f"{layer:15}: {count}")
        
    print("\n--- [FAILURE CLASS DISTRIBUTION] ---")
    for cls, count in stats["failure_reasons"].items():
        print(f"{cls:15}: {count}")
        
    print("\n--- [DIAGNOSTIC PATTERNS] ---")
    print(f"Model Refusals : {stats['diagnostics']['refusals']}")
    print(f"Empty Responses: {stats['diagnostics']['empty_responses']}")
    print(f"Syntax Fails   : {stats['diagnostics']['syntax_fails']}")
    print(f"Search Mismatch: {stats['diagnostics']['search_mismatches']}")
    
    print("\n--- [AGGREGATE COSTS] ---")
    avg_wall = stats['costs']['total_wall_time'] / stats['total_rows'] if stats['total_rows'] > 0 else 0
    print(f"Avg Wall Time  : {avg_wall:.2f}s")
    print(f"Total Retries  : {stats['costs']['total_retries']}")
    print("="*40 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path", type=str, help="Path to Step 6 JSONL results")
    args = parser.parse_args()
    analyze_benchmarks(Path(args.file_path))
