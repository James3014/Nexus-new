ORIGINAL = 'def chunk(lst, n):\n    result = []\n    for i in range(0, len(lst), n):\n        result.append(lst[i:i+n])\n    result.append(lst[-1])\n    return result\n'
GOLDEN = 'def chunk(lst, n):\n    return [lst[i:i+n] for i in range(0, len(lst), n)]\n'
VERIFIER = ('python3', '-c', 'from f import chunk; assert chunk([1,2,3,4,5],2)==[[1,2],[3,4],[5]]')
EXPECTED_FAILURE = 'AssertionError'
