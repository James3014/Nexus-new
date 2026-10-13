import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def dispatch_alert(
    level: str, message: str, detail: dict = None, *, root: Path | str | None = None
):
    """Write one learn alert under ``<root>/.nexus/reports/alerts``.

    ``root`` is the workspace (project) root whose learn store raised the alert; callers must
    pass it.  Without it the alert lands under the process cwd (legacy behavior).
    """
    base = Path(root).expanduser().resolve() if root else Path.cwd()
    alert_dir = base / ".nexus" / "reports" / "alerts"
    alert_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    alert_id = f"learn_{int(datetime.now().timestamp())}"
    payload = {
        "alert_id": alert_id,
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "detail": detail or {},
    }
    alert_path = alert_dir / f"{alert_id}.json"
    alert_path.write_text(json.dumps(payload, indent=2))
    print(f"🚨 [Learn-Alert] {level}: {message}", file=sys.stderr)
    return alert_path
