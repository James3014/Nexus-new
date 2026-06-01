from nexus.services.local_heal.validator import validate_name_sanity


def test_validate_name_sanity_allows_docstring_ellipsis_examples():
    code = '''
def example():
    """
    >>> example()
    array([True, False]...)
    """
    return True
'''

    valid, message = validate_name_sanity(code)

    assert valid is True
    assert message == ""


def test_validate_name_sanity_rejects_executable_ellipsis_placeholder():
    code = """
def example():
    ...
"""

    valid, message = validate_name_sanity(code)

    assert valid is False
    assert "placeholder" in message.lower()
