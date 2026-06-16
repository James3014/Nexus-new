from dataclasses import dataclass
import re
import ast
from typing import List, Tuple, Dict, Any
from nexus.services.local_heal.errors import PatchError, PatchErrorKind
from nexus.services.local_heal.validator import validate_syntax

@dataclass
class PatchIntent:
    file_path: str
    search: str
    replace: str
    operation: str = "replace"

@dataclass
class ValidationResult:
    is_valid: bool
    error: PatchError | None = None
    telemetry: Dict[str, Any] | None = None

class SolidSearchReplaceProtocol:
    """
    🛡️ Solid SEARCH/REPLACE Protocol (v1.1 Hardened)
    支援單一文件多區塊解析，並對拒答與占位符實施嚴格門禁。
    """
    
    def __init__(self):
        # 匹配 FILE 表頭 (容許前方有些微格式，如 ```python\n)
        self.file_pattern = re.compile(r'^(?:```\w*\n)?FILE:\s*([^\n]+)', re.MULTILINE)
        # 匹配 SEARCH/REPLACE 區塊
        self.sr_pattern = re.compile(
            r'<<<<<<< SEARCH\s*\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE', 
            re.DOTALL
        )
        
    def detect_refusal(self, raw_output: str) -> bool:
        refusal_keywords = ["i apologize", "i cannot", "i'm sorry", "sorry", "as an ai", "unfortunately"]
        lower_output = raw_output.lower()
        return any(kw in lower_output for kw in refusal_keywords) and "<<<<<<< SEARCH" not in raw_output

    def parse(self, raw_output: str) -> List[PatchIntent] | PatchError:
        if not raw_output or not raw_output.strip():
            return PatchError(kind=PatchErrorKind.EMPTY_RESPONSE, message="LLM output is empty.")
            
        if self.detect_refusal(raw_output):
            return PatchError(kind=PatchErrorKind.REFUSAL_DETECTED, message="LLM refused fix.")
            
        # 1. 依照 FILE: 切分段落
        file_sections = self.file_pattern.split(raw_output)
        # result looks like: ["junk before", "path1", "content1", "path2", "content2"]
        
        intents = []
        if len(file_sections) >= 2:
            for i in range(1, len(file_sections), 2):
                file_path = file_sections[i].strip()
                content = file_sections[i+1]
                
                for match in self.sr_pattern.finditer(content):
                    intents.append(PatchIntent(
                        file_path=file_path,
                        search=match.group(1),
                        replace=match.group(2)
                    ))
        
        # 2. 嘗試無 FILE 的 fallback (針對 14b 可能省略 header 的情況)
        if not intents and len(file_sections) < 2:
            fallback_res = self._parse_no_header_fallback(raw_output)
            if not isinstance(fallback_res, PatchError):
                intents = fallback_res

        # 3. 舊版簡約格式的相容 Fallback (SEARCH:/REPLACE:/END)
        if not intents:
            simple_pattern = re.compile(r'FILE:\s*([^\n]+)\s*\nSEARCH:\s*(?:\n)?(.*?)\nREPLACE:\s*(?:\n)?(.*?)(?:\nEND\s*|$)', re.DOTALL)
            for match in simple_pattern.finditer(raw_output):
                intents.append(PatchIntent(
                    file_path=match.group(1).strip(),
                    search=match.group(2),
                    replace=match.group(3)
                ))
        
        if not intents:
            return PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="No valid SEARCH/REPLACE blocks parsed.")
        return intents

    def _parse_no_header_fallback(self, raw: str) -> List[PatchIntent] | PatchError:
        # 如果模型只噴了區塊但沒噴 FILE，且只有一個檔案被定位，我們嘗試自動補全
        intents = []
        for match in self.sr_pattern.finditer(raw):
            intents.append(PatchIntent(
                file_path="UNKNOWN_PENDING", # 由 PatchSynthesisPhase 根據 Context 補全
                search=match.group(1),
                replace=match.group(2)
            ))
        if not intents:
            return PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="Missing FILE header and blocks.")
        return intents

    def validate(self, intent: PatchIntent, source_text: str) -> ValidationResult:
        placeholders = ["# ...", "// ...", "... [truncated]", "...", "…"]
        if any(ph in intent.search for ph in placeholders) or any(ph in intent.replace for ph in placeholders):
            return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SEARCH_HAS_PLACEHOLDER, message="Placeholders detected."))

        # 逐字匹配
        if intent.search not in source_text:
            # 容錯：移除 SEARCH 塊末尾可能多餘的空行再試一次
            if intent.search.rstrip() in source_text:
                intent.search = intent.search.rstrip()
                return ValidationResult(is_valid=True)
                
            # P0-1: 整合 MatchChain fuzzy fallback
            from nexus.services.local_heal.matcher import MatchChain
            match_res = MatchChain().find_match(source_text, intent.search, intent.replace)
            if match_res is not None and match_res.similarity >= 0.85:
                intent.search = match_res.verbatim_text
                return ValidationResult(is_valid=True, telemetry={"strategy_used": match_res.strategy_name, "similarity": match_res.similarity})
                
            return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SEARCH_MISMATCH, message=f"SEARCH mismatch in {intent.file_path}"))
            
        return ValidationResult(is_valid=True)

class SyntaxGate:
    @staticmethod
    def check(intent: PatchIntent, source_text: str) -> ValidationResult:
        try:
            patched_text = source_text.replace(intent.search, intent.replace)
            success, msg = validate_syntax(patched_text)
            if not success:
                return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message=msg))
            return ValidationResult(is_valid=True)
        except Exception as e:
            return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SYNTAX_ERROR, message=str(e)))
