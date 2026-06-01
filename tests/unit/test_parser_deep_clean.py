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


def test_parser_accepts_inline_simple_search_replace_headers():
    parser = SearchReplaceParser()

    llm_output = (
        "FILE: astropy/modeling/separable.py\n"
        "SEARCH: def _separable(transform):\n"
        "    return old_value\n"
        "REPLACE: def _separable(transform):\n"
        "    return new_value\n"
        "END"
    )

    blocks = parser.parse_blocks(llm_output)

    assert len(blocks) == 1
    assert blocks[0]["file"] == "astropy/modeling/separable.py"
    assert blocks[0]["search"].startswith("def _separable")
    assert blocks[0]["replace"].startswith("def _separable")


def test_parser_accepts_final_simple_block_without_end_marker():
    parser = SearchReplaceParser()

    llm_output = (
        "FILE: astropy/modeling/separable.py\n"
        "SEARCH: def _separable(transform):\n"
        "    return old_value\n"
        "\n"
        "REPLACE: def _separable(transform):\n"
        "    return new_value\n"
    )

    blocks = parser.parse_blocks(llm_output)

    assert len(blocks) == 1
    assert blocks[0]["search"].startswith("def _separable")
    assert blocks[0]["replace"].startswith("def _separable")
