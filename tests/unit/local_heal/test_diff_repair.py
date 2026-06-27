from __future__ import annotations

from nexus.services.local_heal.diff_repair import repair_malformed_diff

def test_repair_malformed_diff_success() -> None:
    malformed_diff = """--- a/f.py
+++ b/f.py
@@ -2,1 +2,1 @@ (malformed offset header)
-print('hello')
+print('world')
"""
    locked_search = "print('hello')\n"
    reconstructed, receipt = repair_malformed_diff(malformed_diff, "f.py", locked_search, span_start=5)
    
    assert receipt.repair_attempted is True
    assert receipt.repair_success is True
    assert receipt.repaired_by_rule == "reconstruct_single_span_diff"
    assert "--- a/f.py" in reconstructed
    assert "+++ b/f.py" in reconstructed
    assert "@@ -5" in reconstructed
    assert "-print('hello')" in reconstructed
    assert "+print('world')" in reconstructed

def test_repair_malformed_diff_no_added_lines() -> None:
    malformed_diff = """--- a/f.py
+++ b/f.py
-print('hello')
"""
    locked_search = "print('hello')\n"
    reconstructed, receipt = repair_malformed_diff(malformed_diff, "f.py", locked_search)
    
    assert receipt.repair_attempted is True
    assert receipt.repair_success is False
    assert receipt.repair_reason == "no_added_lines_found_in_diff"

def test_repair_malformed_diff_missing_args() -> None:
    malformed_diff = "--- a/f.py\n+++ b/f.py\n-print('hello')\n"
    _, receipt1 = repair_malformed_diff(malformed_diff, "", "print('hello')")
    assert receipt1.repair_success is False
    assert receipt1.repair_reason == "missing_target_file_or_locked_search"
    
    _, receipt2 = repair_malformed_diff(malformed_diff, "f.py", "")
    assert receipt2.repair_success is False


def test_repair_malformed_diff_with_source_root() -> None:
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as src_root:
        file_path = os.path.join(src_root, "f.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("def func():\n    print('original')\n")
            
        malformed_diff = """--- a/f.py
+++ b/f.py
-print('original')
+print('replaced')
"""
        locked_search = "print('original')"
        reconstructed, receipt = repair_malformed_diff(
            malformed_diff,
            "f.py",
            locked_search,
            span_start=2,
            source_root=src_root
        )
        assert receipt.repair_success is True
        assert "    print('original')" in receipt.repaired_diff
        assert "    print('replaced')" in receipt.repaired_diff
        assert "@@ -2" in reconstructed
