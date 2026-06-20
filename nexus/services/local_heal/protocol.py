from dataclasses import dataclass
import re
import ast
from typing import List, Tuple, Dict, Any
from nexus.services.local_heal.errors import PatchError, PatchErrorKind, PatchMismatchSubclass
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
        import hashlib
        placeholders = ["# ...", "// ...", "... [truncated]", "...", "…"]
        if any(ph in intent.search for ph in placeholders) or any(ph in intent.replace for ph in placeholders):
            return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SEARCH_HAS_PLACEHOLDER, message="Placeholders detected."))

        source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]
        search_stripped = intent.search.strip()
        search_in_source = search_stripped in source_text

        # T1.2: Record canonical span telemetry
        canonical_span_telemetry = {
            "source_hash": source_hash,
            "search_length": len(search_stripped),
            "search_in_source_exact": search_in_source,
            "source_length": len(source_text),
        }

        if search_in_source:
            idx = source_text.index(search_stripped)
            start_line = source_text[:idx].count("\n") + 1
            end_line = source_text[:idx + len(search_stripped)].count("\n") + 1
            canonical_span_telemetry["canonical_line_start"] = start_line
            canonical_span_telemetry["canonical_line_end"] = end_line
            return ValidationResult(is_valid=True, telemetry={"canonical_span": canonical_span_telemetry, "auto_corrected": False})

        # 容錯：移除 SEARCH 塊末尾可能多餘的空行再試一次
        if intent.search.rstrip() in source_text:
            intent.search = intent.search.rstrip()
            canonical_span_telemetry["auto_corrected"] = True
            canonical_span_telemetry["correction"] = "trailing_whitespace_strip"
            return ValidationResult(is_valid=True, telemetry={"canonical_span": canonical_span_telemetry, "auto_corrected": True})
            
        # T1.3B: Enhanced fuzzy fallback - record candidate but do NOT pass gate
        from nexus.services.local_heal.matcher import MatchChain
        match_res = MatchChain().find_match(source_text, intent.search, intent.replace)
        if match_res is not None and match_res.similarity >= 0.75:
            original_search_hash = hashlib.sha256(intent.search.encode()).hexdigest()[:16]
            canonical_search_hash = hashlib.sha256(match_res.verbatim_text.encode()).hexdigest()[:16]

            subclass = self._classify_mismatch_subclass(intent.search, match_res, source_text)
            canonical_span_telemetry["auto_corrected"] = False
            canonical_span_telemetry["correction"] = f"fuzzy_candidate:{match_res.strategy_name}:{match_res.similarity:.3f}"
            canonical_span_telemetry["original_failed_search_hash"] = original_search_hash
            canonical_span_telemetry["canonical_search_hash"] = canonical_search_hash
            canonical_span_telemetry["fuzzy_candidate_text"] = match_res.verbatim_text[:500]

            if match_res.verbatim_text in source_text:
                idx = source_text.index(match_res.verbatim_text)
                canonical_span_telemetry["candidate_line_start"] = source_text[:idx].count("\n") + 1
                canonical_span_telemetry["candidate_line_end"] = source_text[:idx + len(match_res.verbatim_text)].count("\n") + 1

            patch_error = PatchError(
                kind=PatchErrorKind.SEARCH_MISMATCH,
                message=f"Fuzzy candidate found (similarity={match_res.similarity:.3f}) but not verbatim - requires canonical authority",
                mismatch_subclass=subclass,
                file_path=intent.file_path,
                failed_search_text=intent.search[:500],
                closest_match=match_res.verbatim_text,
                telemetry={
                    "canonical_span": canonical_span_telemetry,
                    "fuzzy_strategy": match_res.strategy_name,
                    "fuzzy_similarity": match_res.similarity,
                    "requires_authority": True,
                },
            )
            return ValidationResult(is_valid=False, error=patch_error, telemetry={
                "canonical_span": canonical_span_telemetry,
                "fuzzy_strategy": match_res.strategy_name,
                "fuzzy_similarity": match_res.similarity,
            })
            
        # Classify mismatch subclass for failed match
        subclass = self._classify_mismatch_subclass(intent.search, match_res, source_text)
        canonical_span_telemetry["auto_corrected"] = False

        # T1.2: Enrich telemetry with closest match info
        closest_telemetry = {}
        if match_res is not None:
            closest_telemetry = {
                "closest_strategy": match_res.strategy_name,
                "closest_similarity": match_res.similarity,
                "closest_snippet_length": len(match_res.verbatim_text),
                "closest_snippet_preview": match_res.verbatim_text[:200],
            }
            # T1.3B: Compute resolved_span from closest match
            if match_res.verbatim_text in source_text:
                idx = source_text.index(match_res.verbatim_text)
                start_line = source_text[:idx].count("\n") + 1
                end_line = source_text[:idx + len(match_res.verbatim_text)].count("\n") + 1
                closest_telemetry["resolved_span"] = f"L{start_line}-L{end_line}"
                closest_telemetry["resolved_span_lines"] = end_line - start_line + 1

        # T1.2: Populate PatchError with file_path and failed_search_text
        validate_telemetry = {
            "canonical_span": canonical_span_telemetry,
            "closest_match": closest_telemetry,
        }
        patch_error = PatchError(
            kind=PatchErrorKind.SEARCH_MISMATCH,
            message=f"SEARCH mismatch in {intent.file_path}",
            mismatch_subclass=subclass,
            file_path=intent.file_path,
            failed_search_text=intent.search[:500],
            telemetry=validate_telemetry,
        )

        return ValidationResult(is_valid=False, error=patch_error, telemetry={
            "canonical_span": canonical_span_telemetry,
            "closest_match": closest_telemetry,
        })

    def _classify_mismatch_subclass(self, search_text: str, match_res, source_text: str) -> PatchMismatchSubclass:
        """Classify the specific type of search mismatch."""
        if match_res is None:
            # No match found at all
            return PatchMismatchSubclass.VERBATIM_SEARCH_MISMATCH
        
        strategy = match_res.strategy_name
        similarity = match_res.similarity
        
        # Check if it's a normalization drift (matched after normalization but not verbatim)
        if strategy in ("NormalizedMatch", "DiffLibFuzzyMatcher"):
            if similarity < 0.95:
                return PatchMismatchSubclass.SEARCH_NORMALIZATION_DRIFT
        
        # Check if it's a false friend (close but wrong location)
        if strategy == "DiffLibFuzzyMatcher" and similarity >= 0.85:
            # Check if the match is in a different function/class scope
            search_lines = search_text.strip().splitlines()
            match_lines = match_res.verbatim_text.strip().splitlines()
            if len(search_lines) > 2 and len(match_lines) > 2:
                # Simple heuristic: if first/last lines differ significantly, it's a wrong span
                if search_lines[0].strip() != match_lines[0].strip():
                    return PatchMismatchSubclass.WRONG_TARGET_SPAN
            return PatchMismatchSubclass.CLOSEST_SNIPPET_FALSE_FRIEND
        
        # Default to verbatim mismatch
        return PatchMismatchSubclass.VERBATIM_SEARCH_MISMATCH

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
