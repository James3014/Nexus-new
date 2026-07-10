ORIGINAL = 'if True\n    x = 1\n'
GOLDEN = 'if True:\n    x = 1\n'
VERIFIER = ('python3', '-c', "exec(open('f.py').read()); assert x == 1")
EXPECTED_FAILURE = 'SyntaxError'
