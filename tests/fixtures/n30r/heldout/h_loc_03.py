ORIGINAL = 'def clamp(val, lo, hi):\n    return val\n'
GOLDEN = 'def clamp(val, lo, hi):\n    return max(lo, min(hi, val))\n'
VERIFIER = ('python3', '-c', 'from f import clamp; assert clamp(5,1,10)==5; assert clamp(-1,0,10)==0; assert clamp(15,0,10)==10')
EXPECTED_FAILURE = 'AssertionError'
