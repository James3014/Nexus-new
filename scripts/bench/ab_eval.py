#!/usr/bin/env python3
import pandas as pd
import sys
from pathlib import Path

def compare(file_a: str, file_b: str):
    df_a = pd.read_csv(file_a)
    df_b = pd.read_csv(file_b)
    
    sr_a = (df_a['status'] == 'PASS').mean() * 100
    sr_b = (df_b['status'] == 'PASS').mean() * 100
    
    tk_a = df_a['total_tokens'].mean()
    tk_b = df_b['total_tokens'].mean()
    
    print(f"--- ⚖️ A/B Comparison: {file_a} vs {file_b} ---")
    print(f"Success Rate: {sr_a:.1f}% -> {sr_b:.1f}% ({sr_b - sr_a:+.1f}%)")
    print(f"Avg Tokens: {tk_a:.1f} -> {tk_b:.1f} ({tk_b - tk_a:+.1f})")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ab_eval.py <file_a> <file_b>")
    else:
        compare(sys.argv[1], sys.argv[2])
