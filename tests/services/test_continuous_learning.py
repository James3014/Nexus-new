import json
import os
from pathlib import Path
from types import SimpleNamespace

from nexus.services.continuous_learning import (
    finalize_learning_loop,
    refresh_writeback_status,
    run_protocol_startup_gate,
)


def _build_state(task_id: str = "task-1", **metadata):
    return SimpleNamespace(task_id=task_id, metadata=metadata)


def test_run_protocol_startup_gate_records_ack_and_strict_ci(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "AGENT_MANDATORY_PROTOCOL.md").write_text("protocol", encoding="utf-8")
    scripts_ops = tmp_path / "scripts" / "ops"
    scripts_ops.mkdir(parents=True, exist_ok=True)
    (scripts_ops / "ci_gate.py").write_text("print('ok')", encoding="utf-8")

    calls = []

    def fake_runner(cmd, cwd):
        calls.append((cmd, cwd))
        return 0, "CI PASS", ""

    result = run_protocol_startup_gate(tmp_path, command_runner=fake_runner)

    assert result.ok is True
    assert result.ci_mode == "strict"
    assert any("--strict" in segment for segment in calls[0][0])

    ack_log = tmp_path / ".nexus" / "events" / "protocol_ack.jsonl"
    session_log = tmp_path / ".nexus" / "events" / "session_start.jsonl"
    assert ack_log.exists()
    assert session_log.exists()

    ack_row = json.loads(ack_log.read_text(encoding="utf-8").strip().splitlines()[-1])
    session_row = json.loads(session_log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert ack_row["protocol_path"].endswith("docs/AGENT_MANDATORY_PROTOCOL.md")
    assert session_row["ci_gate_mode"] == "strict"
    assert session_row["ci_gate_ok"] is True


def test_run_protocol_startup_gate_uses_dry_run_for_read_only_command(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "AGENT_MANDATORY_PROTOCOL.md").write_text("protocol", encoding="utf-8")
    scripts_ops = tmp_path / "scripts" / "ops"
    scripts_ops.mkdir(parents=True, exist_ok=True)
    (scripts_ops / "ci_gate.py").write_text("print('ok')", encoding="utf-8")

    calls = []

    def fake_runner(cmd, cwd):
        calls.append(cmd)
        return 0, "CI PASS", ""

    result = run_protocol_startup_gate(
        tmp_path,
        command_name="nexus:status",
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert result.ci_mode == "dry-run-readonly"
    assert any("--dry-run" in segment for segment in calls[0])


def test_finalize_learning_loop_writes_lessons_and_writeback_todo(tmp_path):
    state = _build_state(
        task_id="nexus-learn-1",
        task_description="Harden learning loop",
        cycle_root_cause="phantom success due to missing proof",
        rejection_history=["missing write-back"],
        phantom_success_reason="proof missing",
        learning_signal_updated=True,
        policy_patch_applied=True,
    )

    result = finalize_learning_loop(tmp_path, state, success=False, source="pipeline.crystallize")

    lessons_file = tmp_path / ".codex_lessons.md"
    writeback_file = tmp_path / ".nexus" / "reports" / "writeback_todo.json"

    assert result["lessons_written"] is True
    assert lessons_file.exists()
    lessons_text = lessons_file.read_text(encoding="utf-8")
    assert "phantom success due to missing proof" in lessons_text
    assert "proof missing" in lessons_text

    assert writeback_file.exists()
    todo = json.loads(writeback_file.read_text(encoding="utf-8"))
    assert todo["task_id"] == "nexus-learn-1"
    assert todo["writeback_required"] is True
    assert todo["delta_artifacts"]["index_delta"].endswith("_INDEX.delta.md")
    assert any(item["target"].endswith("INDEX.md") for item in todo["items"])
    assert any(item["target"].endswith(".codex_lessons.md") for item in todo["items"])
    assert result["delivery_status"] == "code_done_writeback_pending"
    assert state.metadata["delivery_status"] == "code_done_writeback_pending"


def test_finalize_learning_loop_marks_fully_delivered_when_no_writeback_needed(tmp_path):
    state = _build_state(task_id="nexus-learn-2", task_description="noop")

    result = finalize_learning_loop(tmp_path, state, success=True, source="pipeline.crystallize")

    todo = json.loads((tmp_path / ".nexus" / "reports" / "writeback_todo.json").read_text(encoding="utf-8"))
    assert result["writeback_required"] is False
    assert result["delivery_status"] == "fully_delivered"
    assert state.metadata["delivery_status"] == "fully_delivered"
    assert all(item["status"] == "completed" for item in todo["items"])


def test_refresh_writeback_status_promotes_pending_to_fully_delivered(tmp_path):
    state = _build_state(
        task_id="nexus-learn-3",
        task_description="sync writeback",
        cycle_root_cause="missing docs sync",
        rejection_history=["docs pending"],
    )

    result = finalize_learning_loop(tmp_path, state, success=True, source="pipeline.crystallize")
    assert result["delivery_status"] == "code_done_writeback_pending"

    todo_path = tmp_path / ".nexus" / "reports" / "writeback_todo.json"
    docs_index = tmp_path / "docs" / "INDEX.md"
    spec_file = tmp_path / "MUSE_ENGINE_SPEC_V17.1_HARDENED.md"
    docs_index.parent.mkdir(parents=True, exist_ok=True)
    docs_index.write_text("updated index", encoding="utf-8")
    spec_file.write_text("updated spec", encoding="utf-8")

    newer_mtime = todo_path.stat().st_mtime + 5
    os.utime(docs_index, (newer_mtime, newer_mtime))
    os.utime(spec_file, (newer_mtime, newer_mtime))

    refreshed = refresh_writeback_status(tmp_path, state=state, source="test-refresh")

    todo = json.loads(todo_path.read_text(encoding="utf-8"))
    assert refreshed["delivery_status"] == "fully_delivered"
    assert state.metadata["delivery_status"] == "fully_delivered"
    assert all(item["status"] == "completed" for item in todo["items"])
    completion_log = tmp_path / ".nexus" / "events" / "writeback_completion.jsonl"
    assert completion_log.exists()


def test_refresh_writeback_status_auto_applies_delta_artifacts(tmp_path):
    state = _build_state(
        task_id="nexus-learn-4",
        task_description="auto apply writeback",
        cycle_root_cause="need indexed doc sync",
        rejection_history=["index delta pending", "spec delta pending"],
    )

    result = finalize_learning_loop(tmp_path, state, success=True, source="pipeline.crystallize")
    assert result["delivery_status"] == "code_done_writeback_pending"

    refreshed = refresh_writeback_status(tmp_path, state=state, source="startup-gate")

    index_text = (tmp_path / "docs" / "INDEX.md").read_text(encoding="utf-8")
    spec_text = (tmp_path / "MUSE_ENGINE_SPEC_V17.1_HARDENED.md").read_text(encoding="utf-8")
    todo = json.loads((tmp_path / ".nexus" / "reports" / "writeback_todo.json").read_text(encoding="utf-8"))

    assert refreshed["delivery_status"] == "fully_delivered"
    assert state.metadata["delivery_status"] == "fully_delivered"
    assert "## Auto Writeback: nexus-learn-4" in index_text
    assert "## Auto Writeback: nexus-learn-4" in spec_text
    assert all(item["status"] == "completed" for item in todo["items"])
    assert any(item.get("auto_applied") for item in todo["items"] if item["target"].endswith("INDEX.md"))
