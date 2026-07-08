from dataclasses import dataclass
import re
import ast
from typing import List, Tuple, Dict, Any
from nexus.services.local_heal.errors import PatchError, PatchErrorKind, PatchMismatchSubclass
from nexus.services.local_heal.validator import validate_syntax
from nexus.services.local_heal.output_understanding import _detect_format, OutputFormat

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

    @staticmethod
    def classify_format(raw: str) -> str:
        # P1.5: Delegate to canonical _detect_format() first
        detected = _detect_format(raw)

        # Map OutputFormat enum to protocol.py string labels
        _format_map = {
            OutputFormat.EMPTY_OR_REFUSAL: None,  # handled below
            OutputFormat.UNIFIED_DIFF: "UNIFIED_DIFF",
            OutputFormat.FENCED_SEARCH_REPLACE: "FENCED_SEARCH_REPLACE",
            OutputFormat.SEARCH_REPLACE: "VALID_SEARCH_REPLACE",
            OutputFormat.MALFORMED_OUTPUT: None,  # fall through to sub-classification
        }

        if detected == OutputFormat.EMPTY_OR_REFUSAL:
            if not raw or not raw.strip():
                return "EMPTY"
            return "REFUSAL"

        if detected in _format_map and _format_map[detected] is not None:
            return _format_map[detected]

        # MALFORMED_OUTPUT: fall through to existing sub-classification
        if not raw or not raw.strip():
            return "EMPTY"

        # Refusal check (redundant safety net)
        refusal_keywords = ["i apologize", "i cannot", "i'm sorry", "sorry", "as an ai", "unfortunately", "llm refused fix", "cannot fulfill"]
        lower_raw = raw.lower()
        if any(kw in lower_raw for kw in refusal_keywords) and "<<<<<<< SEARCH" not in raw:
            return "REFUSAL"

        # Check for unified diff headers or hunks
        has_diff_headers = ("--- a/" in raw and "+++ b/" in raw) or ("--- " in raw and "+++ " in raw)
        has_hunk = "@@ " in raw
        if has_diff_headers or (has_hunk and ("---" in raw or "+++" in raw)):
            return "UNIFIED_DIFF"

        # Check for SSRP
        has_search = "<<<<<<< SEARCH" in raw
        has_replace = ">>>>>>> REPLACE" in raw
        if has_search and has_replace:
            if "```" in raw:
                return "FENCED_SEARCH_REPLACE"
            return "VALID_SEARCH_REPLACE"

        if has_search or has_replace:
            return "MALFORMED_SEARCH_REPLACE"

        if "```" in raw:
            return "MARKDOWN_FENCED"

        # Code indicators for plain_text vs natural_language
        code_keywords = ["def ", "import ", "class ", "return ", "const ", "let ", "function ", "var ", "sys.", "os.", "print("]
        if any(kw in raw for kw in code_keywords) or ("=" in raw and len(raw.splitlines()) > 1):
            return "PLAIN_TEXT"

        return "NATURAL_LANGUAGE"


    def parse(self, raw_output: str, anchor_text: str = None, protocol_mode: str | None = None) -> List[PatchIntent] | PatchError:
        if not raw_output or not raw_output.strip():
            return PatchError(kind=PatchErrorKind.EMPTY_RESPONSE, message="LLM output is empty.")
            
        if self.detect_refusal(raw_output):
            return PatchError(kind=PatchErrorKind.REFUSAL_DETECTED, message="LLM refused fix.")
            
        if protocol_mode is None:
            import os
            protocol_mode = os.getenv("NEXUS_PROTOCOL_MODE", "standard")

        if protocol_mode == "anchored_edit" and anchor_text is not None:
            # 1. 嘗試解析為單純的 REPLACE 區塊，若有的話
            replace_pattern = re.compile(r'<<<<<<< REPLACE\s*\n(.*?)\n>>>>>>> REPLACE', re.DOTALL)
            match = replace_pattern.search(raw_output)
            if match:
                replacement = match.group(1)
            else:
                # 2. 相容舊版簡約的 REPLACE 格式
                replace_simple = re.compile(r'REPLACE:\s*(?:\n)?(.*?)(?:\nEND\s*|$)', re.DOTALL)
                match_simple = replace_simple.search(raw_output)
                if match_simple:
                    replacement = match_simple.group(1)
                else:
                    # 3. 嘗試找標準的 SEARCH/REPLACE 結構中的 REPLACE 部分
                    standard_match = self.sr_pattern.search(raw_output)
                    if standard_match:
                        replacement = standard_match.group(2)
                    else:
                        # P9: Detect markdown fences BEFORE stripping
                        raw_stripped = raw_output.strip()
                        if AnchoredEditReplacementGuard.MARKDOWN_FENCE_PATTERN.match(raw_stripped):
                            lines = raw_stripped.splitlines()
                            if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                                # Reject — markdown fence wrapping is not allowed
                                return PatchError(
                                    kind=PatchErrorKind.REPLACEMENT_MARKDOWN_FENCE,
                                    message="Replacement is wrapped in markdown code fences."
                                )
                        # 4. Fallback: treat entire output as replacement
                        replacement = raw_stripped

            # P9: Strict replacement-only validation
            is_clean, error_kind, error_msg = AnchoredEditReplacementGuard.validate_replacement(
                replacement,
                anchor_text,
                expected_ast_valid=True,
            )
            if not is_clean:
                return PatchError(kind=error_kind, message=error_msg)

            # 提取 FILE 表頭 (若有)
            file_match = self.file_pattern.search(raw_output)
            file_path = file_match.group(1).strip() if file_match else "UNKNOWN_PENDING"

            return [PatchIntent(
                file_path=file_path,
                search=anchor_text,
                replace=replacement
            )]

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
        import os
        protocol_mode = os.getenv("NEXUS_PROTOCOL_MODE", "standard")

        if protocol_mode == "anchored_edit":
            from nexus.services.local_heal.errors import MatchAuthority
            # 1. 拒絕空 replacement
            if not intent.replace or not intent.replace.strip():
                return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.PATCH_EMPTY, message="Replacement is empty.", file_path=intent.file_path))
            # 2. 拒絕 out-of-range 或 mismatch
            if intent.search not in source_text:
                return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SEARCH_MISMATCH, message="Anchor text not found in source.", file_path=intent.file_path))
            # 3. 確保單一匹配防止多重匹配引發歧義
            if source_text.count(intent.search) > 1:
                return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.NAME_SANITY_ERROR, message="Ambiguous anchor: multiple occurrences in source.", file_path=intent.file_path))

            # 構造 telemetry
            source_hash = hashlib.sha256(source_text.encode()).hexdigest()[:16]
            canonical_span_telemetry = {
                "source_hash": source_hash,
                "search_length": len(intent.search),
                "search_in_source_exact": True,
                "source_length": len(source_text),
                "model_generated_search": False,
            }
            
            idx = source_text.index(intent.search)
            canonical_span_telemetry["canonical_line_start"] = source_text[:idx].count("\n") + 1
            canonical_span_telemetry["canonical_line_end"] = source_text[:idx + len(intent.search)].count("\n") + 1

            return ValidationResult(
                is_valid=True,
                telemetry={
                    "canonical_span": canonical_span_telemetry,
                    "auto_corrected": False,
                    "match_authority": MatchAuthority.CONTROL_PLANE_VERBATIM,
                    "protocol_mode": "anchored_edit"
                }
            )

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
        
        import os
        protocol_mode = os.getenv("NEXUS_PROTOCOL_MODE", "standard")
        
        if match_res is not None and match_res.similarity >= 0.75:
            if protocol_mode == "control_plane_search_model_replace":
                from nexus.services.local_heal.errors import MatchAuthority
                intent.search = match_res.verbatim_text
                canonical_span_telemetry["auto_corrected"] = True
                canonical_span_telemetry["correction"] = f"control_plane_override:{match_res.strategy_name}:{match_res.similarity:.3f}"
                
                idx = source_text.index(match_res.verbatim_text)
                canonical_span_telemetry["canonical_line_start"] = source_text[:idx].count("\n") + 1
                canonical_span_telemetry["canonical_line_end"] = source_text[:idx + len(match_res.verbatim_text)].count("\n") + 1
                
                return ValidationResult(
                    is_valid=True,
                    telemetry={
                        "canonical_span": canonical_span_telemetry,
                        "auto_corrected": True,
                        "match_authority": MatchAuthority.CONTROL_PLANE_VERBATIM,
                        "protocol_mode": "control_plane_search_model_replace"
                    }
                )
            
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

class AnchoredEditReplacementGuard:
    """Strict replacement-only validation for anchored_edit mode.

    Rejects prose contamination, markdown fences, bullet lists, explanation
    paragraphs, and mixed natural language + code blocks.
    """

    PROSE_PATTERNS = [
        re.compile(r'(?i)^#\s*(here\s+is|this\s+is|the\s+fix|the\s+patch|the\s+replacement)'),
        re.compile(r'(?i)^[-*]\s+(here|this|the|note|see|consider|we|you|the\s+fix)'),
        re.compile(r'(?i)^>\s*(here|this|the|note|see|consider|we|you)'),
        re.compile(r'(?i)^(here\s+is\s+the|this\s+replaces|the\s+following|note\s*:|warning\s*:)'),
        re.compile(r'(?i)^(in\s+summary|in\s+conclusion|to\s+fix|to\s+resolve|the\s+issue)'),
        re.compile(r'(?i)^(the\s+fix\s+involves|the\s+change|this\s+fix|this\s+patch|this\s+change)'),
        re.compile(r'(?i)^(we\s+need\s+to|we\s+should|you\s+should|you\s+need\s+to)'),
        re.compile(r'(?i)^(ensure\s+that|make\s+sure|note\s+that|remember\s+that)'),
        re.compile(r'(?i)^(this\s+ensures|this\s+prevents|this\s+avoids|this\s+fixes)'),
    ]

    MARKDOWN_FENCE_PATTERN = re.compile(
        r'^```[\w]*\n', re.MULTILINE
    )

    @classmethod
    def validate_replacement(
        cls,
        replacement: str,
        anchor_text: str,
        *,
        expected_ast_valid: bool = True,
    ) -> tuple[bool, PatchErrorKind | None, str]:
        """Validate replacement text for anchored_edit mode.

        Returns (is_valid, error_kind, message).
        """
        stripped = replacement.strip()

        # 1. Empty replacement
        if not stripped:
            return False, PatchErrorKind.REPLACEMENT_EMPTY, "Replacement is empty after stripping."

        # 2. Markdown fence wrapping
        if cls.MARKDOWN_FENCE_PATTERN.match(stripped):
            lines = stripped.splitlines()
            if len(lines) >= 2 and lines[-1].strip().startswith("```"):
                return False, PatchErrorKind.REPLACEMENT_MARKDOWN_FENCE, (
                    "Replacement is wrapped in markdown code fences."
                )

        # 3. Prose contamination — check each line
        for line in stripped.splitlines():
            for pattern in cls.PROSE_PATTERNS:
                if pattern.match(line):
                    return False, PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION, (
                        f"Replacement contains prose: {line.strip()[:80]}"
                    )

        # 4. Mixed natural language + code: if >30% of non-empty lines start with
        #    natural language markers, it's prose contamination
        non_empty_lines = [l for l in stripped.splitlines() if l.strip()]
        if non_empty_lines:
            prose_markers = re.compile(
                r'(?i)^\s*(here|this|the|note|see|consider|we|you|fix|patch|change|add|remove|update|import|def|class|return|if|for|while|try|except|with|raise|assert|print|from)\b'
            )
            code_lines = sum(1 for l in non_empty_lines if prose_markers.match(l))
            code_lines += sum(1 for l in non_empty_lines if l.strip().startswith('#'))
            # If less than 40% look like code, it's probably prose
            if code_lines / len(non_empty_lines) < 0.4:
                return False, PatchErrorKind.REPLACEMENT_PROSE_CONTAMINATION, (
                    f"Replacement appears to be natural language ({code_lines}/{len(non_empty_lines)} code-like lines)."
                )

        # 5. AST validity check
        if expected_ast_valid:
            try:
                ast.parse(stripped)
            except SyntaxError:
                # Try wrapping in a function to check indented blocks
                try:
                    ast.parse(f"def _wrapper():\n" + "\n".join(f"    {l}" for l in stripped.splitlines()))
                except SyntaxError as e:
                    return False, PatchErrorKind.REPLACEMENT_SYNTAX_INVALID, (
                        f"Replacement is not syntactically valid: {e}"
                    )

        return True, None, ""


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
