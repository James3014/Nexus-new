from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re
import yaml
import logging

logger = logging.getLogger(__name__)

class FeatureTasker:
    """🌲 [Wave 2] Feature Tasker: Roadmap to Actionable Tasks"""
    
    def __init__(self, roadmap_path: Path):
        self.roadmap_path = roadmap_path

    def parse_insights(self) -> List[Dict[str, str]]:
        """將 80 洞察 Markdown 轉化為任務清單內容內容內容及性能"""
        if not self.roadmap_path.exists():
            logger.warning(f"🌲 [Tasker] Roadmap not found at {self.roadmap_path}")
            return []
            
        tasks = []
        with open(self.roadmap_path, "r") as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines):
            # 🚀 行動 16: 解析 Markdown 列表作為任務
            match = re.search(r"^[-\*]\s+(.*)", line)
            if match:
                tasks.append({
                    "task_id": f"FEAT-{i:03d}",
                    "description": match.group(1).split("[")[0].strip(),
                    "priority": "HIGH" if "🏆" in line else "NORMAL"
                })
        
        logger.info(f"🌲 [Tasker] Extracted {len(tasks)} tasks from roadmap.")
        return tasks

if __name__ == "__main__":
    tasker = FeatureTasker(Path("80_insights_roadmap.md"))
    print(tasker.parse_insights()[:5])
