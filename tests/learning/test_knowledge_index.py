import pytest
import tempfile
from pathlib import Path
from nexus.learning.knowledge_index import KnowledgeIndex

def test_knowledge_index():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        index = KnowledgeIndex(tmp_path)
        
        # Write some skills
        skill1 = """---
name: s1
description: Fix websocket race condition missing mutex
task_id: bug-1
task_type: bug
keywords: [websocket, race]
success_metric:
  repair_success: true
  retry_count: 1
  pattern_reuse_rate: 0.0
---
# Body
## 修復步驟
Use Mutex"""

        skill2 = """---
name: s2
description: Fix index out of bounds exception in user array
task_id: bug-2
task_type: bug
keywords: [array, bounds]
success_metric:
  repair_success: true
  retry_count: 1
  pattern_reuse_rate: 0.0
---
# 實驗與研究證據
```json
{"hypothesis_id": "H1", "content": "check len()"}
```
"""

        # Manually create skill files
        skills_dir = tmp_path / "skills" / "learned"
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "s1.md").write_text(skill1)
        (skills_dir / "s2.md").write_text(skill2)
        
        # Test Load Full
        full_s1 = index.load_full_skill("s1")
        assert "Use Mutex" in full_s1
        
        # Test Load Evidence
        ev_s1 = index.load_evidence("s1")
        assert ev_s1 is None  # no research section
        
        ev_s2 = index.load_evidence("s2")
        assert ev_s2 is not None
        assert ev_s2["hypothesis_id"] == "H1"
        
        # Test Search (Token Overlap)
        # Should match s2 strongly
        res2 = index.search_similar("user array out of bounds exception index error", threshold=0.0)
        assert len(res2) > 0
        assert res2[0][0].name == "s2"
        
        # Should match s1
        res1 = index.search_similar("concurrent websocket race condition mutex lock", threshold=0.0)
        assert len(res1) > 0
        assert res1[0][0].name == "s1"
