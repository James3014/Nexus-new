import json
import hashlib
from pathlib import Path

def redact_task_id(task_id: str) -> str:
    """Apply one-way hash to task_id to mask original name."""
    if not task_id:
        return ""
    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:16]

def export_and_redact():
    project_root = Path(__file__).resolve().parents[2]
    source_log = project_root / ".nexus" / "metrics" / "s2t_runtime_adoption_evidence.jsonl"
    dest_log = project_root / "docs" / "reports" / "s2t_redacted_evidence_bundle.jsonl"

    if not source_log.exists():
        print(f"❌ Source log file not found at: {source_log}")
        return

    dest_log.parent.mkdir(parents=True, exist_ok=True)

    records_processed = 0
    redacted_count = 0

    with open(source_log, "r", encoding="utf-8") as infile, \
         open(dest_log, "w", encoding="utf-8") as outfile:
        for line in infile:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except Exception as e:
                print(f"⚠️ Failed to parse JSON line: {e}")
                continue

            # Redaction Logic
            if "task_id" in data:
                data["task_id"] = redact_task_id(data["task_id"])
                redacted_count += 1
            
            # Write to redacted bundle
            outfile.write(json.dumps(data) + "\n")
            records_processed += 1

    print("--- [NEXUS EXPORT] S2T Traces Redaction Complete ---")
    print(f"Source: {source_log}")
    print(f"Destination: {dest_log}")
    print(f"Processed Records: {records_processed}")
    print(f"Redacted Task IDs: {redacted_count}")
    print("✅ EVIDENCE_BUNDLE_EXPORTED_OK")

if __name__ == "__main__":
    export_and_redact()
