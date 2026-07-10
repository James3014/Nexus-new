ORIGINAL = 'def sign(x):\n    return 1\n'
GOLDEN = 'def sign(x):\n    if x > 0: return 1\n    if x < 0: return -1\n    return 0\n'
VERIFIER = ('python3', '-c', 'from f import sign; assert sign(5)==1; assert sign(-3)==-1; assert sign(0)==0')
EXPECTED_FAILURE = 'AssertionError'
