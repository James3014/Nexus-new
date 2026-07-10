ORIGINAL = 'def negate(x):\n    return x\n'
GOLDEN = 'def negate(x):\n    return -x\n'
VERIFIER = ('python3', '-c', 'from f import negate; assert negate(5)==-5; assert negate(-3)==3')
EXPECTED_FAILURE = 'AssertionError'
