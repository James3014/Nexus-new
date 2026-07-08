import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import os
from nexus.services.local_heal.local_model_executor import (
    _reanchor_pipeline_patch_to_locked_search,
    LocalModelExecutorRequest,
    _extract_old_new_text_from_unified_diff
)

# 建立一個臨時目錄及檔案
tmp_dir = Path("./tmp_test_reanchor")
tmp_dir.mkdir(exist_ok=True)
current_text = "def double(x):\n    return x * 2\n"
target_file = tmp_dir / "math_util.py"
target_file.write_text(current_text, encoding="utf-8")

# 模擬一個 request
req = LocalModelExecutorRequest(
    task_id="toy-math-solve",
    problem_statement="test",
    repo_root=str(tmp_dir),
    target_file="math_util.py",
    selected_capabilities=(),
    evidence_refs=(),
)

# 從 live run 抓取出來的其中一個 projected_patch 範例
projected_patch = """--- a/math_util.py
+++ b/math_util.py
@@ -1,4 +1,8 @@
 def double(x):
     if not isinstance(x, (int, float)):
         raise ValueError("Input must be a number")
-    return x * 2
+    try:
+        return x * 2
+    except Exception:
+        return None
"""

locked_search = "def double(x):\n    return x * 2"

print("Locked Search:")
print(repr(locked_search))
print("Current Text:")
print(repr(current_text))

old_text, new_text = _extract_old_new_text_from_unified_diff(projected_patch)
print("\nExtracted old_text from diff:")
print(repr(old_text))
print("Extracted new_text from diff:")
print(repr(new_text))

# 模擬 reanchor logic
print("\nEvaluating reanchor conditions:")
print("1. projected_patch or locked_search empty?", not projected_patch.strip() or not locked_search.strip())
print("2. old_text or new_text empty?", not old_text.strip() or not new_text.strip())
print("3. old_text.strip() == locked_search.strip()?", old_text.strip() == locked_search.strip())

# 檢測 locked_search.strip() in current_text
print("4. locked_search.strip() in current_text?", locked_search.strip() in current_text)

# 執行 reanchor
rebuilt, meta = _reanchor_pipeline_patch_to_locked_search(req, locked_search, projected_patch)
print("\nReanchored Result:")
print("pipeline_locked_search_reanchored:", meta.get("pipeline_locked_search_reanchored"))
print("Rebuilt patch:\n", rebuilt)

import shutil
shutil.rmtree(tmp_dir)
