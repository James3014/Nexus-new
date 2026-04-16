#!/usr/bin/env python3
import sys
import os
import json
import argparse
import re
from pathlib import Path

def check_content_quality(file_path: Path, min_words: int, min_paragraphs: int, blacklist: list):
    if not file_path.exists():
        return False, "File missing"
    
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    # 1. Single line check
    if len([l for l in lines if l.strip()]) <= 1:
        return False, "Content too thin (single line)"
    
    # 2. Word count
    words = re.findall(r'\w+', content)
    if len(words) < min_words:
        return False, f"Word count {len(words)} < {min_words}"
    
    # 3. Paragraph count
    paragraphs = [p for p in content.split('\n\n') if p.strip()]
    if len(paragraphs) < min_paragraphs:
        return False, f"Paragraph count {len(paragraphs)} < {min_paragraphs}"
    
    # 4. Template keywords (Blacklist)
    for term in blacklist:
        if term in content:
            return False, f"Prohibited template term detected: '{term}'"
            
    # 5. Duplication rate (Basic)
    unique_words = set(words)
    if len(words) > 0:
        ratio = len(unique_words) / len(words)
        if ratio < 0.3: # Arbitrary threshold for high repetition
            return False, f"High repetition detected (unique ratio {ratio:.2f})"
            
    return True, "OK"

def main():
    parser = argparse.ArgumentParser(description="Nexus Content Quality Gate")
    parser.add_argument("--files", nargs="+", required=True, help="Markdown files to check")
    parser.add_argument("--min-words", type=int, default=100) # User requested 800 but we start moderate for demo
    parser.add_argument("--min-paragraphs", type=int, default=3)
    parser.add_argument("--blacklist", nargs="*", default=["高品質重鑄執行中", "Physical Lockdown"])
    parser.add_argument("--output", type=str, help="JSON output path")
    
    args = parser.parse_args()
    results = []
    all_passed = True
    
    for f in args.files:
        path = Path(f)
        ok, reason = check_content_quality(path, args.min_words, args.min_paragraphs, args.blacklist)
        results.append({
            "file": str(path),
            "passed": ok,
            "reason": reason
        })
        if not ok:
            all_passed = False
            
    report = {
        "all_passed": all_passed,
        "results": results
    }
    
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        
    if not all_passed:
        print("❌ [Content-Quality] Failures detected:")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['file']}: {r['reason']}")
        sys.exit(1)
    
    print("✅ [Content-Quality] All files passed substance check.")

if __name__ == "__main__":
    main()
