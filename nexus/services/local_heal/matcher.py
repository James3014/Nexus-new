import ast
import re
from typing import Tuple, Protocol, List, Optional, Any
from dataclasses import dataclass

class Normalizer:
    """負責代碼空格與引號歸一化的專職組件 (SoC / Clean Code)"""
    def normalize_quotes(self, text: str) -> str:
        normalized = text.replace('"', "'")
        normalized = normalized.replace("\\'", "'")
        normalized = normalized.replace("''", "'")
        return normalized

    def normalize_whitespace(self, text: str) -> str:
        # 🛡️ 戰甲：移除所有換行與連續空白，達成 Whitespace-Agnostic
        text = text.replace("\n", " ").replace("\r", " ")
        return " ".join(text.split())

    def normalize(self, text: str) -> str:
        return self.normalize_whitespace(self.normalize_quotes(text))


@dataclass
class MatchResult:
    strategy_name: str
    verbatim_text: str       # 從檔案中提取到的原始真實程式碼
    normalized_search: str   # 歸一化的搜尋區塊
    similarity: float = 1.0  # 匹配相似度


class MatchStrategy(Protocol):
    """匹配策略協議 (Protocol)"""
    def match(self, file_content: str, search_text: str, replace_text: str = "") -> Optional[MatchResult]:
        ...


class ExactMatch:
    """Level 1: 完美字面匹配"""
    def match(self, file_content: str, search_text: str, replace_text: str = "") -> Optional[MatchResult]:
        start = 0
        while True:
            idx = file_content.find(search_text, start)
            if idx == -1:
                break
            end_idx = idx + len(search_text)
            if end_idx >= len(file_content) or file_content[end_idx] in ('\n', '\r'):
                return MatchResult(
                    strategy_name="ExactMatch",
                    verbatim_text=search_text,
                    normalized_search=search_text
                )
            start = idx + 1
        return None


class StrippedMatch:
    """Level 2: 忽略首尾空白的字面匹配 ( Enforces perfect line boundary )"""
    def match(self, file_content: str, search_text: str, replace_text: str = "") -> Optional[MatchResult]:
        s_stripped = search_text.strip()
        if not s_stripped:
            return None
        start = 0
        while True:
            idx = file_content.find(s_stripped, start)
            if idx == -1:
                break
            end_idx = idx + len(s_stripped)
            if end_idx >= len(file_content) or file_content[end_idx] in ('\n', '\r'):
                return MatchResult(
                    strategy_name="StrippedMatch",
                    verbatim_text=s_stripped,
                    normalized_search=s_stripped
                )
            start = idx + 1
        return None


class NormalizedMatch:
    """Level 3: 引號與空格歸一化滑動視窗匹配"""
    def __init__(self):
        self.normalizer = Normalizer()

    def match(self, file_content: str, search_text: str, replace_text: str = "") -> Optional[MatchResult]:
        s_stripped = search_text.strip()
        if not s_stripped:
            return None

        norm_search = self.normalizer.normalize(s_stripped)
        if not norm_search:
            return None

        norm_file = self.normalizer.normalize(file_content)
        count = norm_file.count(norm_search)
        if count != 1:
            return None

        norm_start = norm_file.find(norm_search)

        if len(s_stripped) > 250:
            search_range_start = max(0, norm_start - 50)
            search_range_end = min(len(file_content), norm_start + len(s_stripped) + 50)
        else:
            search_range_start = max(0, norm_start - 200)
            search_range_end = min(len(file_content), norm_start + len(s_stripped) + 200)

        len_s = len(s_stripped)
        if len_s > 250:
            min_len = int(0.9 * len_s)
            max_len = int(1.1 * len_s)
        else:
            min_len = int(0.5 * len_s)
            max_len = int(2.0 * len_s)

        for i in range(search_range_start, search_range_end):
            for length in range(min_len, max_len + 1):
                if i + length > len(file_content):
                    break
                sub_str = file_content[i:i+length]
                norm_sub = self.normalizer.normalize(sub_str)
                if norm_sub == norm_search:
                    return MatchResult(
                        strategy_name="NormalizedMatch",
                        verbatim_text=sub_str,
                        normalized_search=sub_str
                    )
        return None


class TruncatedMatch:
    """Level 4: 截斷自癒模糊匹配"""
    def __init__(self):
        self.normalizer = Normalizer()

    def match(self, file_content: str, search_text: str, replace_text: str = "") -> Optional[MatchResult]:
        search_stripped = search_text.strip()
        lines = search_stripped.splitlines()
        if len(lines) < 2:
            return None

        complete_part = "\n".join(lines[:-1]).strip()
        last_line_prefix = lines[-1].strip()

        if not complete_part or not last_line_prefix:
            return None

        norm_complete = self.normalizer.normalize(complete_part)
        norm_file = self.normalizer.normalize(file_content)

        count = norm_file.count(norm_complete)
        if count != 1:
            return None

        norm_start = norm_file.find(norm_complete)
        search_range_start = max(0, norm_start - 50)
        search_range_end = min(len(file_content), norm_start + len(complete_part) + 50)
        
        found_start_idx = -1
        verbatim_complete = ""
        len_c = len(complete_part)
        min_len = int(0.9 * len_c)
        max_len = int(1.1 * len_c)

        for i in range(search_range_start, search_range_end):
            for length in range(min_len, max_len + 1):
                if i + length > len(file_content):
                    break
                sub_str = file_content[i:i+length]
                if self.normalizer.normalize(sub_str) == norm_complete:
                    verbatim_complete = sub_str
                    end_idx = i + length
                    found_start_idx = i
                    break
            if verbatim_complete:
                break

        if not verbatim_complete:
            return None

        remaining_content = file_content[end_idx:]
        lines_after = remaining_content.splitlines(keepends=True)
        if not lines_after:
            return None

        matched_verbatim_full = verbatim_complete
        for line in lines_after:
            if not line.strip():
                matched_verbatim_full += line
                continue
            if line.strip().startswith(last_line_prefix):
                # 取得原本檔案中這一行被完全定位的字面，包含其完整的尾端
                matched_verbatim_full += line
                
                # 為了避免替換後造成檔案後面剩餘未匹配行與替換行重複 (例如 replace_text 包含了 return total，而 original 也有 return total)，
                # 如果原本檔案的下一行或兩行內容已經被 replace_text 的尾端完全覆蓋，我們在 verbatim_match 中將它們一併吞掉以防止重疊重複。
                appended_len = len(matched_verbatim_full) - len(verbatim_complete)
                actual_end_idx = end_idx + appended_len
                rest_lines = file_content[actual_end_idx:].splitlines(keepends=True)
                for next_line in rest_lines:
                    if not next_line.strip():
                        matched_verbatim_full += next_line
                        continue
                    # 確保包含縮排與空格的相容比對。
                    stripped_next = next_line.strip()
                    replace_stripped_lines = [r.strip() for r in replace_text.splitlines() if r.strip()]
                    
                    # 如果下一行已經包含在 replace_text 的尾端，將它併入 matched_verbatim_full 中整塊替換，避免尾部重疊重複
                    if stripped_next in replace_stripped_lines:
                        matched_verbatim_full += next_line
                    else:
                        break
                        
                return MatchResult(
                    strategy_name="TruncatedMatch",
                    verbatim_text=matched_verbatim_full,
                    normalized_search=complete_part + "\n" + line.rstrip()
                )
            else:
                return None

        return None


class ASTSemanticMatch:
    """Level 5: AST 語意樹拓撲匹配，最極致的 model-agnostic 格式對齊自癒"""
    def match(self, file_content: str, search_text: str, replace_text: str = "") -> Optional[MatchResult]:
        try:
            search_tree = ast.parse(search_text.strip())
            search_dump = ast.dump(search_tree, annotate_fields=False, include_attributes=False)
        except Exception:
            return None

        lines = file_content.splitlines()
        search_lines_count = len(search_text.strip().splitlines())
        
        # 滑動窗口在原始代碼中以 AST 層級比對相似結構
        for start_idx in range(len(lines) - search_lines_count + 1):
            for offset in range(-2, 3):  # 允許行數有些微浮動
                end_idx = start_idx + search_lines_count + offset
                if end_idx < start_idx or end_idx > len(lines):
                    continue
                candidate_snippet = "\n".join(lines[start_idx:end_idx])
                try:
                    candidate_tree = ast.parse(candidate_snippet.strip())
                    candidate_dump = ast.dump(candidate_tree, annotate_fields=False, include_attributes=False)
                    if candidate_dump == search_dump:
                        return MatchResult(
                            strategy_name="ASTSemanticMatch",
                            verbatim_text=candidate_snippet,
                            normalized_search=candidate_snippet
                        )
                except Exception:
                    continue
        return None


class DiffLibFuzzyMatcher:
    """Level 3.5: 基於 difflib SequenceMatcher 的空格/縮排漂移模糊自癒匹配"""
    def __init__(self, threshold: float = 0.8):
        self.threshold = threshold
        self.normalizer = Normalizer()

    def match(self, file_content: str, search_text: str, replace_text: str = "", context_hints: list[str] = None) -> Optional[MatchResult]:
        import difflib
        s_stripped = search_text.strip()
        if not s_stripped:
            return None

        from nexus.services.local_heal.closest_snippet import find_closest_snippet
        closest = find_closest_snippet(file_content, s_stripped, context_hints=context_hints)
        if not closest:
            return None

        ratio = difflib.SequenceMatcher(None, s_stripped, closest.strip()).ratio()
        if ratio >= self.threshold:
            return MatchResult(
                strategy_name="DiffLibFuzzyMatcher",
                verbatim_text=closest,
                normalized_search=s_stripped,
                similarity=ratio
            )
        return None


class MatchChain:
    """責任鏈管理器：按照複雜度與效能由低到高依序執行匹配"""
    def __init__(self, strategies: List[MatchStrategy] = None):
        if strategies is None:
            self.strategies = [
                ExactMatch(),
                StrippedMatch(),
                TruncatedMatch(),      # 優先嘗試截斷自癒，防範 NormalizedMatch 誤匹配為前半截 substring
                DiffLibFuzzyMatcher(),
                NormalizedMatch(),
                ASTSemanticMatch()
            ]
        else:
            self.strategies = strategies

    def find_match(self, file_content: str, search_text: str, replace_text: str = "", context_hints: list[str] = None) -> Optional[MatchResult]:
        for strategy in self.strategies:
            # 支援動態分發 context_hints 到支援它的策略
            if hasattr(strategy, "match"):
                import inspect
                sig = inspect.signature(strategy.match)
                if "context_hints" in sig.parameters:
                    res = strategy.match(file_content, search_text, replace_text, context_hints=context_hints)
                else:
                    res = strategy.match(file_content, search_text, replace_text)
                
                if res is not None:
                    return res
        return None


class SlidingWindowMatcher:
    """舊版滑動視窗相容接口，直接呼叫新版 NormalizedMatch"""
    def __init__(self):
        self.impl = NormalizedMatch()

    def match(self, file_content: str, search_text: str) -> Tuple[str, str]:
        res = self.impl.match(file_content, search_text)
        if res is not None:
            return res.verbatim_text, res.verbatim_text
        return "", ""

