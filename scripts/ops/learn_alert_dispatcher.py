import os, json, sys
from pathlib import Path
from datetime import datetime, timezone

def dispatch_alert(level: str, message: str, detail: dict = None):
    alert_dir = Path(".nexus/reports/alerts")
    alert_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    alert_id = f"learn_{int(datetime.now().timestamp())}"
    payload = {"alert_id": alert_id, "timestamp": timestamp, "level": level, "message": message, "detail": detail or {}}
    alert_path = alert_dir / f"{alert_id}.json"
    alert_path.write_text(json.dumps(payload, indent=2))
    print(f"🚨 [Learn-Alert] {level}: {message}", file=sys.stderr)
    return alert_path
