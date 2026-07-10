"""Smoke task 4: dependency-light multi-assertion repair (two bugs)."""
# original — two bugs: off-by-one and wrong comparison
ORIGINAL = """\
def count_positives(nums):
    count = 0
    for n in nums:
        if n > 0:
            count += 0
    return count
"""
# golden — fixed
GOLDEN = """\
def count_positives(nums):
    count = 0
    for n in nums:
        if n > 0:
            count += 1
    return count
"""
VERIFIER = ("python3", "-c", "from f import count_positives; assert count_positives([1, -1, 2, 0, 3]) == 3; assert count_positives([]) == 0; assert count_positives([-1, -2]) == 0")
EXPECTED_FAILURE = "AssertionError"
