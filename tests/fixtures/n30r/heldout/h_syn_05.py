ORIGINAL = 'def fn():\n    x = 1\n    x = 2\n    return x\n'
GOLDEN = 'def fn():\n    return 1\n'
VERIFIER = ('python3', '-c', 'from f import fn; assert fn()==1')
EXPECTED_FAILURE = 'AssertionError'
