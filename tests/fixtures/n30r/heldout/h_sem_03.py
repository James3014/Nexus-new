ORIGINAL = 'def is_palindrome(s):\n    return s == s\n'
GOLDEN = 'def is_palindrome(s):\n    return s == s[::-1]\n'
VERIFIER = ('python3', '-c', "from f import is_palindrome; assert is_palindrome('racecar') is True; assert is_palindrome('hello') is False")
EXPECTED_FAILURE = 'AssertionError'
