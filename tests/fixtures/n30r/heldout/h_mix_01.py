ORIGINAL = 'def count_chars(s):\n    d = {}\n    for c in s:\n        d[c] = d.get(c, 0)\n    return d\n'
GOLDEN = 'def count_chars(s):\n    d = {}\n    for c in s:\n        d[c] = d.get(c, 0) + 1\n    return d\n'
VERIFIER = ('python3', '-c', "from f import count_chars; r=count_chars('aab'); assert r['a']==2 and r['b']==1")
EXPECTED_FAILURE = 'AssertionError'
