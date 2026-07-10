ORIGINAL = "def compact(s):\n    return ' '.join(s.split('x'))\n"
GOLDEN = "def compact(s):\n    return ' '.join(s.split())\n"
VERIFIER = ('python3', '-c', "from f import compact; assert compact('  a  b  ')=='a b'")
EXPECTED_FAILURE = 'AssertionError'
