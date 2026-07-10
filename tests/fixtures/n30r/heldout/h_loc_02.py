ORIGINAL = 'def max_of_two(a, b):\n    return a\n'
GOLDEN = 'def max_of_two(a, b):\n    return a if a >= b else b\n'
VERIFIER = ('python3', '-c', 'from f import max_of_two; assert max_of_two(3,5)==5; assert max_of_two(7,2)==7')
EXPECTED_FAILURE = 'AssertionError'
