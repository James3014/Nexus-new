import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# --- P1-C: Structured Lesson Schema ---
LESSON_SCHEMA_VERSION = "lesson_event.v1"


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _norm_text(value: Optional[str]) -> str:
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value


def _norm_list(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    seen = set()
    out = []
    for v in values:
        item = _norm_text(v)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


@dataclass
class LessonEvent:
    lesson_id: str
    task_id: str
    trace_id: Optional[str]
    decision_id: Optional[str]
    timestamp_utc: str
    source_phase: str
    category: str
    root_cause: str
    evidence: List[str] = field(default_factory=list)
    corrective_action: str = ""
    reusable_when: List[str] = field(default_factory=list)
    do_not_apply_when: List[str] = field(default_factory=list)
    outcome: str = "success"
    confidence: float = 0.7
    patch_hash: Optional[str] = None
    artifact_refs: List[str] = field(default_factory=list)
    schema_version: str = LESSON_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["evidence"] = _norm_list(data.get("evidence"))
        data["reusable_when"] = _norm_list(data.get("reusable_when"))
        data["do_not_apply_when"] = _norm_list(data.get("do_not_apply_when"))
        data["root_cause"] = _norm_text(data.get("root_cause"))
        data["corrective_action"] = _norm_text(data.get("corrective_action"))
        data["category"] = _norm_text(data.get("category")) or "UNKNOWN"
        data["source_phase"] = _norm_text(data.get("source_phase")) or "C"
        data["outcome"] = _norm_text(data.get("outcome")) or "success"
        data["task_id"] = _norm_text(data.get("task_id"))
        return data


# --- P1-C: Persistence & Sync Helpers ---


def compute_lesson_id(
    task_id: str,
    root_cause: str,
    corrective_action: str,
    patch_hash: Optional[str] = None,
) -> str:
    payload = {
        "task_id": _norm_text(task_id),
        "root_cause": _norm_text(root_cause).lower(),
        "corrective_action": _norm_text(corrective_action).lower(),
        "patch_hash": _norm_text(patch_hash or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    except Exception:
        return []
    return rows


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + "\n"
    )
    path.write_text(content, encoding="utf-8")


def upsert_lesson_event(jsonl_path: Path, event: LessonEvent) -> bool:
    rows = load_jsonl(jsonl_path)
    payload = event.to_dict()
    payload["lesson_id"] = event.lesson_id

    replaced = False
    new_rows = []
    for row in rows:
        if row.get("lesson_id") == event.lesson_id:
            new_rows.append(payload)
            replaced = True
        else:
            new_rows.append(row)

    if not replaced:
        new_rows.append(payload)

    write_jsonl(jsonl_path, new_rows)
    return not replaced


def render_human_lesson_block(event: LessonEvent) -> str:
    data = event.to_dict()
    lines = [
        f"### Lesson {data['task_id']}",
        f"- **Category**: {data['category']}",
        f"- **Root cause**: {data['root_cause']}",
        f"- **Corrective action**: {data['corrective_action']}",
        f"- **Outcome**: {data['outcome']}",
    ]
    if data["reusable_when"]:
        lines.append(f"- **Reusable when**: {', '.join(data['reusable_when'])}")
    if data["do_not_apply_when"]:
        lines.append(f"- **Do not apply when**: {', '.join(data['do_not_apply_when'])}")
    if data["evidence"]:
        lines.append(f"- **Evidence**: {', '.join(data['evidence'])}")
    lines.append(f"- **Lesson ID**: `{event.lesson_id}`")
    return "\n".join(lines).strip() + "\n"


def sync_markdown_lesson_index(md_path: Path, event: LessonEvent) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    block = render_human_lesson_block(event)

    if not md_path.exists():
        md_path.write_text("# 🧬 Project Evolution Lessons\n\n" + block, encoding="utf-8")
        return

    doc = md_path.read_text(encoding="utf-8")
    marker = f"### Lesson {event.task_id}"
    if marker in doc:
        # Replace the entire block for this task_id to avoid duplication
        pattern = rf"### Lesson {re.escape(event.task_id)}\n(?:.*?)(?=\n### Lesson |\Z)"
        doc = re.sub(pattern, block.rstrip(), doc, flags=re.S)
    else:
        if not doc.endswith("\n"):
            doc += "\n"
        doc += "\n" + block

    md_path.write_text(doc, encoding="utf-8")


def build_structured_lesson(
    *,
    task_id: str,
    raw_lesson: str,
    category: Optional[str] = None,
    root_cause: Optional[str] = None,
    evidence: Optional[List[str]] = None,
    corrective_action: Optional[str] = None,
    reusable_when: Optional[List[str]] = None,
    do_not_apply_when: Optional[List[str]] = None,
    source_phase: str = "C",
    trace_id: Optional[str] = None,
    decision_id: Optional[str] = None,
    outcome: str = "success",
    confidence: float = 0.7,
    patch_hash: Optional[str] = None,
    artifact_refs: Optional[List[str]] = None,
) -> LessonEvent:
    lesson_text = _norm_text(raw_lesson)

    # Heuristic parsing if specific fields not provided
    guessed_root = (
        root_cause or (lesson_text.split(". ")[0].strip() if lesson_text else "Unknown")
    )
    guessed_action = corrective_action or (
        (lesson_text.split(". ", 1)[1].strip() if ". " in lesson_text else lesson_text)
    )

    event = LessonEvent(
        lesson_id="",
        task_id=task_id,
        trace_id=trace_id,
        decision_id=decision_id,
        timestamp_utc=utc_now_iso(),
        source_phase=source_phase,
        category=(category or "UNKNOWN"),
        root_cause=guessed_root,
        evidence=evidence or [],
        corrective_action=guessed_action,
        reusable_when=reusable_when or [],
        do_not_apply_when=do_not_apply_when or [],
        outcome=outcome,
        confidence=confidence,
        patch_hash=patch_hash,
        artifact_refs=artifact_refs or [],
    )
    normalized = event.to_dict()
    event.lesson_id = compute_lesson_id(
        task_id=normalized["task_id"],
        root_cause=normalized["root_cause"],
        corrective_action=normalized["corrective_action"],
        patch_hash=normalized.get("patch_hash"),
    )
    return event


def persist_structured_lesson(
    *,
    repo_root: Path,
    task_id: str,
    raw_lesson: str,
    **kwargs,
) -> LessonEvent:
    event = build_structured_lesson(task_id=task_id, raw_lesson=raw_lesson, **kwargs)

    repo_root = Path(repo_root)
    lesson_jsonl = repo_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
    codex_md = repo_root / ".codex_lessons.md"  # Sync to main lessons file

    upsert_lesson_event(lesson_jsonl, event)
    sync_markdown_lesson_index(codex_md, event)
    return event


# --- Original Imports & Setup ---


@dataclass
class TargetVerification:
    target_file: str
    anchor_id: str
    task_id: str
    marker_found: bool = False
    anchor_found: bool = False
    anchor_unique: bool = False
    block_count: int = 0
    is_most_recent: bool = False
    content_hash_expected: Optional[str] = None
    content_hash_actual: Optional[str] = None
    reasons: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    final_status: str
    fail_code: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    verified_targets: List[TargetVerification] = field(default_factory=list)
    event_payload: Dict[str, Any] = field(default_factory=dict)


FAIL_CODES = {
    "TODO_MISSING": "WB_TODO_MISSING",
    "TARGET_MISSING": "WB_TARGET_MISSING",
    "ANCHOR_DUPLICATE": "WB_ANCHOR_DUPLICATE",
    "ANCHOR_NOT_FOUND": "WB_ANCHOR_NOT_FOUND",
    "MARKER_MISSING": "WB_MARKER_MISSING",
    "TASK_BLOCK_MISSING": "WB_TASK_BLOCK_MISSING",
    "TASK_BLOCK_DUPLICATE": "WB_TASK_BLOCK_DUPLICATE",
    "CONTENT_MISMATCH": "WB_CONTENT_MISMATCH",
    "SORT_VIOLATION": "WB_SORT_VIOLATION",
    "NOT_READY": "WB_NOT_READY",
}

from nexus.core.steward import MemorySteward


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
    
    def _rel(target_path: Path) -> str:
        try:
            return str(target_path.relative_to(project_root))
        except ValueError:
            return str(target_path)

    return [
        {
            "target": _rel(project_root / ".codex_lessons.md"),
            "reason": "human-readable lesson crystallization",
            "status": "completed",
            "completed_at": _utc_now(),
            "completion_source": "continuous-learning",
        },
        {
            "target": _rel(project_root / "docs" / "INDEX.md"),
            "reason": summary,
            "status": "pending",
        },
        {
            "target": _rel(project_root / "MUSE_ENGINE_SPEC_V17.1_HARDENED.md"),
            "reason": "phase/learning/governance delta review",
            "status": "pending",
        },
    ]


def _apply_semantic_patch(path: Path, category: str, task_id: str, heading: str, body: str) -> bool:
    import re
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    
    # 🛡️ Category Anchor Defs
    start_anchor = f"<!-- nexus-anchor:{category} -->"
    end_anchor = f"<!-- /nexus-anchor:{category} -->"
    
    # 🛡️ Task Marker Defs
    task_start = f"<!-- nexus-writeback:{task_id} -->"
    task_end = f"<!-- /nexus-writeback:{task_id} -->"
    new_task_block = f"\n{task_start}\n{heading}\n\n{body}\n{task_end}\n"

    # Step 1: Ensure Category Anchor exists
    if start_anchor not in content or end_anchor not in content:
        # Dual-track: Look for legacy footer or just append
        full_anchor_block = f"\n\n## Auto Writeback: {category}\n{start_anchor}\n{end_anchor}\n"
        if "%% " in content: # Insert before footer
            parts = content.split("%%", 1)
            content = parts[0].rstrip() + full_anchor_block + "%%" + parts[1]
        else:
            content = content.rstrip() + full_anchor_block
    
    # Step 2: Extract Category segment
    pattern = re.escape(start_anchor) + "(.*?)" + re.escape(end_anchor)
    match = re.search(pattern, content, re.DOTALL)
    if not match: return False # Should not happen after Step 1
    
    segment = match.group(1)
    
    # Step 3: Check for Task-ID replacement
    task_pattern = re.escape(task_start) + ".*?" + re.escape(task_end)
    if re.search(task_pattern, segment, re.DOTALL):
        # REPLACE existing task block
        new_segment = re.sub(task_pattern, new_task_block.strip() + "\n", segment, flags=re.DOTALL)
    else:
        # PREPEND (Most Recent First)
        new_segment = "\n" + new_task_block.strip() + "\n" + segment.lstrip()

    # Step 4: Re-stitch document
    final_content = content[:match.start(1)] + new_segment + content[match.end(1):]
    path.write_text(final_content, encoding="utf-8")
    return True


def _auto_apply_writeback_item(root: Path, payload: Dict[str, Any], item: Dict[str, Any], source: str) -> bool:
    target_raw = item.get("target", "")
    target = Path(target_raw)
    if not target.is_absolute():
        target = root / target
        
    task_id = str(payload.get("task_id", "unknown"))
    delta_artifacts = payload.get("delta_artifacts", {}) or {}
    delta_key = None
    target_name = target.name
    category = "learning-trace"
    if target_name == "INDEX.md":
        delta_key = "index_delta"
        category = "evolution"
    elif target_name.startswith("MUSE_ENGINE_SPEC"):
        delta_key = "spec_delta"
        category = "governance-hardening"
    if not delta_key:
        return False

    delta_path_raw = delta_artifacts.get(delta_key)
    if not delta_path_raw:
        return False
    delta_path = Path(str(delta_path_raw))
    if not delta_path.is_absolute():
        delta_path = root / delta_path
        
    if not delta_path.exists():
        return False

    heading = f"### Auto Writeback: {task_id}"
    body = "\n".join(
        [
            f"- Applied at: `{_utc_now()}`",
            f"- Applied by: `{source}`",
            f"- Delta artifact: `{delta_path}`",
            "",
            delta_path.read_text(encoding="utf-8").rstrip(),
        ]
    )
    
    changed = _apply_semantic_patch(target, category, task_id, heading, body)
    if changed:
        # Pre-calculate expectation for the validator
        item["status"] = "completed"
        item["completed_at"] = _utc_now()
        item["completion_source"] = source
        item["auto_applied"] = True
        
        # 🛡️ Capture the exact truth block as defined in _apply_semantic_patch
        task_start = f"<!-- nexus-writeback:{task_id} -->"
        task_end = f"<!-- /nexus-writeback:{task_id} -->"
        # Match the logic in _apply_semantic_patch exactly
        rendered_block = f"{task_start}\n{heading}\n\n{body}\n{task_end}"
        item["expected_hash"] = hashlib.sha256(rendered_block.encode("utf-8")).hexdigest()
        item["anchor_id"] = category
        
    return changed


def _normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").strip()
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def validate_writeback_completion(
    task_id: str,
    todo_path: Path,
    repo_root: Path,
) -> ValidationResult:
    if not todo_path.exists():
        return ValidationResult(ok=False, final_status="code_done_writeback_pending", fail_code=FAIL_CODES["TODO_MISSING"], reasons=["todo missing"])
    
    payload = json.loads(todo_path.read_text(encoding="utf-8"))
    items = payload.get("items", []) or []
    
    verified_targets = []
    reasons = []
    fail_code = None
    all_ok = True if items else False
    
    for item in items:
        target_raw = item.get("target", "")
        status = item.get("status", "pending")
        
        # 🛡️ P1-B: Any non-completed item blocks promotion
        if status != "completed":
            reasons.append(f"{target_raw}: pending")
            fail_code = fail_code or FAIL_CODES["NOT_READY"]
            all_ok = False
            continue

        anchor_id = item.get("anchor_id") # P1-B: Only anchored files are semantically validated
        expected_hash = item.get("expected_hash")
        
        # 🛡️ Skip semantic validation if no anchor is defined (e.g. .codex_lessons.md)
        if not anchor_id:
            tv = TargetVerification(target_file=str(target_raw), anchor_id="", task_id=task_id, is_most_recent=True)
            verified_targets.append(tv)
            continue

        # Handle both absolute and relative targets correctly
        target = Path(target_raw)
        if not target.is_absolute():
            target = repo_root / target
        
        tv = TargetVerification(target_file=str(target_raw), anchor_id=anchor_id, task_id=task_id, content_hash_expected=expected_hash)
        
        if not target.exists():
            tv.reasons.append("target missing")
            verified_targets.append(tv)
            reasons.append(f"{target_raw}: missing")
            fail_code = fail_code or FAIL_CODES["TARGET_MISSING"]
            all_ok = False
            continue
            
        doc = target.read_text(encoding="utf-8")
        start_anchor = f"<!-- nexus-anchor:{anchor_id} -->"
        end_anchor = f"<!-- /nexus-anchor:{anchor_id} -->"
        anchor_hits = [m.start() for m in re.finditer(re.escape(start_anchor), doc)]
        
        tv.anchor_found = len(anchor_hits) > 0
        tv.anchor_unique = len(anchor_hits) == 1
        
        if not tv.anchor_found:
            tv.reasons.append("anchor not found")
            verified_targets.append(tv)
            reasons.append(f"{target_raw}: anchor {anchor_id} missing")
            fail_code = fail_code or FAIL_CODES["ANCHOR_NOT_FOUND"]
            all_ok = False
            continue
            
        if not tv.anchor_unique:
            tv.reasons.append("duplicate anchor")
            verified_targets.append(tv)
            reasons.append(f"{target_raw}: duplicate anchor {anchor_id}")
            fail_code = fail_code or FAIL_CODES["ANCHOR_DUPLICATE"]
            all_ok = False
            continue

        # Extract Region
        pattern = re.escape(start_anchor) + "(.*?)" + re.escape(end_anchor)
        match = re.search(pattern, doc, re.DOTALL)
        if not match:
            tv.reasons.append("anchor slice failed")
            verified_targets.append(tv)
            all_ok = False
            continue
            
        region = match.group(1)
        tv.marker_found = "Auto Writeback" in region
        
        # Extract Task Block
        task_start = f"<!-- nexus-writeback:{task_id} -->"
        task_end = f"<!-- /nexus-writeback:{task_id} -->"
        task_pattern = re.escape(task_start) + "(.*?)" + re.escape(task_end)
        task_hits = list(re.finditer(task_pattern, region, re.DOTALL))
        tv.block_count = len(task_hits)
        
        if tv.block_count == 0:
            tv.reasons.append("task block missing")
            verified_targets.append(tv)
            reasons.append(f"{target_raw}: block {task_id} missing")
            fail_code = fail_code or FAIL_CODES["TASK_BLOCK_MISSING"]
            all_ok = False
            continue
            
        if tv.block_count > 1:
            tv.reasons.append("duplicate task block")
            verified_targets.append(tv)
            reasons.append(f"{target_raw}: duplicate block {task_id}")
            fail_code = fail_code or FAIL_CODES["TASK_BLOCK_DUPLICATE"]
            all_ok = False
            continue
            
        # Hash Check
        actual_block = task_hits[0].group(0)
        actual_hash_raw = hashlib.sha256(actual_block.encode("utf-8")).hexdigest()
        
        if expected_hash and actual_hash_raw != expected_hash:
            # 🛡️ Fallback: If raw match fails, try normalized match to account for minor whitespace jitter
            actual_hash_norm = hashlib.sha256(_normalize_markdown(actual_block).encode("utf-8")).hexdigest()
            if actual_hash_norm != expected_hash:
                tv.reasons.append(f"content mismatch (raw:{actual_hash_raw[:8]} expected:{expected_hash[:8]})")
                verified_targets.append(tv)
                reasons.append(f"{target_raw}: hash mismatch")
                fail_code = fail_code or FAIL_CODES["CONTENT_MISMATCH"]
                all_ok = False
                continue
        
        # Sort Check (Simple: is it first in region?)
        all_blocks = list(re.finditer(r"<!-- nexus-writeback:.*? -->", region))
        if all_blocks and task_start not in all_blocks[0].group(0):
            tv.reasons.append("sort violation")
            verified_targets.append(tv)
            reasons.append(f"{target_raw}: not most recent")
            fail_code = fail_code or FAIL_CODES["SORT_VIOLATION"]
            all_ok = False
            continue
            
        tv.is_most_recent = True
        verified_targets.append(tv)

    return ValidationResult(
        ok=all_ok,
        final_status="fully_delivered" if all_ok else "code_done_writeback_pending",
        fail_code=None if all_ok else (fail_code or FAIL_CODES["NOT_READY"]),
        reasons=reasons,
        verified_targets=verified_targets,
        event_payload={
            "task_id": task_id,
            "status": "pass" if all_ok else "fail",
            "fail_code": fail_code,
            "targets_count": len(verified_targets)
        }
    )


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

    task_id = payload.get("task_id", "unknown")
    items = payload.get("items", []) or []
    changed = False
    previous_status = payload.get("delivery_status") or "code_done_writeback_pending"

    # Step 1: Attempt auto-apply for pending items
    for item in items:
        if item.get("status") == "completed":
            continue
        if auto_apply and _auto_apply_writeback_item(root, payload, item, source):
            changed = True

    # Step 1.5: Flush to disk before validation (read-after-write consistency)
    if changed:
        payload["items"] = items
        todo_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 2: Semantic Validation Gate (P1-B Heart)
    val_result = validate_writeback_completion(task_id, todo_path, root)
    
    # Step 3: Record Validation Event
    _append_jsonl(root / ".nexus" / "events" / "writeback_validation.jsonl", val_result.event_payload)

    writeback_required = bool(payload.get("writeback_required"))
    delivery_status = val_result.final_status if writeback_required else "fully_delivered"

    payload["items"] = items
    payload["delivery_status"] = delivery_status
    if changed or delivery_status != previous_status:
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
        "completed": val_result.ok if writeback_required else True,
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

    # --- P1-C: Structured Lesson Persistence ---
    if lessons_written:
        task_id = getattr(state, "task_id", "unknown")
        for v in violations:
            persist_structured_lesson(
                repo_root=root,
                task_id=task_id,
                raw_lesson=v.get("reason", "Unknown Issue"),
                category=v.get("category", "UNKNOWN"),
                root_cause=v.get("reason", "Unknown Issue"),
                corrective_action=v.get("suggestion", "N/A"),
                artifact_refs=[
                    ".nexus/reports/acceptancecheck.json",
                    ".nexus/reports/auditresult.json",
                ],
            )
        
        # 🚀 F4: Automate Vector Indexing (P2-A)
        try:
            from nexus.services.memory_indexer import rebuild_memory_index
            rebuild_memory_index(root)
            logging.info(f"💎 [LearningLoop] Memory index rebuilt for task {task_id}")
        except Exception as e:
            logging.warning(f"⚠️ [LearningLoop] Vector indexing failed: {e}")
    # --------------------------------------------

    # 🧬 [Phase 13] Skill Win Rate 回寫 (經驗沉澱)
    try:
        from nexus.learning.skill_lifecycle import record_usage
        from nexus.learning.skill_registry import SkillRegistry

        skill_id = getattr(state, "task_id", "unknown")
        skills_dir = root / "skills" / "learned"
        outcome = "success" if success else "failure"

        # 1. 記錄使用事件
        if skills_dir.exists() and skill_id != "unknown":
            record_usage(skills_dir, skill_id, skill_id, outcome)

        # 2. 重新計算 win_rate 並回寫 Registry
        registry_path = root / ".nexus" / "registry" / "shared_skills.db"
        if registry_path.exists() and skill_id != "unknown":
            registry = SkillRegistry(registry_path)
            existing = registry.get_by_task_id(skill_id)
            if existing:
                # Assuming repair_success acts as absolute success count and retry_count as failures/retries
                total_uses = existing.get("repair_success", 0) + existing.get("retry_count", 0)
                successes = existing.get("repair_success", 0)
                if success:
                    successes += 1
                total_uses += 1
                win_rate = float(successes) / total_uses if total_uses > 0 else 0.0
                registry.update_win_rate(skill_id, win_rate)
    except Exception as e:
        logging.warning(f"⚠️ [Phase13] Skill win_rate writeback failed: {e}")

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
    # 🚀 [v0.2/v0.3] Soul-Palace Belief Revision Linkage
    try:
        from nexus.services.mem_palace import MemPalace
        from scripts.ops.brain_loop_closure import BrainLoopClosure
        
        if not success:
            palace = MemPalace(str(root))
            loop = BrainLoopClosure(root)
            
            # 1. 動態鎖定當前任務相關的信念 (S5 Hardening)
            active_beliefs = palace.list_beliefs(status="ACTIVE")
            task_id = getattr(state, "task_id", "unknown")
            
            # 尋找映射：這可能是由當前任務建立的信念，或內容包含任務 ID 的信念
            to_revise = []
            for b in active_beliefs:
                b_id = b.get("id")
                b_content = str(b.get("content", ""))
                
                # 判定邏輯：精確匹配 ID 或 模糊匹配內容 (Actual Schema: ['id', 'content', ...])
                if b_id == task_id or task_id in b_content:
                    to_revise.append(b_id)
            
            # 2. 執行修訂傳播
            for b_id in to_revise:
                loop.propagate_belief_revision(b_id, "superseded")
                logging.info(f"🧠 [SoulPalace:C] Dynamic belief revision triggered: {b_id} -> superseded")
                
            if not to_revise:
                logging.debug(f"🧠 [SoulPalace:C] No active beliefs found correlating with failed task {task_id}")
    except Exception as e:
        logging.warning(f"⚠️ [SoulPalace:C] Dynamic belief revision failed: {e}")

    return {
        "lessons_written": lessons_written,
        "writeback_required": writeback_required,
        "writeback_todo_path": todo_path,
        "delivery_status": delivery_status,
        "delta_artifacts": delta_paths,
    }
