"""Smoke task 2: anchor/localization-sensitive repair (wrong variable name)."""
# original — uses wrong variable, causes NameError
ORIGINAL = """\
def double(x):
    return y * 2
"""
# golden — fixed
GOLDEN = """\
def double(x):
    return x * 2
"""
VERIFIER = ("python3", "-c", "from f import double; assert double(5) == 10")
EXPECTED_FAILURE = "NameError"
