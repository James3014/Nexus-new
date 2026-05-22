from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


SKILL_ROOTS = (
    Path(".agents/skills"),
    Path.home() / ".agents" / "skills",
    Path.home() / ".hermes" / "skills",
)
FORBIDDEN_TOKENS = (
    "eval(",
    "exec(",
    "subprocess",
    "os.system",
    "os.popen",
    "socket.",
    "requests.",
    "httpx.",
    "urllib.",
    "curl ",
    "rm -rf",
)


def resolve_skill_path(skill_id: str, *, roots: tuple[Path, ...] = SKILL_ROOTS) -> Path | None:
    if not skill_id:
        return None
    for root in roots:
        candidate = root / skill_id / "SKILL.md"
        if candidate.exists():
            return candidate
    for root in roots:
        if not root.exists():
            continue
        matches = sorted(root.rglob(f"{skill_id}/SKILL.md"))
        if matches:
            return matches[0]
    return None


def scan_skill_source(skill_id: str, *, skill_path: str | Path | None = None) -> dict[str, Any]:
    resolved = Path(skill_path) if skill_path else resolve_skill_path(skill_id)
    if resolved is None or not resolved.exists():
        return {
            "skill_id": skill_id,
            "status": "BLOCKED_BY_POLICY",
            "failed_security_contract_rules": ["SKILL_SOURCE_NOT_FOUND"],
            "skill_path": "",
            "source_sha256": "",
        }
    source = resolved.read_text(encoding="utf-8", errors="replace")
    lowered = source.lower()
    failed = [
        f"FORBIDDEN_TOKEN:{token.strip()}"
        for token in FORBIDDEN_TOKENS
        if token in lowered
    ]
    return {
        "skill_id": skill_id,
        "status": "PASS" if not failed else "BLOCKED_BY_POLICY",
        "failed_security_contract_rules": failed,
        "skill_path": str(resolved),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_line_count": source.count("\n") + 1,
    }


def build_skill_materialization_command() -> list[str]:
    code = (
        "from pathlib import Path; import hashlib; "
        "p=Path('SKILL.md'); data=p.read_bytes(); "
        "print(hashlib.sha256(data).hexdigest())"
    )
    return ["python3", "-c", code]


def build_skill_command_spec(item: Mapping[str, Any]) -> dict[str, Any]:
    skill_id = str(item.get("skill_id") or "")
    scan = scan_skill_source(skill_id)
    return {
        "capability_id": str(item.get("capability_id") or ""),
        "skill_id": skill_id,
        "priority": str(item.get("priority") or ""),
        "source_review": scan,
        "command": build_skill_materialization_command() if scan["status"] == "PASS" else [],
        "workspace_file": "SKILL.md" if scan["status"] == "PASS" else "",
        "promotion_credit_allowed": scan["status"] == "PASS",
    }
