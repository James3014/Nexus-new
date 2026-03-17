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
    
    # Calculate stats
    success_rate = (df['status'] == 'PASS').mean() * 100
    avg_tokens = df['total_tokens'].mean()
    avg_health = df['health_score'].mean() if 'health_score' in df.columns else 0
    
    print(f"--- 📊 Nexus Evaluation Report ---")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Avg Tokens: {avg_tokens:.1f}")
    print(f"Avg Health: {avg_health:.1f}%")
    
    # Export to markdown
    report_md = f"""# Nexus Evaluation Summary
- **Success Rate**: {success_rate:.1f}%
- **Avg Tokens**: {avg_tokens:.1f}
- **Avg Health**: {avg_health:.1f}%

## Task Details
{df.to_markdown(index=False)}
"""
    Path("evaluation_report.md").write_text(report_md)
    print("✅ Report exported to evaluation_report.md")

if __name__ == "__main__":
    main()
