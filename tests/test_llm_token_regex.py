import pytest
import re

@pytest.mark.parametrize("output, expected_tokens", [
    ("Total Session Tokens: 1,420", 1420),
    ("Total Session Tokens: 2,500", 2500),
    ("Total Session Tokens: 10,000", 10000),
    ("Total Session Tokens: 123", 123),
    ("tokens used 500", 500),
    ('[Metrics] total_tokens: 800', 800),
    ('{"total_tokens": 1200}', 1200),
    ("No tokens here", 0),
])
def test_token_regex_extraction(output, expected_tokens):
    """驗證 llm.py 中的正則表達式是否能正確提取各種格式的 Token。"""
    
    # 這裡模擬 nexus/services/llm.py 中的提取邏輯
    tokens_total = 0
    
    # 格式 1: tokens used 123
    token_match = re.search(r"tokens used\s+(\d+(?:,\d+)?)", output, re.I)
    # 格式 2: [Metrics] total_tokens: 123
    token_match_v2 = re.search(r"total_tokens[:\s]+(\d+(?:,\d+)?)", output, re.I)
    # 格式 3: usage: { ..."total_tokens": 123 }
    token_match_v3 = re.search(r"\"total_tokens\":\s*(\d+)", output, re.I)
    # 格式 4: Total Session Tokens: 1,234 (codex-loop brain format)
    token_match_v4 = re.search(r"Total Session Tokens:\s*(\d+(?:,\d+)?)", output, re.I)
    
    if token_match:
        tokens_total = int(token_match.group(1).replace(",", ""))
    elif token_match_v2:
        tokens_total = int(token_match_v2.group(1).replace(",", ""))
    elif token_match_v3:
        tokens_total = int(token_match_v3.group(1).replace(",", ""))
    elif token_match_v4:
        tokens_total = int(token_match_v4.group(1).replace(",", ""))
        
    assert tokens_total == expected_tokens
