#!/usr/bin/env python3
import pandas as pd
import sys
from pathlib import Path

def main():
    csv_path = Path("ci_benchmark.csv")
    if not csv_path.exists():
        print("❌ Error: ci_benchmark.csv not found.")
        sys.exit(1)
        
    df = pd.read_csv(csv_path)
    
    health_column = "health" if "health" in df.columns else "health_score"
    token_column = "tokens" if "tokens" in df.columns else "total_tokens"

    # Calculate stats
    success_rate = (df['status'] == 'PASS').mean() * 100
    avg_tokens = df[token_column].mean() if token_column in df.columns else 0
    avg_health = df[health_column].mean() if health_column in df.columns else 0
    
    print(f"--- 📊 Nexus Evaluation Report ---")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Avg Tokens: {avg_tokens:.1f}")
    print(f"Avg Health: {avg_health:.1f}%")
    
    # Export to markdown
    try:
        task_details = df.to_markdown(index=False)
    except ImportError:
        task_details = df.to_csv(index=False)

    report_md = f"""# Nexus Evaluation Summary
- **Success Rate**: {success_rate:.1f}%
- **Avg Tokens**: {avg_tokens:.1f}
- **Avg Health**: {avg_health:.1f}%

## Task Details
{task_details}
"""
    Path("evaluation_report.md").write_text(report_md)
    print("✅ Report exported to evaluation_report.md")

if __name__ == "__main__":
    main()
