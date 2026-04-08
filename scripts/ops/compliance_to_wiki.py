import json
import os
import time
from pathlib import Path
from datetime import datetime

# 🛡️ Nexus Compliance-to-Wiki Adapter (v22.5)
# This script transforms raw Nexus logs into human-readable Wiki pages.

REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_COMPLIANCE_DIR = REPO_ROOT / "nexus_wiki_vault" / "07_Compliance"
REPORTS_DIR = REPO_ROOT / ".nexus" / "reports"
KNOWLEDGE_DIR = REPO_ROOT / ".nexus" / "knowledge"

def transform_enterprise_audit():
    print("🚀 Transforming Enterprise Audit report...")
    report_file = REPORTS_DIR / "enterprise_audit.json"
    if not report_file.exists():
        print("⚠️ enterprise_audit.json not found.")
        return

    with open(report_file, "r") as f:
        data = json.load(f)

    timestamp_str = datetime.fromtimestamp(data.get("timestamp", time.time())).strftime("%Y-%m-%d %H:%M:%S")
    results = data.get("results", [])
    
    md_content = f"""# 🛡️ Compliance Status: Nexus Enterprise v22.5
- **Timestamp**: {timestamp_str}
- **Commit SHA**: `{data.get("commit_sha", "N/A")}`
- **Nexus Participation Ratio**: {data.get("nexus_participation_ratio", 0.0) * 100}%

## 🔍 Core Audit Dimensions (SOC2-like)
| Dimension | Status | Metrics |
|-----------|--------|---------|
"""
    for res in results:
        status_emoji = "✅ PASS" if res["status"] == "PASS" else "❌ FAIL"
        metrics = ", ".join([f"{k}: {v}" for k, v in res.items() if k not in ["name", "status"]])
        md_content += f"| {res['name']} | {status_emoji} | {metrics} |\n"

    md_content += f"\n## 🧱 Gate Summary\n"
    for k, v in data.get("gate_summary", {}).items():
        md_content += f"- **{k}**: {v}\n"

    target_path = WIKI_COMPLIANCE_DIR / "Current_Compliance_Status.md"
    with open(target_path, "w") as f:
        f.write(md_content)
    print(f"✅ Exported to {target_path}")

def transform_incidents():
    print("🚀 Transforming Incident logs from episodic memory...")
    memory_file = KNOWLEDGE_DIR / "episodic_memory.jsonl"
    if not memory_file.exists():
        print("⚠️ episodic_memory.jsonl not found.")
        return

    incidents = []
    with open(memory_file, "r") as f:
        for line in f:
            entry = json.loads(line)
            # Filter for failures or specific patterns
            if not entry.get("success", True) or entry.get("curiosity_failure_penalty", 0) > 0:
                incidents.append(entry)

    md_content = "# 🛡️ SLA Incident Logs (v22.5 - Traceability)\n"
    md_content += "| Timestamp | Task ID | Result | Root Cause | Trust Level |\n"
    md_content += "|-----------|---------|--------|------------|-------------|\n"

    for inc in incidents[-10:]: # Latest 10 incidents
        meta = inc.get("metadata", {})
        outcome = meta.get("nexus_outcome_v2", {})
        ts = inc.get("timestamp", "N/A")
        task_id = inc.get("task_id", "N/A")
        rc = meta.get("cycle_root_cause", "unknown")
        trust = outcome.get("trust_level", "untrusted")
        md_content += f"| {ts} | {task_id} | ❌ FAIL | {rc} | {trust} |\n"

    target_path = WIKI_COMPLIANCE_DIR / "Incident_Trace_Log.md"
    with open(target_path, "w") as f:
        f.write(md_content)
    print(f"✅ Exported to {target_path}")

def update_dashboard():
    # ... (原有代碼)
    pass

def distill_feynman_lessons():
    print("🚀 Distilling Feynman warnings into learning system lessons...")
    audit_dir = REPO_ROOT / "compliance" / "audit"
    lesson_file = KNOWLEDGE_DIR / "lesson_events.jsonl"
    
    warning_files = list(audit_dir.glob("feynman_warnings_*.json"))
    if not warning_files:
        print("ℹ️ No new Feynman warnings to distill.")
        return

    new_lessons = []
    for wf in warning_files:
        with open(wf, "r") as f:
            data = json.load(f)
            for warn in data.get("warnings", []):
                new_lessons.append({
                    "lesson_id": f"FEYNMAN-{int(time.time())}-{hash(warn) % 1000}",
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "category": "LOGIC_DRIFT",
                    "root_cause": "Feynman Audit Warning",
                    "evidence": [warn],
                    "corrective_action": "Align implementation with source documentation/spec.",
                    "confidence": 0.8,
                    "outcome": "success",
                    "task_id": "compliance-sync"
                })
        # Move processed files to archive to prevent duplicate lessons
        archive_dir = audit_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        os.rename(wf, archive_dir / wf.name)

    if new_lessons:
        with open(lesson_file, "a") as f:
            for lesson in new_lessons:
                f.write(json.dumps(lesson) + "\n")
        print(f"✅ Distilled {len(new_lessons)} lessons into {lesson_file}")

if __name__ == "__main__":
    os.makedirs(WIKI_COMPLIANCE_DIR, exist_ok=True)
    transform_enterprise_audit()
    transform_incidents()
    update_dashboard()
    distill_feynman_lessons()
