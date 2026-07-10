ORIGINAL = 'def abs_val(x):\n    return -x\n'
GOLDEN = 'def abs_val(x):\n    return x if x >= 0 else -x\n'
VERIFIER = ('python3', '-c', 'from f import abs_val; assert abs_val(5)==5; assert abs_val(-3)==3')
EXPECTED_FAILURE = 'AssertionError'
