ORIGINAL = 'def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return b\n'
GOLDEN = 'def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n'
VERIFIER = ('python3', '-c', 'from f import gcd; assert gcd(12,8)==4; assert gcd(7,13)==1')
EXPECTED_FAILURE = 'AssertionError'
