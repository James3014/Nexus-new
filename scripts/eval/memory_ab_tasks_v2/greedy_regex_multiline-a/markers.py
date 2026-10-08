import re

BLOCK = re.compile(r"<<begin>>(.*)<<end>>")  # BUG: greedy, and '.' does not match newlines


def extract_blocks(text):
    """Return the stripped body of every <<begin>>...<<end>> block, in order.

    Blocks may span several lines and may be empty. Unclosed blocks are ignored.
    """
    match = BLOCK.search(text)
    if not match:
        return []
    return [match.group(1).strip()]
