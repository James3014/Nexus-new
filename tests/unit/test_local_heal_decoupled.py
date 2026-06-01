import pytest
from nexus.services.local_heal.matcher import Normalizer, SlidingWindowMatcher

def test_normalizer_quotes_and_whitespace():
    norm = Normalizer()
    text = "  hello   \"world\"  and   'everyone'  "
    result = norm.normalize(text)
    # 雙引號應轉單引號，多空格應壓縮，首尾應清理
    assert result == "hello 'world' and 'everyone'"

def test_sliding_window_matcher_exact_and_fuzzy():
    matcher = SlidingWindowMatcher()
    file_content = "def test_func():\n    return 'hello world'\n"
    search_text = "def test_func():\n  return \"hello world\""
    
    # 執行歸一化滑動視窗匹配
    matched_sub, verbatim = matcher.match(file_content, search_text)
    assert matched_sub == "def test_func():\n    return 'hello world'"
    assert verbatim == matched_sub


def test_parser_aider_format_parsed_correctly():
    from nexus.services.local_heal.parser import SearchReplaceParser
    parser = SearchReplaceParser()
    
    llm_output = (
        "Here is the fix:\n\n"
        "FILE: math_utils.py\n"
        "<<<<<<< SEARCH\n"
        "def add(a, b):\n"
        "    return a - b\n"
        "=======\n"
        "def add(a, b):\n"
        "    return a + b\n"
        ">>>>>>> REPLACE\n"
    )
    
    blocks = parser.parse_blocks(llm_output)
    assert len(blocks) == 1
    assert blocks[0]["file"] == "math_utils.py"
    assert "return a - b" in blocks[0]["search"]
    assert "return a + b" in blocks[0]["replace"]


def test_parser_create_file_block_parsed_as_create_operation():
    from nexus.services.local_heal.parser import SearchReplaceParser
    parser = SearchReplaceParser()

    blocks = parser.parse_blocks(
        "CREATE FILE: pkg/new_transform.py\n"
        "<<<<<<< CONTENT\n"
        "def transform():\n"
        "    return 'created'\n"
        ">>>>>>> CONTENT\n"
    )

    assert len(blocks) == 1
    assert blocks[0]["operation"] == "create"
    assert blocks[0]["file"] == "pkg/new_transform.py"
    assert "def transform" in blocks[0]["replace"]

