ORIGINAL = 'def all_positive(nums):\n    return True\n'
GOLDEN = 'def all_positive(nums):\n    return all(n > 0 for n in nums)\n'
VERIFIER = ('python3', '-c', 'from f import all_positive; assert all_positive([1,2,3]) is True; assert all_positive([1,-1,3]) is False')
EXPECTED_FAILURE = 'AssertionError'
