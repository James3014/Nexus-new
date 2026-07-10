ORIGINAL = 'def divide(a, b)\n    return a / b\n'
GOLDEN = 'def divide(a, b):\n    return a / b\n'
VERIFIER = ('python3', '-c', 'from f import divide; assert divide(10,2)==5.0')
EXPECTED_FAILURE = 'SyntaxError'
