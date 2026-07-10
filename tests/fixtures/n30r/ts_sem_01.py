ORIGINAL = "def count_words(s):\n    return len(s.split('x'))\n"
GOLDEN = 'def count_words(s):\n    return len(s.split())\n'
VERIFIER = ('python3', '-c', "from f import count_words; assert count_words('hello world')==2; assert count_words('one')==1")
EXPECTED_FAILURE = 'AssertionError'
