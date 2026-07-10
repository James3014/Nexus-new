ORIGINAL = 'def add(a, b)\n    return a + b\n'
GOLDEN = 'def add(a, b):\n    return a + b\n'
VERIFIER = ('python3', '-c', 'from f import add; assert add(2,3)==5')
EXPECTED_FAILURE = 'SyntaxError'
