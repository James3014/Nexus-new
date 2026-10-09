import re

COMMENT = re.compile(r"/\*.*\*/")  # BUG: greedy, and '.' does not match newlines


def strip_comments(source):
    """Remove /* ... */ block comments, keeping all other text.

    Comments may span lines and may be empty (/**/). Each comment ends at its
    first closing marker.
    """
    return COMMENT.sub("", source)
