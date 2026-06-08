import pytest
from nexus.engine.contracts.verification import Verdict, VerifierType
from nexus.engine.verifiers.refactor_guard import RefactorGuard

def test_refactor_guard_rejects_tangled_refactoring():
    """驗證 Refactor Guard 會阻擋混雜業務邏輯修復與檔案移動的 Patch。"""
    guard = RefactorGuard()
    
    # 模擬一個 Tangled Patch：包含檔案重命名與內容修改
    patch = """
diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
diff --git a/core_logic.py b/core_logic.py
--- a/core_logic.py
+++ b/core_logic.py
@@ -1,2 +1,2 @@
-def calc(x): return x + 1
+def calc(x): return x + 2
    """
    
    result = guard.verify(patch)
    assert result.verdict == Verdict.HARD_REJECT
    assert "Tangled Refactoring" in result.reason
    assert "Do not mix file renames" in result.constraint_for_next_round

def test_refactor_guard_allows_single_responsibility():
    """驗證單純的邏輯修補能被允許。"""
    guard = RefactorGuard()
    
    patch = """
diff --git a/core_logic.py b/core_logic.py
--- a/core_logic.py
+++ b/core_logic.py
@@ -1,2 +1,2 @@
-def calc(x): return x + 1
+def calc(x): return x + 2
    """
    
    result = guard.verify(patch)
    assert result.verdict == Verdict.PASS
