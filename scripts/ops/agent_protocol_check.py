#!/usr/bin/env python3
import sys
from pathlib import Path

def check_protocol():
    agents_md = Path("AGENTS.md")
    if not agents_md.exists():
        print("❌ AGENTS.md missing")
        return 1
    
    content = agents_md.read_text()
    required_terms = [
        "allowed_paths",
        "forbidden_paths",
        "max_files_touched",
        "Semantic Completion Criteria",
        "Evidence Reporting Format",
        "Failure-to-Lesson Writeback"
    ]
    
    missing = [term for term in required_terms if term not in content]
    
    if missing:
        print(f"❌ Protocol check FAILED. Missing: {', '.join(missing)}")
        return 1
    
    print("✅ Protocol check PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(check_protocol())
