ORIGINAL = 'class Calculator:\n    def add(self, a, b)\n        return a + b\n'
GOLDEN = 'class Calculator:\n    def add(self, a, b):\n        return a + b\n'
VERIFIER = ('python3', '-c', 'from f import Calculator; assert Calculator().add(2,3)==5')
EXPECTED_FAILURE = 'SyntaxError'
