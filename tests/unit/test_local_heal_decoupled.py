import importlib.util

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


def test_parser_aider_format_parsed_correctly() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None


def test_parser_create_file_block_parsed_as_create_operation() -> None:
    # Retired in #2491 (ARCHIVED_2026-10-17_deadcode_b3.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.parser") is None

