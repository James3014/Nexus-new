import pytest
import hashlib
from nexus.services.local_heal.diff_to_ssrp import DiffToSSRPConverter

def test_diff_to_ssrp_converts_single_file_exact_preimage():
    source = (
        "def add(a, b):\n"
        "    return a + b\n"
        "def sub(a, b):\n"
        "    return a - b\n"
    )
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,4 +1,4 @@\n"
        " def add(a, b):\n"
        "-    return a + b\n"
        "+    return int(a + b)\n"
        " def sub(a, b):\n"
        "     return a - b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_to_ssrp_converted"
    assert "FILE: math.py" in ssrp
    assert "<<<<<<< SEARCH" in ssrp
    assert "return a + b" in ssrp
    assert "return int(a + b)" in ssrp
    assert ">>>>>>> REPLACE" in ssrp

def test_diff_to_ssrp_rejects_multi_file_diff():
    source = "content"
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
        "--- a/other.py\n"
        "+++ b/other.py\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_multi_file_rejected"
    assert ssrp == ""

def test_diff_to_ssrp_rejects_target_file_mismatch():
    source = "content"
    diff = (
        "--- a/other.py\n"
        "+++ b/other.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_target_mismatch"
    assert ssrp == ""

def test_diff_to_ssrp_rejects_missing_preimage():
    source = "content"
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-missing line\n"
        "+b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_missing_preimage"
    assert ssrp == ""

def test_diff_to_ssrp_rejects_ambiguous_preimage():
    source = (
        "a\n"
        "a\n"
    )
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_ambiguous_preimage"
    assert ssrp == ""

def test_diff_to_ssrp_records_source_hash():
    source = "some source content"
    diff = (
        "--- a/math.py\n"
        "+++ b/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-some source content\n"
        "+replaced\n"
    )
    ssrp, status, tele = DiffToSSRPConverter.convert(diff, "math.py", source)
    assert status == "unified_diff_to_ssrp_converted"
    expected_src_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    expected_cand_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    assert tele["source_hash_before"] == expected_src_hash
    assert tele["candidate_hash"] == expected_cand_hash
