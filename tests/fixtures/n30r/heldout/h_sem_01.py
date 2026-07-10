ORIGINAL = 'def factorial(n):\n    if n == 0: return 0\n    return n * factorial(n-1)\n'
GOLDEN = 'def factorial(n):\n    if n == 0: return 1\n    return n * factorial(n-1)\n'
VERIFIER = ('python3', '-c', 'from f import factorial; assert factorial(5)==120; assert factorial(0)==1')
EXPECTED_FAILURE = 'AssertionError'
