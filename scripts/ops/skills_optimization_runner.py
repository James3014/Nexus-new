#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False))
        handle.write("\n")


def _optimize_skill_doc(skill_path: Path) -> tuple[bool, str]:
    if not skill_path.exists():
        return False, "skill_not_found"
    content = skill_path.read_text(encoding="utf-8")
    updated = content
    changed = False
    if "## Trigger Precision" not in updated:
        updated += (
            "\n\n## Trigger Precision\n"
            "- Match only when task scope clearly maps to this skill.\n"
            "- Reject ambiguous prompts and request routing fallback.\n"
        )
        changed = True
    if "## Output Contract" not in updated:
        updated += (
            "\n\n## Output Contract\n"
            "- Must return actionable result.\n"
            "- Must include failure reason when no action can be applied.\n"
            "- Must avoid claiming success without verifiable evidence.\n"
        )
        changed = True
    if changed:
        skill_path.write_text(updated, encoding="utf-8")
        return True, "optimized"
    return True, "already_optimized"


def _validate_skill_doc(skill_path: Path) -> tuple[bool, str]:
    if not skill_path.exists():
        return False, "missing_after_optimize"
    content = skill_path.read_text(encoding="utf-8")
    if "## Trigger Precision" not in content:
        return False, "missing_trigger_precision"
    if "## Output Contract" not in content:
        return False, "missing_output_contract"
    return True, "ok"


def run_once(project_root: Path, max_items: int = 3, rebound: float = 0.15) -> int:
    queue_path = project_root / ".nexus" / "metrics" / "skills_optimization_queue.json"
    queue = _load_json(queue_path)
    items = list(queue.get("items", []) or [])
    if not items:
        print("ℹ️ [skills:optimize] queue empty")
        return 0

    weights_path = project_root / "scripts" / "core" / "autonomic_weights.json"
    weights = _load_json(weights_path) or {"skill_adjustments": {}}
    adjustments = dict(weights.get("skill_adjustments", {}) or {})
    run_log_path = project_root / ".nexus" / "metrics" / "skills_optimization_runs.jsonl"

    processed = []
    remaining = []
    for idx, item in enumerate(items):
        if idx >= max_items:
            remaining.append(item)
            continue
        skill_id = str(item.get("skill_id", "")).strip()
        skill_path = Path(item.get("skill_path_builtin", ""))
        before = float(adjustments.get(skill_id, 0.0))
        optimized, optimize_msg = _optimize_skill_doc(skill_path)
        valid, validate_msg = _validate_skill_doc(skill_path)
        success = bool(optimized and valid)
        after = before
        if success:
            after = min(8.0, before + rebound)
            adjustments[skill_id] = after
        processed_row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "skill_id": skill_id,
            "handler_skill": "skill-creator-advanced",
            "optimize_status": optimize_msg,
            "validate_status": validate_msg,
            "success": success,
            "weight_before": round(before, 4),
            "weight_after": round(after, 4),
        }
        _append_jsonl(run_log_path, processed_row)
        processed.append(processed_row)
        if not success:
            remaining.append(item)

    weights["skill_adjustments"] = adjustments
    weights["last_updated"] = datetime.now(timezone.utc).isoformat()
    _write_json(weights_path, weights)

    queue["items"] = remaining
    queue["last_processed_at"] = datetime.now(timezone.utc).isoformat()
    queue["processed_count"] = int(queue.get("processed_count", 0) or 0) + len(processed)
    _write_json(queue_path, queue)

    print(
        f"✅ [skills:optimize] processed={len(processed)} remaining={len(remaining)} "
        f"log={run_log_path}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-consume skills optimization queue.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--max-items", type=int, default=3)
    parser.add_argument("--rebound", type=float, default=0.15)
    args = parser.parse_args()
    return run_once(Path(args.project_root), max_items=int(args.max_items), rebound=float(args.rebound))


if __name__ == "__main__":
    raise SystemExit(main())
