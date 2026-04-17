from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import yaml
import logging
from dataclasses import dataclass
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
from nexus.learning.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

@dataclass
class ScanReport:
    new_skills: int = 0
    updated_skills: int = 0
    skipped: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class ExternalSkillLoader:
    """🧬 Nexus v4.0: 外部技能載入器
    職責：掃描外部 SKILL.md 目錄，解析並注入 SkillRegistry。
    """
    
    def __init__(self, registry: SkillRegistry, scan_dirs: List[Path]):
        self.registry = registry
        self.scan_dirs = scan_dirs

    def scan_and_register(self) -> ScanReport:
        report = ScanReport()
        for sdir in self.scan_dirs:
            if not sdir.exists():
                logger.warning("scan_dir_not_found: %s", sdir)
                continue
            
            # 支援目錄下直接有 SKILL.md 或子目錄中有 SKILL.md
            for skill_file in sdir.glob("**/SKILL.md"):
                try:
                    fm = self._parse_skill_md(skill_file)
                    if fm:
                        self.registry.upsert(fm, origin_node_id="external")
                        report.new_skills += 1
                except Exception as e:
                    report.errors.append(f"Error parsing {skill_file}: {str(e)}")
                    report.skipped += 1
        return report

    def _parse_skill_md(self, path: Path) -> Optional[SkillFrontmatter]:
        """解析 SKILL.md 並轉化為 Nexus 標準模型"""
        try:
            content = path.read_text(encoding="utf-8")
            parts = content.split("---")
            if len(parts) < 3:
                return None
            
            fm_dict = yaml.safe_load(parts[1])
            if not fm_dict:
                return None
            
            skill_id = fm_dict.get("id") or fm_dict.get("name") or path.parent.name
            
            # 偵測附件物
            has_scripts = (path.parent / "scripts").exists()
            has_evals = (path.parent / "evals").exists() or (path.parent / "assets" / "evals").exists()
            
            # 提取觸發詞
            triggers = fm_dict.get("trigger_keywords", [])
            if not triggers and "description" in fm_dict:
                # 簡單啟發式提取描述前半段
                triggers = fm_dict["description"].split(" ")[:3]

            metric = SkillSuccessMetric(
                repair_success=False,
                retry_count=0,
                pattern_reuse_rate=0.0
            )

            return SkillFrontmatter(
                name=fm_dict.get("name", skill_id),
                description=fm_dict.get("description", ""),
                task_id=skill_id,
                success_metric=metric,
                source="external-skill-md",
                trust_level="reviewed",  # 外部匯入預設為 reviewed
                task_type=fm_dict.get("task_type", "unknown"),
                keywords=fm_dict.get("keywords", []) + triggers,
                origin_type="external-skill-md",
                external_path=str(path.absolute()),
                has_scripts=has_scripts,
                has_evals=has_evals,
                trigger_keywords=triggers
            )
        except Exception as e:
            logger.error("skill_parse_failed [%s]: %s", path, e)
            return None
