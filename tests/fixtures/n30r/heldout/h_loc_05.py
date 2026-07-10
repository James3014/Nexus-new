ORIGINAL = 'def swap(a, b):\n    return a, a\n'
GOLDEN = 'def swap(a, b):\n    return b, a\n'
VERIFIER = ('python3', '-c', 'from f import swap; assert swap(1,2)==(2,1)')
EXPECTED_FAILURE = 'AssertionError'
