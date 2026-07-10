ORIGINAL = 'class Foo:\n    def bar(self)\n        return 42\n'
GOLDEN = 'class Foo:\n    def bar(self):\n        return 42\n'
VERIFIER = ('python3', '-c', 'from f import Foo; assert Foo().bar()==42')
EXPECTED_FAILURE = 'SyntaxError'
