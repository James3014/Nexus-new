#!/usr/bin/env python3
"""Verify the machine-local Skill overlay without mutating either tree."""

from __future__ import annotations

import json
from pathlib import Path


SKILL_ROOT = Path("/Users/jameschen/.agents/skills")
SKILLS = (
    "nexus-current-state-audit",
    "nexus-mcp-access-audit",
    "nexus-mcp-task-executor",
    "nexus-candidate-acceptance-audit",
    "nexus-model-task-compiler",
    "nexus-model-onboarding-calibration",
    "nexus-handoff",
)
REQUIRED = (
    "task_id",
    "attempt_id",
    "action_id",
    "idempotency_key",
    "tool_manifest_hash",
    "full_tool_schema_hash",
    "permission_policy_hash",
    "lifecycle_revision",
    "server_instance_id",
    "UNKNOWN_REQUIRES_RECONCILE",
    "uncertain_mutation",
    "next_action",
    "recommended_tool",
)


def verify() -> dict[str, object]:
    failures: list[str] = []
    details: list[dict[str, object]] = []
    for skill in SKILLS:
        path = SKILL_ROOT / skill / "SKILL.md"
        if not path.is_file():
            failures.append(f"missing:{path}")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [token for token in REQUIRED if token not in text]
        marker_count = text.count("## Lifecycle V1 contract overlay")
        if missing:
            failures.append(f"missing_tokens:{skill}:{','.join(missing)}")
        if marker_count != 1:
            failures.append(f"overlay_marker_count:{skill}:{marker_count}")
        if "nexus-lifecycle-controller" in text:
            failures.append(f"forbidden_second_controller:{skill}")
        details.append({"skill": skill, "path": str(path), "bytes": len(text.encode("utf-8")), "missing": missing, "overlay_marker_count": marker_count})
    return {"schema": "nexus.agent_skill_lifecycle_overlay.v1", "repository_mutation": False, "skill_count": len(SKILLS), "details": details, "failures": failures, "gate_passed": not failures}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["gate_passed"] else 1)
