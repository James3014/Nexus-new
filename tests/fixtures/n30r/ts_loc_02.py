ORIGINAL = 'def first_even(nums):\n    for n in nums:\n        if n % 2 == 1:\n            return n\n    return None\n'
GOLDEN = 'def first_even(nums):\n    for n in nums:\n        if n % 2 == 0:\n            return n\n    return None\n'
VERIFIER = ('python3', '-c', 'from f import first_even; assert first_even([1,3,4,5])==4; assert first_even([1,3,5])==None')
EXPECTED_FAILURE = 'AssertionError'
