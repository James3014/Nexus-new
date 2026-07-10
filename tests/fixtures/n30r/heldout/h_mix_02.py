ORIGINAL = 'def unique(lst):\n    return list(lst)\n'
GOLDEN = 'def unique(lst):\n    return list(dict.fromkeys(lst))\n'
VERIFIER = ('python3', '-c', 'from f import unique; assert unique([1,2,2,3])==[1,2,3]')
EXPECTED_FAILURE = 'AssertionError'
