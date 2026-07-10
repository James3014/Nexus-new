"""Smoke task 1: syntax/format-sensitive repair (missing colon)."""
# original — fails with SyntaxError
ORIGINAL = """\
def greet(name)
    return f"Hello, {name}!"
"""
# golden — fixed
GOLDEN = """\
def greet(name):
    return f"Hello, {name}!"
"""
VERIFIER = ("python3", "-c", "from f import greet; assert greet('world') == 'Hello, world!'")
EXPECTED_FAILURE = "SyntaxError"
