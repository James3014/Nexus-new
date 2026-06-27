from __future__ import annotations

from nexus.services.local_heal.diff_normalizer import normalize_diff_header

def test_normalize_diff_header_no_change() -> None:
    diff = """--- a/f.py
+++ b/f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
    new_diff, receipt = normalize_diff_header(diff, "f.py")
    assert not receipt.normalized
    assert new_diff == diff
    assert receipt.original_target_file == "f.py"

def test_normalize_diff_header_missing_prefix() -> None:
    diff = """--- f.py
+++ f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
    new_diff, receipt = normalize_diff_header(diff, "f.py")
    assert receipt.normalized
    assert "missing_ab_prefix" in receipt.normalization_reason
    assert "--- a/f.py" in new_diff
    assert "+++ b/f.py" in new_diff
    assert receipt.original_target_file == "f.py"

def test_normalize_diff_header_mismatched_filename() -> None:
    diff = """--- old_f.py
+++ new_f.py
@@ -1 +1 @@
-print('hello')
+print('world')
"""
    new_diff, receipt = normalize_diff_header(diff, "f.py")
    assert receipt.normalized
    assert "filename_mismatch" in receipt.normalization_reason
    assert "--- a/f.py" in new_diff
    assert "+++ b/f.py" in new_diff
    assert receipt.original_target_file == "new_f.py"
