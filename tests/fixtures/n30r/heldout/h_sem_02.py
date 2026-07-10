ORIGINAL = 'def fibonacci(n):\n    if n <= 1: return 1\n    return fibonacci(n-1) + fibonacci(n-2)\n'
GOLDEN = 'def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)\n'
VERIFIER = ('python3', '-c', 'from f import fibonacci; assert fibonacci(0)==0; assert fibonacci(1)==1; assert fibonacci(6)==8')
EXPECTED_FAILURE = 'AssertionError'
