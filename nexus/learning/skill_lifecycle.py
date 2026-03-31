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
from nexus.learning.disk_janitor import DiskJanitor
from nexus.learning.disk_policy import DiskPolicy
from nexus.core.errors import NexusError, ValidationError, PhaseError
import logging

logger = logging.getLogger(__name__)


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


def _get_usage_log(skills_dir: Path) -> Path:
    return skills_dir / USAGE_LOG_FILENAME

def archive_to_eternal(project_root: Path, skills_dir: Path, deid: bool = True):
    """🛰️ v22 Phase 1: 物理將本地日誌永恆化至 Arweave"""
    log_path = _get_usage_log(skills_dir)
    if not log_path.exists():
        return

    from nexus.learning.eternal_memory import EternalMemoryManager
    manager = EternalMemoryManager(project_root, deid=deid)
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    lesson = json.loads(line.strip())
                    manager.upload_lesson(lesson)
                except: continue
        logger.info("eternal_archive_completed [%s]", log_path.name)
    except Exception as e:
        logger.error("eternal_archive_physical_error_graceful_降級 [%s]", str(e))

def record_usage(skills_dir: Path, skill_id: str, task_id: str, outcome: str = "success") -> None:
    """Append a usage event to the JSONL log, rotating if necessary."""
    log_path = _get_usage_log(skills_dir)
    
    # 1. Automatic Log Rotation Trigger
    try:
        policy = DiskPolicy.from_env()
        max_bytes = policy.max_log_size_mb * 1024 * 1024
        if log_path.exists() and log_path.stat().st_size > max_bytes:
            janitor = DiskJanitor(skills_dir.parent.parent, config=policy)
            janitor.rotate_usage_log(skills_dir)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("auto_log_rotation_failed task_id=unknown skill_id=%s trace_id=unknown: %s", skill_id, exc)

    # 2. Append event
    event = UsageEvent(
        skill_id=skill_id,
        used_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        task_id=task_id,
        outcome=outcome,
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    # Update last_used_at in skill frontmatter
    skill_path = skills_dir / f"{skill_id}.md"
    if skill_path.exists():
        content = skill_path.read_text(encoding="utf-8")
        now_str = event.used_at
        if re.search(r"^last_used_at:", content, re.MULTILINE):
            content = re.sub(r"^last_used_at:.*$", f"last_used_at: {now_str}", content, flags=re.MULTILINE)
        else:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                parts[1] = parts[1].rstrip("\n") + f"\nlast_used_at: {now_str}\n"
                content = "---".join(parts)
        skill_path.write_text(content, encoding="utf-8")


def count_successful_uses(skills_dir: Path, skill_id: str) -> int:
    """Count successful usage events for a given skill (streaming, OOM-safe)."""
    log_path = skills_dir / USAGE_LOG_FILENAME
    if not log_path.exists():
        return 0
    count = 0
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("skill_id") == skill_id and entry.get("outcome") == "success":
                        count += 1
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("usage_log_read_failed skill_id=%s: %s", skill_id, exc)
    except Exception as exc:
        logger.error("unexpected_error_during_usage_count skill_id=%s: %s", skill_id, exc)
        raise NexusError(f"Failed to count usage for {skill_id}") from exc
    return count


def promote_skill(skills_dir: Path, skill_id: str, target_level: str) -> Dict[str, Any]:
    """Promote a skill to the target trust level with atomic backup/rollback."""
    filename = f"{skill_id}.md" if not skill_id.endswith(".md") else skill_id
    skill_path = skills_dir / filename
    if not skill_path.exists():
        return {"success": False, "message": f"技能不存在: {skill_id}"}

    if target_level not in TRUST_LEVELS:
        return {"success": False, "message": f"無效的信任等級: {target_level}"}

    content = skill_path.read_text(encoding="utf-8")
    current_level = "auto-generated"
    trust_match = re.search(r"trust_level:\s*(.+)", content)
    if trust_match:
        current_level = trust_match.group(1).strip().strip('"').strip("'")

    try:
        current_idx = TRUST_LEVELS.index(current_level)
        target_idx = TRUST_LEVELS.index(target_level)
    except ValueError:
        return {"success": False, "message": f"格式異常或未知等級: {current_level}"}

    if target_idx <= current_idx:
        return {"success": False, "message": f"目標等級 ({target_level}) 必須高於當前等級 ({current_level})"}

    if target_idx != current_idx + 1:
        return {"success": False, "message": f"只能逐級升級: {current_level} → {TRUST_LEVELS[current_idx + 1]}"}

    if target_level in ("tested", "production"):
        scan_result = scan_skill(content)
        if not scan_result.safe:
            return {"success": False, "message": f"安全掃描未通過: {scan_result.blocked_reasons}"}
        usage_count = count_successful_uses(skills_dir, skill_id)
        required_uses = 1 if target_level == "tested" else 3
        if usage_count < required_uses:
            return {"success": False, "message": f"使用次數不足 (目前 {usage_count}/{required_uses})"}

    # Transactional Update
    backup_path = skill_path.with_suffix(".md.bak")
    shutil.copy2(skill_path, backup_path)
    
    try:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            if re.search(r"^trust_level:\s*.+$", frontmatter, re.MULTILINE):
                frontmatter = re.sub(r"^trust_level:\s*.+$", f"trust_level: {target_level}", frontmatter, count=1, flags=re.MULTILINE)
            else:
                frontmatter = frontmatter.rstrip("\n") + f"\ntrust_level: {target_level}\n"
            new_content = f"---{frontmatter}---{parts[2]}"
        else:
            new_content = re.sub(r"^trust_level:\s*.+$", f"trust_level: {target_level}", content, count=1, flags=re.MULTILINE)
        
        skill_path.write_text(new_content, encoding="utf-8")
        backup_path.unlink(missing_ok=True)
        return {
            "success": True,
            "message": f"✅ 技能 {skill_id} 已從 {current_level} 升級到 {target_level}",
        }
    except Exception as exc:
        shutil.move(str(backup_path), str(skill_path))
        logger.error("promotion_failed_restored skill_id=%s: %s", skill_id, exc)
        return {"success": False, "message": f"寫入失敗，已還原備份: {exc}"}


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

def reactivate_skill(skills_dir: Path, skill_id: str) -> Dict[str, Any]:
    """重新啟用被衰減的技能，恢復其 trust 權重。"""
    filename = f"{skill_id}.md" if not skill_id.endswith(".md") else skill_id
    skill_path = skills_dir / filename
    if not skill_path.exists():
        return {"success": False, "message": f"技能不存在: {skill_id}"}

    content = skill_path.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if re.search(r"^last_used_at:", content, re.MULTILINE):
        content = re.sub(r"^last_used_at:.*$", f"last_used_at: {now}", content, flags=re.MULTILINE)
    else:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            parts[1] = parts[1].rstrip("\n") + f"\nlast_used_at: {now}\n"
            content = "---".join(parts)

    skill_path.write_text(content, encoding="utf-8")
    return {"success": True, "message": f"🔄 Crystal reactivated: {skill_id}"}


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
