from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple

from scripts.steward import MemorySteward


CommandRunner = Callable[[List[str], Path], Tuple[int, str, str]]
READ_ONLY_COMMANDS = {"nexus:status", "nexus:probe", "nexus:hud", "nexus:spec-lock", "nexus:skills-health"}


@dataclass
class ProtocolGateResult:
    ok: bool
    protocol_path: Path
    ci_mode: str
    ci_summary: str
    ci_exit_code: int
    session_log: Path
    ack_log: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def _load_json(path: Path) -> Dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _append_section_once(path: Path, marker: str, heading: str, body: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing:
        return False
    block = "\n".join(
        [
            "",
            marker,
            heading,
            "",
            body.rstrip(),
            "",
        ]
    )
    path.write_text(existing.rstrip() + block + "\n", encoding="utf-8")
    return True


def _default_command_runner(cmd: List[str], cwd: Path) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def run_protocol_startup_gate(
    project_root: Path | str,
    *,
    command_name: str | None = None,
    command_runner: CommandRunner | None = None,
) -> ProtocolGateResult:
    root = Path(project_root)
    refresh_writeback_status(root, source="startup-gate")
    protocol_path = root / "docs" / "AGENT_MANDATORY_PROTOCOL.md"
    ci_script = root / "scripts" / "ops" / "ci_gate.py"
    ack_log = root / ".nexus" / "events" / "protocol_ack.jsonl"
    session_log = root / ".nexus" / "events" / "session_start.jsonl"
    cache_file = root / ".nexus" / "events" / "latest_protocol_gate.json"
    runner = command_runner or _default_command_runner

    protocol_exists = protocol_path.exists()
    ci_mode = "strict" if ci_script.exists() else "missing"
    cache_ttl_sec = int(os.environ.get("NEXUS_PROTOCOL_GATE_CACHE_TTL_SEC", "900"))
    now_ts = datetime.now(timezone.utc).timestamp()

    cached_payload: Dict[str, Any] | None = None
    if cache_file.exists():
        try:
            cached_payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached_payload = None

    is_read_only = command_name in READ_ONLY_COMMANDS
    if (
        is_read_only
        and cached_payload
        and cached_payload.get("ci_gate_ok") is True
        and (now_ts - float(cached_payload.get("timestamp_epoch", 0))) <= cache_ttl_sec
    ):
        ack_payload = {
            "timestamp_utc": _utc_now(),
            "protocol_path": str(protocol_path),
            "protocol_exists": protocol_exists,
            "ci_gate_mode": "cached-strict",
            "ci_gate_ok": True,
        }
        session_payload = {
            "timestamp_utc": _utc_now(),
            "cwd": str(root),
            "protocol_path": str(protocol_path),
            "protocol_loaded": protocol_exists,
            "ci_gate_mode": "cached-strict",
            "ci_gate_ok": True,
            "ci_gate_exit_code": int(cached_payload.get("ci_gate_exit_code", 0)),
            "ci_gate_summary": str(cached_payload.get("ci_gate_summary", "cached strict pass")),
            "command_name": command_name or "",
        }
        _append_jsonl(ack_log, ack_payload)
        _append_jsonl(session_log, session_payload)
        return ProtocolGateResult(
            ok=protocol_exists,
            protocol_path=protocol_path,
            ci_mode="cached-strict",
            ci_summary=str(cached_payload.get("ci_gate_summary", "cached strict pass")),
            ci_exit_code=int(cached_payload.get("ci_gate_exit_code", 0)),
            session_log=session_log,
            ack_log=ack_log,
        )

    if is_read_only and ci_script.exists():
        ci_mode = "dry-run-readonly"
        exit_code, stdout, stderr = runner(
            [os.environ.get("NEXUS_UV_BIN", "uv"), "run", str(ci_script), "--dry-run"],
            root,
        )
        ci_summary = stdout or stderr or ""
    elif ci_script.exists():
        exit_code, stdout, stderr = runner(
            [os.environ.get("NEXUS_UV_BIN", "uv"), "run", str(ci_script), "--strict"],
            root,
        )
        ci_summary = stdout or stderr or ""
    else:
        exit_code, ci_summary = 0, "ci_gate_missing"

    ack_payload = {
        "timestamp_utc": _utc_now(),
        "protocol_path": str(protocol_path),
        "protocol_exists": protocol_exists,
        "ci_gate_mode": ci_mode,
        "ci_gate_ok": exit_code == 0,
    }
    session_payload = {
        "timestamp_utc": _utc_now(),
        "cwd": str(root),
        "protocol_path": str(protocol_path),
        "protocol_loaded": protocol_exists,
        "ci_gate_mode": ci_mode,
        "ci_gate_ok": exit_code == 0,
        "ci_gate_exit_code": exit_code,
        "ci_gate_summary": ci_summary,
        "command_name": command_name or "",
    }
    _append_jsonl(ack_log, ack_payload)
    _append_jsonl(session_log, session_payload)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "timestamp_epoch": now_ts,
                "ci_gate_mode": ci_mode,
                "ci_gate_ok": exit_code == 0,
                "ci_gate_exit_code": exit_code,
                "ci_gate_summary": ci_summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return ProtocolGateResult(
        ok=protocol_exists and exit_code == 0,
        protocol_path=protocol_path,
        ci_mode=ci_mode,
        ci_summary=ci_summary,
        ci_exit_code=exit_code,
        session_log=session_log,
        ack_log=ack_log,
    )


def _iter_lesson_candidates(state: Any, success: bool) -> Iterable[Dict[str, str]]:
    metadata = getattr(state, "metadata", {}) or {}
    task_desc = metadata.get("task_description", "")
    if metadata.get("cycle_root_cause"):
        yield {
            "reason": str(metadata["cycle_root_cause"]),
            "suggestion": f"Encode repair path and proof discipline for task: {task_desc or state.task_id}",
        }
    if metadata.get("phantom_success_reason"):
        yield {
            "reason": f"phantom_success::{metadata['phantom_success_reason']}",
            "suggestion": "Require proof-present evidence before claiming success.",
        }
    for rejection in metadata.get("rejection_history", []) or []:
        yield {
            "reason": f"rejection::{rejection}",
            "suggestion": "Persist the rejection cause and add a matching repair/write-back action.",
        }
    if not success and not metadata.get("cycle_root_cause") and not metadata.get("rejection_history"):
        yield {
            "reason": f"task_failed::{state.task_id}",
            "suggestion": "Capture root cause and proof gap before next retry.",
        }


def _should_require_writeback(state: Any) -> bool:
    metadata = getattr(state, "metadata", {}) or {}
    markers = (
        "cycle_root_cause",
        "phantom_success_reason",
        "learning_signal_updated",
        "policy_patch_applied",
        "pattern_reuse_rate",
        "next_run_hit_rate",
        "pipeline_terminal_state",
        "rejection_history",
    )
    return any(metadata.get(marker) for marker in markers)


def _build_writeback_items(project_root: Path, state: Any, success: bool) -> List[Dict[str, Any]]:
    metadata = getattr(state, "metadata", {}) or {}
    summary = metadata.get("cycle_root_cause") or metadata.get("phantom_success_reason") or "sync docs after task completion"
    status = "completed" if success else "pending"
    return [
        {
            "target": str(project_root / ".codex_lessons.md"),
            "reason": "human-readable lesson crystallization",
            "status": "completed",
            "completed_at": _utc_now(),
            "completion_source": "continuous-learning",
        },
        {
            "target": str(project_root / "docs" / "INDEX.md"),
            "reason": summary,
            "status": "pending",
        },
        {
            "target": str(project_root / "MUSE_ENGINE_SPEC_V17.1_HARDENED.md"),
            "reason": "phase/learning/governance delta review",
            "status": "pending",
        },
    ]


def _auto_apply_writeback_item(payload: Dict[str, Any], item: Dict[str, Any], source: str) -> bool:
    target = Path(str(item.get("target", "")))
    task_id = str(payload.get("task_id", "unknown"))
    delta_artifacts = payload.get("delta_artifacts", {}) or {}
    delta_key = None
    target_name = target.name
    if target_name == "INDEX.md":
        delta_key = "index_delta"
    elif target_name.startswith("MUSE_ENGINE_SPEC"):
        delta_key = "spec_delta"
    if not delta_key:
        return False

    delta_path_raw = delta_artifacts.get(delta_key)
    if not delta_path_raw:
        return False
    delta_path = Path(str(delta_path_raw))
    if not delta_path.exists():
        return False

    marker = f"<!-- nexus-writeback:{task_id}:{target_name} -->"
    heading = f"## Auto Writeback: {task_id}"
    body = "\n".join(
        [
            f"- Applied at: `{_utc_now()}`",
            f"- Applied by: `{source}`",
            f"- Delta artifact: `{delta_path}`",
            "",
            delta_path.read_text(encoding="utf-8").rstrip(),
        ]
    )
    changed = _append_section_once(target, marker, heading, body)
    if changed:
        item["status"] = "completed"
        item["completed_at"] = _utc_now()
        item["completion_source"] = source
        item["auto_applied"] = True
    return changed


def refresh_writeback_status(
    project_root: Path | str,
    *,
    state: Any | None = None,
    source: str = "auto-refresh",
    auto_apply: bool = True,
) -> Dict[str, Any]:
    root = Path(project_root)
    todo_path = root / ".nexus" / "reports" / "writeback_todo.json"
    payload = _load_json(todo_path)
    if not payload:
        return {
            "writeback_required": False,
            "delivery_status": "fully_delivered",
            "completed": False,
            "todo_path": todo_path,
        }

    items = payload.get("items", []) or []
    changed = False
    todo_mtime = todo_path.stat().st_mtime if todo_path.exists() else 0.0
    previous_status = payload.get("delivery_status") or (
        "code_done_writeback_pending" if payload.get("writeback_required") else "fully_delivered"
    )

    for item in items:
        if item.get("status") == "completed":
            continue
        target = Path(str(item.get("target", "")))
        if auto_apply and _auto_apply_writeback_item(payload, item, source):
            changed = True
            continue
        if target.exists() and target.stat().st_mtime >= todo_mtime:
            item["status"] = "completed"
            item["completed_at"] = _utc_now()
            item["completion_source"] = source
            changed = True

    writeback_required = bool(payload.get("writeback_required"))
    all_completed = all(item.get("status") == "completed" for item in items)
    delivery_status = "fully_delivered" if (not writeback_required or all_completed) else "code_done_writeback_pending"

    payload["items"] = items
    payload["delivery_status"] = delivery_status
    if changed or payload.get("delivery_status") != previous_status:
        todo_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = getattr(state, "metadata", None)
    if isinstance(metadata, dict):
        metadata["writeback_items"] = items
        metadata["delivery_status"] = delivery_status
        metadata["writeback_required"] = writeback_required
        metadata["writeback_todo_path"] = str(todo_path)

    event = {
        "timestamp_utc": _utc_now(),
        "task_id": payload.get("task_id", "unknown"),
        "source": source,
        "delivery_status": delivery_status,
        "writeback_required": writeback_required,
        "items_completed": sum(1 for item in items if item.get("status") == "completed"),
        "items_total": len(items),
    }
    if changed or delivery_status != previous_status:
        _append_jsonl(root / ".nexus" / "events" / "writeback_completion.jsonl", event)

    return {
        "writeback_required": writeback_required,
        "delivery_status": delivery_status,
        "completed": all_completed,
        "items": items,
        "todo_path": todo_path,
    }


def _write_delta_artifacts(project_root: Path, state: Any, success: bool, source: str) -> Dict[str, Path]:
    metadata = getattr(state, "metadata", {}) or {}
    auto_dir = project_root / ".nexus" / "reports" / "writeback"
    auto_dir.mkdir(parents=True, exist_ok=True)
    task_id = getattr(state, "task_id", "unknown")
    root_cause = metadata.get("cycle_root_cause") or metadata.get("phantom_success_reason") or "n/a"
    rejection_lines = metadata.get("rejection_history", []) or []

    index_delta = auto_dir / f"{task_id}_INDEX.delta.md"
    spec_delta = auto_dir / f"{task_id}_SPEC.delta.md"

    index_delta.write_text(
        "\n".join(
            [
                f"# INDEX Delta: {task_id}",
                "",
                f"- Source: `{source}`",
                f"- Success: `{success}`",
                f"- Root Cause: {root_cause}",
                f"- Pending Writeback: `{_should_require_writeback(state)}`",
                "",
                "## Rejection History",
                *([f"- {line}" for line in rejection_lines] or ["- none"]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    spec_delta.write_text(
        "\n".join(
            [
                f"# SPEC Delta: {task_id}",
                "",
                "## Suggested Updates",
                f"- Reflect learning loop outcome from `{source}`.",
                f"- Document root cause: {root_cause}",
                "- Review protocol/startup gate expectations if this task changed delivery behavior.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"index_delta": index_delta, "spec_delta": spec_delta}


def finalize_learning_loop(
    project_root: Path | str,
    state: Any,
    *,
    success: bool,
    source: str,
) -> Dict[str, Any]:
    root = Path(project_root)
    steward = MemorySteward(root)
    violations = list(_iter_lesson_candidates(state, success))
    lessons_written = bool(violations) and bool(steward.crystallize(violations))
    delta_paths = _write_delta_artifacts(root, state, success, source)

    writeback_required = _should_require_writeback(state)
    items = _build_writeback_items(root, state, success)
    if not writeback_required:
        for item in items:
            item["status"] = "completed"
    todo_payload = {
        "timestamp_utc": _utc_now(),
        "task_id": getattr(state, "task_id", "unknown"),
        "success": success,
        "source": source,
        "writeback_required": writeback_required,
        "items": items,
        "delta_artifacts": {key: str(value) for key, value in delta_paths.items()},
    }
    todo_path = root / ".nexus" / "reports" / "writeback_todo.json"
    todo_path.parent.mkdir(parents=True, exist_ok=True)
    todo_path.write_text(json.dumps(todo_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    refreshed = refresh_writeback_status(
        root,
        state=state,
        source="continuous-learning-finalize",
        auto_apply=False,
    )
    delivery_status = refreshed["delivery_status"]
    metadata = getattr(state, "metadata", None)
    if isinstance(metadata, dict):
        metadata["lessons_written"] = lessons_written
        metadata["writeback_required"] = writeback_required
        metadata["writeback_todo_path"] = str(todo_path)
        metadata["writeback_items"] = items
        metadata["writeback_delta_artifacts"] = {key: str(value) for key, value in delta_paths.items()}
        metadata["delivery_status"] = delivery_status

    loop_event = {
        "timestamp_utc": _utc_now(),
        "task_id": getattr(state, "task_id", "unknown"),
        "success": success,
        "source": source,
        "lessons_written": lessons_written,
        "writeback_required": writeback_required,
        "writeback_todo_path": str(todo_path),
        "delivery_status": delivery_status,
    }
    _append_jsonl(root / ".nexus" / "events" / "learning_loop.jsonl", loop_event)
    return {
        "lessons_written": lessons_written,
        "writeback_required": writeback_required,
        "writeback_todo_path": todo_path,
        "delivery_status": delivery_status,
        "delta_artifacts": delta_paths,
    }
