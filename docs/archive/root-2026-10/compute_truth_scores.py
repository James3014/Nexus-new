#!/usr/bin/env python3
import json
import sys
import pandas as pd
from pathlib import Path

def analyze_truth(jsonl_path: str):
    path = Path(jsonl_path)
    if not path.exists():
        print(f"❌ Error: {jsonl_path} not found.")
        return

    data = []
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    df = pd.DataFrame(data)
    
    # 📊 Truth Matrix Analysis
    total = len(df)
    passed = len(df[df["status"] == "PASS"])
    failed = len(df[df["status"] == "FAIL"])
    
    avg_health = df["health_score"].mean() if "health_score" in df else 0
    avg_duration = df["duration"].mean() if "duration" in df else 0
    
    # Repo-level breakdown
    df["repo_prefix"] = df["task_id"].apply(lambda x: x.split("__")[0])
    repo_stats = df.groupby("repo_prefix").agg({
        "status": lambda x: (x == "PASS").sum(),
        "task_id": "count"
    }).rename(columns={"status": "passed", "task_id": "total"})
    
    print("\n" + "="*40)
    print("🏆 PHASE 3 ELITE TRUTH REPORT")
    print("="*40)
    print(f"📈 Total Tasks: {total}")
    print(f"✅ PASSED:      {passed} ({passed/total*100:.1f}%)")
    print(f"❌ FAILED:      {failed} ({failed/total*100:.1f}%)")
    print(f"🧬 Avg Health:  {avg_health:.2f}")
    print(f"⏱️  Avg Duration: {avg_duration:.2f}s")
    print("-" * 20)
    print("📊 Repo Statistics:")
    print(repo_stats)
    print("="*40 + "\n")

    # 💾 Export Summary CSV
    summary_csv = path.with_suffix(".summary.csv")
    repo_stats.to_csv(summary_csv)
    print(f"💾 Summary saved to {summary_csv}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compute_truth_scores.py <results.jsonl>")
    else:
        analyze_truth(sys.argv[1])
