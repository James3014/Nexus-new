"""Skill lifecycle management: trust levels, usage tracking, promotion, archival.

Implements the skill supply chain inspired by skill-creator-advanced's
lifecycle model (Phase -1 to Phase 8) and regression gates pattern.

Trust Levels:
    L0: auto-generated  — Pipeline C Phase auto-output, unverified
    L1: reviewed         — Human-approved via `nexus:skills-learned approve`
    L2: tested           — Successfully reused ≥1 time + scan passed
    L3: production       — Successfully reused ≥3 times + scan passed
"""

import json
import re
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from nexus.learning.skill_scanner import scan_skill


TRUST_LEVELS = ["auto-generated", "reviewed", "tested", "production"]
USAGE_LOG_FILENAME = ".usage_log.jsonl"


@dataclass
class UsageEvent:
    skill_id: str
    used_at: str
    task_id: str
    outcome: str  # "success" or "failure"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "used_at": self.used_at,
            "task_id": self.task_id,
            "outcome": self.outcome,
        }


def record_usage(skills_dir: Path, skill_id: str, task_id: str, outcome: str = "success") -> None:
    """Append a usage event to the JSONL log."""
    log_path = skills_dir / USAGE_LOG_FILENAME
    event = UsageEvent(
        skill_id=skill_id,
        used_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        task_id=task_id,
        outcome=outcome,
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def count_successful_uses(skills_dir: Path, skill_id: str) -> int:
    """Count successful usage events for a given skill."""
    log_path = skills_dir / USAGE_LOG_FILENAME
    if not log_path.exists():
        return 0
    count = 0
    for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("skill_id") == skill_id and entry.get("outcome") == "success":
                count += 1
        except json.JSONDecodeError:
            continue
    return count


def promote_skill(skills_dir: Path, skill_id: str, target_level: str) -> Dict[str, Any]:
    """Promote a skill to the target trust level.

    Returns a result dict with success status and message.
    Enforces sequential promotion (no skipping levels).
    """
    filename = f"{skill_id}.md" if not skill_id.endswith(".md") else skill_id
    skill_path = skills_dir / filename
    if not skill_path.exists():
        return {"success": False, "message": f"技能不存在: {skill_id}"}

    if target_level not in TRUST_LEVELS:
        return {"success": False, "message": f"無效的信任等級: {target_level}"}

    content = skill_path.read_text(encoding="utf-8")

    # Extract current trust level from frontmatter
    current_level = "auto-generated"
    trust_match = re.search(r"trust_level:\s*(.+)", content)
    if trust_match:
        current_level = trust_match.group(1).strip().strip('"').strip("'")

    current_idx = TRUST_LEVELS.index(current_level) if current_level in TRUST_LEVELS else 0
    target_idx = TRUST_LEVELS.index(target_level)

    if target_idx <= current_idx:
        return {"success": False, "message": f"目標等級 ({target_level}) 必須高於當前等級 ({current_level})"}

    if target_idx != current_idx + 1:
        return {"success": False, "message": f"只能逐級升級: {current_level} → {TRUST_LEVELS[current_idx + 1]}"}

    # Security scan for tested/production promotion
    if target_level in ("tested", "production"):
        scan_result = scan_skill(content)
        if not scan_result.safe:
            return {
                "success": False,
                "message": f"安全掃描未通過，無法晉升: {scan_result.blocked_reasons}",
            }
        # Check usage count for tested/production
        usage_count = count_successful_uses(skills_dir, skill_id)
        required_uses = 1 if target_level == "tested" else 3
        if usage_count < required_uses:
            return {
                "success": False,
                "message": f"使用次數不足: 需要 {required_uses} 次成功使用，目前 {usage_count} 次",
            }

    # Perform promotion: update trust_level in frontmatter
    if trust_match:
        new_content = content.replace(
            trust_match.group(0),
            f"trust_level: {target_level}",
        )
    else:
        # Insert trust_level after the first ---
        new_content = content.replace("---\n", f"---\ntrust_level: {target_level}\n", 1)

    skill_path.write_text(new_content, encoding="utf-8")
    return {
        "success": True,
        "message": f"✅ 技能 {skill_id} 已從 {current_level} 升級到 {target_level}",
    }


def archive_skill(skills_dir: Path, skill_id: str) -> Dict[str, Any]:
    """Archive a skill by moving it to skills/archived/."""
    filename = f"{skill_id}.md" if not skill_id.endswith(".md") else skill_id
    skill_path = skills_dir / filename
    if not skill_path.exists():
        return {"success": False, "message": f"技能不存在: {skill_id}"}

    archived_dir = skills_dir.parent / "archived"
    archived_dir.mkdir(parents=True, exist_ok=True)
    dest = archived_dir / filename
    shutil.move(str(skill_path), str(dest))
    return {
        "success": True,
        "message": f"📦 技能 {skill_id} 已歸檔到 skills/archived/",
    }


def auto_promote_all(skills_dir: Path) -> List[Dict[str, Any]]:
    """Check all skills and auto-promote those meeting criteria."""
    results = []
    for skill_file in sorted(skills_dir.glob("*.md")):
        skill_id = skill_file.stem
        content = skill_file.read_text(encoding="utf-8")

        # Extract current trust level
        current_level = "auto-generated"
        trust_match = re.search(r"trust_level:\s*(.+)", content)
        if trust_match:
            current_level = trust_match.group(1).strip().strip('"').strip("'")

        current_idx = TRUST_LEVELS.index(current_level) if current_level in TRUST_LEVELS else 0
        if current_idx >= len(TRUST_LEVELS) - 1:
            continue  # Already at max level

        next_level = TRUST_LEVELS[current_idx + 1]

        # Skip auto-generated -> reviewed (requires human approval)
        if current_level == "auto-generated":
            continue

        usage_count = count_successful_uses(skills_dir, skill_id)
        scan_result = scan_skill(content)

        if next_level == "tested" and usage_count >= 1 and scan_result.safe:
            result = promote_skill(skills_dir, skill_id, "tested")
            results.append(result)
        elif next_level == "production" and usage_count >= 3 and scan_result.safe:
            result = promote_skill(skills_dir, skill_id, "production")
            results.append(result)

    return results


def get_skills_stats(skills_dir: Path) -> Dict[str, Any]:
    """Generate a health report of all learned skills."""
    stats: Dict[str, Any] = {
        "total": 0,
        "by_level": {},
        "scan_results": {"safe": 0, "unsafe": 0},
        "total_uses": 0,
    }

    for level in TRUST_LEVELS:
        stats["by_level"][level] = 0

    for skill_file in sorted(skills_dir.glob("*.md")):
        stats["total"] += 1
        content = skill_file.read_text(encoding="utf-8")

        # Trust level
        current_level = "auto-generated"
        trust_match = re.search(r"trust_level:\s*(.+)", content)
        if trust_match:
            current_level = trust_match.group(1).strip().strip('"').strip("'")
        if current_level in stats["by_level"]:
            stats["by_level"][current_level] += 1

        # Scan
        scan_result = scan_skill(content)
        if scan_result.safe:
            stats["scan_results"]["safe"] += 1
        else:
            stats["scan_results"]["unsafe"] += 1

        # Usage count
        skill_id = skill_file.stem
        stats["total_uses"] += count_successful_uses(skills_dir, skill_id)

    return stats
