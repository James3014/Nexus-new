#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

def check_lesson_evidence(project_root: Path) -> bool:
    acceptance_file = project_root / ".nexus" / "reports" / "acceptance_check.json"
    if not acceptance_file.exists():
        # If no acceptance report, we assume it's either first run or everything is fine
        return True

    try:
        data = json.loads(acceptance_file.read_text(encoding="utf-8"))
    except Exception:
        return True

    # If acceptance passed, no need for lesson writeback evidence
    if data.get("status") == "PASS":
        return True

    # Failure detected, check for evidence
    evidence_found = False

    # Evidence A: .nexus/reports/lesson_writeback.json updated in last 24h
    lesson_file = project_root / ".nexus" / "reports" / "lesson_writeback.json"
    if lesson_file.exists():
        mtime = datetime.fromtimestamp(lesson_file.stat().st_mtime, tz=timezone.utc)
        if datetime.now(timezone.utc) - mtime < timedelta(hours=24):
            print(f"✅ Evidence found: {lesson_file} updated at {mtime}")
            evidence_found = True

    if not evidence_found:
        # Evidence B: nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md contains today's date
        matrix_file = project_root / "nexus_wiki_vault" / "06_Ops" / "Ops - Learning Closure Matrix.md"
        if matrix_file.exists():
            today_str = datetime.now().strftime("%Y-%m-%d")
            content = matrix_file.read_text(encoding="utf-8")
            if today_str in content:
                print(f"✅ Evidence found: {matrix_file} contains entry for {today_str}")
                evidence_found = True

    if not evidence_found:
        print("❌ Failure-to-Lesson check FAILED: Acceptance FAIL but no writeback evidence found.")
        print("Required evidence:")
        print("a) .nexus/reports/lesson_writeback.json (updated in last 24h)")
        print(f"b) nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md (contains entry for {datetime.now().strftime('%Y-%m-%d')})")
        return False

    return True

if __name__ == "__main__":
    project_root = Path.cwd()
    if check_lesson_evidence(project_root):
        sys.exit(0)
    else:
        sys.exit(1)
