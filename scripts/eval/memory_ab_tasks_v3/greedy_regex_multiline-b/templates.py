import re

_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


def placeholders(text):
    """Return the stripped names of {{ name }} placeholders, in order.

    A placeholder never spans a line break.
    """
    return [m.strip() for m in _PLACEHOLDER.findall(text)]
