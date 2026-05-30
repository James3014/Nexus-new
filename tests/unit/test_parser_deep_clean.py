import pytest
from nexus.services.local_heal.parser import SearchReplaceParser

def test_parser_strips_inner_markdown_fences():
    parser = SearchReplaceParser()
    
    llm_output = (
        "FILE: math_utils.py\n"
        "<<<<<<< SEARCH\n"
        "```python\n"
        "def add(a, b):\n"
        "    return a - b\n"
        "```\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    blocks = parser.parse_blocks(llm_output)
    assert len(blocks) == 1
    assert "```" not in blocks[0]["search"]
    assert "add(a, b)" in blocks[0]["search"]


def test_parser_rejects_placeholder_search():
    parser = SearchReplaceParser()
    
    # 含有省略號的 SEARCH block
    llm_output_placeholder = (
        "FILE: math_utils.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    # ... existing code ...\n"
        "    return a - b\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    blocks = parser.parse_blocks(llm_output_placeholder)
    assert len(blocks) == 1
    assert blocks[0].get("has_placeholder") is True
