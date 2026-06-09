import pytest
from nexus.engine.patch.target_discovery import TargetFileDiscovery

def test_extract_target_from_diff_header():
    discovery = TargetFileDiscovery()
    raw = "diff --git a/core.py b/core.py\n--- a/core.py\n+++ b/core.py\n@@ -1 +1 @@"
    res = discovery.resolve(raw)
    assert res.resolved is True
    assert res.target_file == "core.py"

def test_extract_target_from_search_block_metadata():
    # If there is no explicit diff header but we passed context
    discovery = TargetFileDiscovery()
    raw = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"
    res = discovery.resolve(raw, context_files=["utils/helpers.py"])
    assert res.resolved is True
    assert res.target_file == "utils/helpers.py"

def test_reject_when_multiple_candidate_files():
    discovery = TargetFileDiscovery()
    raw = "diff --git a/one.py b/one.py\n--- a/one.py\n+++ b/one.py\ndiff --git a/two.py b/two.py\n--- a/two.py\n+++ b/two.py\n"
    res = discovery.resolve(raw)
    assert res.resolved is False
    assert "AMBIGUOUS_TARGET_FILES" in res.reason

def test_reject_when_no_target_can_be_resolved():
    discovery = TargetFileDiscovery()
    raw = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"
    res = discovery.resolve(raw) # No context files
    assert res.resolved is False
    assert res.reason == "NO_TARGET_FILE_FOUND"
