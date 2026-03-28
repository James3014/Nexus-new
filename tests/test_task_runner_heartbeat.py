from pathlib import Path


def test_write_heartbeat_preserves_phase_metrics_section(tmp_path, monkeypatch):
    from scripts.ops import task_runner

    heartbeat = tmp_path / "EXEC_LIVE_STATUS.md"
    heartbeat.write_text(
        "\n".join(
            [
                "# EXEC LIVE STATUS",
                "",
                "<!-- NEXUS_PHASE_METRICS:START -->",
                "## Nexus Phase Metrics (Auto Sync)",
                "| Phase | Health |",
                "| --- | ---: |",
                "| `P` | `90.00` |",
                "<!-- NEXUS_PHASE_METRICS:END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(task_runner, "HEARTBEAT", heartbeat)

    state = {
        "tasks": {
            "auto.repair.pipeline": {
                "status": "done",
                "retry": 0,
                "updated_at": "2026-03-27 12:00:00",
                "note": "ok",
            }
        }
    }

    task_runner.write_heartbeat(state)
    content = heartbeat.read_text(encoding="utf-8")
    assert "<!-- NEXUS_PHASE_METRICS:START -->" in content
    assert "<!-- NEXUS_PHASE_METRICS:END -->" in content
    assert "| `P` | `90.00` |" in content
