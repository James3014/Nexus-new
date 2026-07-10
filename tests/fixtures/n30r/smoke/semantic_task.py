"""Smoke task 3: patch-applies-but-verifier-fails semantic repair (wrong return value)."""
# original — applies fine but returns wrong value
ORIGINAL = """\
def is_even(n):
    return n % 2 == 1
"""
# golden — fixed
GOLDEN = """\
def is_even(n):
    return n % 2 == 0
"""
VERIFIER = ("python3", "-c", "from f import is_even; assert is_even(4) is True; assert is_even(3) is False")
EXPECTED_FAILURE = "AssertionError"
