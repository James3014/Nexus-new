ORIGINAL = 'def safe_divide(a, b):\n    return a / 0\n'
GOLDEN = 'def safe_divide(a, b):\n    return a / b if b != 0 else 0\n'
VERIFIER = ('python3', '-c', 'from f import safe_divide; assert safe_divide(10,2)==5.0; assert safe_divide(10,0)==0')
EXPECTED_FAILURE = 'ZeroDivisionError'
