import json
from datetime import datetime, timezone

lesson = {
    "event_id": "L-FORMAL-001",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "type": "FORMAL_LAW_REUSE",
    "details": {
        "law_id": "FUSION",
        "task_id": "formal-e2e-001",
        "result": "SUCCESS",
        "tokens_saved": 450
    },
    "evidence_ref": "dec8c60"
}

with open(".nexus/events/lessonevents.jsonl", "a") as f:
    f.write(json.dumps(lesson) + "\n")

print(f"✅ Formal Lesson appended to .nexus/events/lessonevents.jsonl")
