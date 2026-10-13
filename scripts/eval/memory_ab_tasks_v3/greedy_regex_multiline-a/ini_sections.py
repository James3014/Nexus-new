import re

_HEADER = re.compile(r"^\[(.*)\]", re.MULTILINE | re.DOTALL)


def section_names(text):
    """Return the names of the [section] header lines in INI text, in order."""
    return _HEADER.findall(text)
