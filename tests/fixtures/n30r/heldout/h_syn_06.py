ORIGINAL = 'x = [1, 2, 3]\ny = x[5]\n'
GOLDEN = 'x = [1, 2, 3]\ny = x[2]\n'
VERIFIER = ('python3', '-c', "exec(open('f.py').read()); assert y == 3")
EXPECTED_FAILURE = 'IndexError'
