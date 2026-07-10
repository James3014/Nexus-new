ORIGINAL = 'def interleave(a, b):\n    result = []\n    i = 0\n    while i < len(a):\n        result.append(a[i])\n        i += 1\n    i = 0\n    while i < len(b):\n        result.append(b[i])\n        i += 1\n    return result\n'
GOLDEN = 'def interleave(a, b):\n    result = []\n    i = 0\n    while i < len(a) or i < len(b):\n        if i < len(a): result.append(a[i])\n        if i < len(b): result.append(b[i])\n        i += 1\n    return result\n'
VERIFIER = ('python3', '-c', 'from f import interleave; assert interleave([1,3],[2,4])==[1,2,3,4]')
EXPECTED_FAILURE = 'AssertionError'
