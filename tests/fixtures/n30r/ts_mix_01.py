ORIGINAL = 'def sum_until_negative(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total\n'
GOLDEN = 'def sum_until_negative(nums):\n    total = 0\n    for n in nums:\n        if n < 0: break\n        total += n\n    return total\n'
VERIFIER = ('python3', '-c', 'from f import sum_until_negative; assert sum_until_negative([1,2,3,-1,4])==6; assert sum_until_negative([-1,2])==0')
EXPECTED_FAILURE = 'AssertionError'
