ORIGINAL = 'for i in range(5)\n    pass\n'
GOLDEN = 'for i in range(5):\n    pass\n'
VERIFIER = ('python3', '-c', "exec(open('f.py').read())")
EXPECTED_FAILURE = 'SyntaxError'
