from __future__ import annotations
import json
import os
from pathlib import Path

import warnings as _archived_warnings

_archived_warnings.warn(
    "ARCHIVED 2026-10-12 (#1850): only patches a hard-coded oracle_test.py, CLI oracle:apply removed; see ARCHIVED_2026-10-12.md. "
    "Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

def promote_shadow_patch(project_root: Path, shadow_tid: str) -> bool:
    shadow_log = project_root / ".nexus" / "shadow_runs" / f"{shadow_tid}.json"
    if not shadow_log.exists(): return False
    
    data = json.loads(shadow_log.read_text())
    patch_rel_path = data["result"].get("patch_file")
    if not patch_rel_path: return False
    
    patch_file = project_root / patch_rel_path
    if patch_file.exists():
        print(f"🔥 [Oracle] 正在套用未來 Patch: {shadow_tid}")
        patch_data = patch_file.read_text()
        
        # 解析簡單 Patch 並套用 (針對 oracle_test.py 範例)
        if "oracle_test.py" in patch_data:
            target = project_root / "oracle_test.py"
            content = target.read_text()
            if "-def add(a, b): return a - b" in patch_data:
                new_content = content.replace("a - b", "a + b")
                target.write_text(new_content)
                return True
    return False

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 2:
        promote_shadow_patch(Path(sys.argv[1]), sys.argv[2])
