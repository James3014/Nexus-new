import pytest
from nexus.core.review_status import ReviewStatusNormalizer

def test_normalize_approved():
    s, success = ReviewStatusNormalizer.normalize("APPROVED")
    assert s == "APPROVED"
    assert success is True

def test_normalize_rejected():
    s, success = ReviewStatusNormalizer.normalize("REJECTED")
    assert s == "REJECTED"
    assert success is False

def test_normalize_skipped():
    s, success = ReviewStatusNormalizer.normalize("SKIPPED_QUOTA")
    assert s == "SKIPPED_QUOTA"
    assert success is True

def test_normalize_unknown():
    s, success = ReviewStatusNormalizer.normalize("GARBAGE")
    assert s == "UNKNOWN"
    assert success is False
