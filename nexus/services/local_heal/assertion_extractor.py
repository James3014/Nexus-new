import re
from typing import List, Dict

class AssertionExtractor:
    """
    🛡️ Parser for pytest AssertionError and stdout to extract counterexamples (TDD Hardening).
    """

    @staticmethod
    def extract_counterexamples(pytest_output: str) -> List[Dict[str, str]]:
        """
        從 pytest 輸出中尋找 AssertionError 的失敗測資。
        支援格式:
        1. E       AssertionError: assert 'actual' == 'expected'
        2. E       assert 'actual' == 'expected'
        """
        counterexamples = []
        if not pytest_output:
            return counterexamples

        # 正則表達式匹配 E AssertionError: assert ... == ... 或是 E assert ... == ...
        pattern_eq = re.compile(
            r"(?:AssertionError:\s*)?assert\s+(?P<actual>.+?)\s+==\s+(?P<expected>.+)"
        )

        for raw_line in pytest_output.splitlines():
            stripped = raw_line.strip()
            if not (stripped.startswith("E") or "AssertionError" in stripped):
                continue
                
            # Remove pytest 'E' prefix
            if stripped.startswith("E "):
                line = stripped[2:].strip()
            elif stripped.startswith("E"):
                line = stripped[1:].strip()
            else:
                line = stripped
            
            match = pattern_eq.search(line)
            if match:
                actual = match.group("actual").strip()
                expected = match.group("expected").strip()
                
                # 去除外層引號（若有）
                for quote in ("'", '"'):
                    if actual.startswith(quote) and actual.endswith(quote) and len(actual) >= 2:
                        actual = actual[1:-1]
                    if expected.startswith(quote) and expected.endswith(quote) and len(expected) >= 2:
                        expected = expected[1:-1]
                
                counterexamples.append({
                    "actual": actual,
                    "expected": expected,
                    "raw_line": line
                })

        return counterexamples

    @staticmethod
    def format_counterexamples(counterexamples: List[Dict[str, str]]) -> str:
        """
        將提取出來的反例格式化為給 LLM 的指示。
        """
        if not counterexamples:
            return ""
        
        lines = [
            "⚠️ [COUNTEREXAMPLES / 失敗斷言與反例]",
            "Your code failed verification on the following cases. Your fix MUST make these pass:",
        ]
        for item in counterexamples:
            lines.append(f"- Expected: {item['expected']} | Actual: {item['actual']}")
        return "\n".join(lines)
