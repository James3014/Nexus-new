import json
import subprocess
from pathlib import Path


def test_write_phase_metrics_updates_run_file_and_live_status(tmp_path):
    project_root = tmp_path
    (project_root / "docs").mkdir(parents=True)
    (project_root / ".nexus" / "runs").mkdir(parents=True)
    status_file = project_root / "docs" / "EXEC_LIVE_STATUS.md"
    status_file.write_text("# Live\n", encoding="utf-8")

    script = Path("/Users/jameschen/Workspace/nexus/scripts/ops/write_phase_metrics.py")
    proc = subprocess.run(
        ["/Users/jameschen/Workspace/nexus/.venv/bin/python", str(script)],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    latest_metrics = project_root / ".nexus" / "runs" / "latest" / "phase_metrics.json"
    assert latest_metrics.exists()

    payload = json.loads(latest_metrics.read_text(encoding="utf-8"))
    assert set(payload["phase_metrics"].keys()) == {"P", "X", "D", "R", "A", "C"}
    assert "pipeline_health" in payload

    run_metrics = project_root / ".nexus" / "runs" / payload["task_id"] / "phase_metrics.json"
    assert run_metrics.exists()

    updated_status = status_file.read_text(encoding="utf-8")
    assert "<!-- NEXUS_PHASE_METRICS:START -->" in updated_status
    assert "<!-- NEXUS_PHASE_METRICS:END -->" in updated_status
