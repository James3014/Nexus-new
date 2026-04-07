import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from nexus.services.memory_repository import MemoryRepository

logger = logging.getLogger(__name__)

class KnowledgeRecoverer:
    """🛡️ Nexus v24.0 Knowledge Recovery Service."""
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.mirror_path = project_root / ".nexus/eternal/mirror"
        self.repo = MemoryRepository(project_root / ".nexus/main_brain.db")

    def recover_from_mirror(self, target_table: str = "policy_memory") -> int:
        """還原本地鏡像至 LanceDB。"""
        if not self.mirror_path.exists():
            logger.warning("⚠️ No mirror directory found.")
            return 0
        
        recovered_count = 0
        mirror_files = list(self.mirror_path.glob("*.jsonl"))
        
        print(f"🕵️ Searching for mirror data in {self.mirror_path}...")
        for mirror_file in mirror_files:
            try:
                rows = []
                with open(mirror_file, "r", encoding="utf-8") as f:
                    for line in f:
                        rows.append(json.loads(line))
                
                if rows:
                    self.repo.add_rows(target_table, rows)
                    recovered_count += len(rows)
                    print(f"✅ Recovered {len(rows)} atoms from {mirror_file.name}")
            except Exception as e:
                logger.error(f"❌ Failed to process mirror {mirror_file.name}: {e}")
        
        return recovered_count

if __name__ == "__main__":
    # 🧪 TEST: Manual Recovery Trigger
    recoverer = KnowledgeRecoverer(Path("/Users/jameschen/Workspace/nexus"))
    count = recoverer.recover_from_mirror()
    print(f"🏁 Recovery Complete. Total Atoms Re-ingested: {count}")
