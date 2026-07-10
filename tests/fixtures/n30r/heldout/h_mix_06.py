ORIGINAL = 'def zip_with(f, a, b):\n    return [f(x) for x in a]\n'
GOLDEN = 'def zip_with(f, a, b):\n    return [f(x, y) for x, y in zip(a, b)]\n'
VERIFIER = ('python3', '-c', 'from f import zip_with; r=zip_with(lambda x,y:x-y,[1,2,3],[4,5]); assert r==[-3,-3]')
EXPECTED_FAILURE = 'AssertionError'
