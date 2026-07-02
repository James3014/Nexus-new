import ast
import difflib
import hashlib
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass, field
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, SyntaxGate
from nexus.services.local_heal.validator import validate_effective_change, validate_name_sanity
from nexus.services.local_heal.errors import PatchError, PatchErrorKind, MatchAuthority
from nexus.services.local_heal.interface import LocalizedFile

@dataclass
class PatchApplicationResult:
    success: bool
    applied_diffs: List[str]
    error_reason: str | None = None
    syntax_gate_passed: bool = True
    preflight_telemetry: dict = field(default_factory=dict)  # Preflight telemetry
    errors: List = field(default_factory=list)  # T1.2: PatchError objects for telemetry
    match_authority: MatchAuthority | None = None  # T3: Authority source for applied patch

class PatchApplier:
    """多重關卡修補套用與驗證器 - 依據 Linus 切小與關注點分離原則"""

    def __init__(self, parser: SolidSearchReplaceProtocol, patcher):
        self.parser = parser
        self.patcher = patcher

    def _lookup_canonical_search_span(
        self, source_text: str, failed_search: str, file_path: str
    ) -> tuple[str | None, dict]:
        """T1.4: Extract canonical SEARCH span from source file.

        Uses failed_search_text as a guide to find the best matching span
        in the canonical source. Returns (canonical_span_or_None, telemetry).

        Rules:
        - SEARCH must be exact substring of source after lookup
        - All auto-corrections are recorded in telemetry
        - Non-canonical SEARCH never enters apply
        """
        import re
        telemetry = {
            "file_path": file_path,
            "failed_search_hash": hashlib.sha256(failed_search.encode()).hexdigest()[:16],
            "lookup_attempts": [],
        }

        if not failed_search or not failed_search.strip():
            telemetry["lookup_result"] = "empty_search"
            return None, telemetry

        failed_stripped = failed_search.strip()

        # Strategy 1: Exact match of stripped text
        if failed_stripped in source_text:
            idx = source_text.index(failed_stripped)
            start_line = source_text[:idx].count("\n") + 1
            end_line = source_text[:idx + len(failed_stripped)].count("\n") + 1
            telemetry["lookup_attempts"].append({"strategy": "exact_stripped", "found": True})
            telemetry["lookup_result"] = "exact_match"
            telemetry["canonical_span_start_line"] = start_line
            telemetry["canonical_span_end_line"] = end_line
            return failed_stripped, telemetry

        # Strategy 2: Line-by-line extraction — find contiguous block in source
        # that best matches the failed search lines
        failed_lines = [l for l in failed_stripped.splitlines() if l.strip()]
        if len(failed_lines) >= 2:
            source_lines = source_text.splitlines()
            best_score = -1.0
            best_start = -1
            best_count = 0

            # Try matching first non-empty line as anchor
            for i, src_line in enumerate(source_lines):
                if not src_line.strip():
                    continue
                # Check if this line matches first failed line (normalized)
                if self._lines_match(src_line, failed_lines[0]):
                    # Extend match forward
                    match_count = 0
                    for j, fl in enumerate(failed_lines):
                        if i + j < len(source_lines) and self._lines_match(source_lines[i + j], fl):
                            match_count += 1
                        else:
                            break
                    if match_count >= max(2, len(failed_lines) * 0.5):
                        score = match_count / len(failed_lines)
                        if score > best_score:
                            best_score = score
                            best_start = i
                            best_count = match_count

            if best_start >= 0 and best_count >= 2:
                # Extract canonical block — use ALL lines from best_start to best_start+best_count
                # But also try to extend to natural boundaries (blank line, dedent, def/class)
                canonical_lines = source_lines[best_start:best_start + best_count]

                # Try to extend to full natural block (next dedent or blank line)
                extend_end = best_start + best_count
                if extend_end < len(source_lines):
                    base_indent = len(canonical_lines[0]) - len(canonical_lines[0].lstrip())
                    for k in range(extend_end, min(extend_end + 5, len(source_lines))):
                        sl = source_lines[k]
                        if not sl.strip():
                            break
                        cur_indent = len(sl) - len(sl.lstrip())
                        if cur_indent < base_indent and sl.strip():
                            break
                        canonical_lines.append(sl)
                        extend_end = k + 1

                canonical_text = "\n".join(canonical_lines)
                # Verify canonical_text is exact substring of source
                if canonical_text in source_text:
                    idx = source_text.index(canonical_text)
                    start_line = source_text[:idx].count("\n") + 1
                    end_line = source_text[:idx + len(canonical_text)].count("\n") + 1
                    similarity = best_score
                    telemetry["lookup_attempts"].append({
                        "strategy": "line_block_extraction",
                        "found": True,
                        "score": round(similarity, 3),
                        "lines_matched": best_count,
                        "lines_total": len(failed_lines),
                    })
                    telemetry["lookup_result"] = "canonical_block_found"
                    telemetry["canonical_span_start_line"] = start_line
                    telemetry["canonical_span_end_line"] = end_line
                    telemetry["canonical_span_lines"] = end_line - start_line + 1
                    telemetry["closest_match_similarity"] = round(similarity, 3)
                    return canonical_text, telemetry

        # Strategy 3: Find the single best-matching line as anchor, extract surrounding context
        source_lines = source_text.splitlines()
        best_line_idx = -1
        best_line_score = -1.0
        for i, src_line in enumerate(source_lines):
            if not src_line.strip():
                continue
            for fl in failed_lines[:5]:
                score = self._line_similarity(src_line, fl)
                if score > best_line_score:
                    best_line_score = score
                    best_line_idx = i

        if best_line_idx >= 0 and best_line_score >= 0.95:
            # Extract context around best line — try to match failed block size
            target_lines = len(failed_lines)
            start = max(0, best_line_idx - target_lines // 2)
            end = min(len(source_lines), start + target_lines + 2)
            # Extend to natural boundaries
            while start > 0 and source_lines[start - 1].strip():
                start -= 1
            while end < len(source_lines) and source_lines[end].strip():
                end += 1

            candidate = "\n".join(source_lines[start:end])
            if candidate in source_text:
                idx = source_text.index(candidate)
                s_line = source_text[:idx].count("\n") + 1
                e_line = source_text[:idx + len(candidate)].count("\n") + 1
                telemetry["lookup_attempts"].append({
                    "strategy": "anchor_context_extraction",
                    "found": True,
                    "anchor_score": round(best_line_score, 3),
                    "anchor_line": best_line_idx + 1,
                })
                telemetry["lookup_result"] = "anchor_context_found"
                telemetry["canonical_span_start_line"] = s_line
                telemetry["canonical_span_end_line"] = e_line
                telemetry["canonical_span_lines"] = e_line - s_line + 1
                telemetry["closest_match_similarity"] = round(best_line_score, 3)
                return candidate, telemetry

        # T1.8 Strategy 4: AST symbol-aware fallback
        ast_result = self._ast_symbol_fallback(source_text, failed_search, file_path)
        if ast_result:
            canonical_span, ast_telemetry = ast_result
            telemetry["lookup_attempts"].append({
                "strategy": "ast_symbol_fallback",
                "found": True,
                **ast_telemetry,
            })
            telemetry["lookup_result"] = "ast_symbol_fallback_found"
            telemetry["canonical_span_start_line"] = ast_telemetry.get("start_line", 0)
            telemetry["canonical_span_end_line"] = ast_telemetry.get("end_line", 0)
            telemetry["canonical_span_lines"] = ast_telemetry.get("end_line", 0) - ast_telemetry.get("start_line", 0) + 1
            telemetry["canonical_span_hash"] = ast_telemetry.get("span_hash", "")
            telemetry["ast_symbol_found"] = True
            telemetry["fallback_used"] = True
            telemetry["fallback_reason"] = "previous_strategies_failed"
            telemetry["canonical_span_source"] = "ast_fallback"
            return canonical_span, telemetry

        telemetry["lookup_attempts"].append({"strategy": "all_failed", "found": False})
        telemetry["lookup_result"] = "no_canonical_span_found"
        return None, telemetry

    def _ast_symbol_fallback(
        self, source_text: str, failed_search: str, file_path: str
    ) -> tuple[str | None, dict]:
        """T1.8: AST-based symbol extraction fallback.

        When line-by-line/fuzzy matching fails, use AST to find the target
        function/class by name and extract its exact canonical span.
        """
        import re
        import hashlib

        telemetry = {
            "target_symbol": "",
            "target_symbol_source": "",
            "target_symbol_confidence": "low",
            "ast_symbol_found": False,
            "ast_symbol_span_start": 0,
            "ast_symbol_span_end": 0,
            "ast_symbol_span_hash": "",
        }

        # Extract target symbol from failed_search_text
        target_symbol = self._extract_target_symbol(failed_search)
        if not target_symbol:
            telemetry["ast_symbol_found"] = False
            return None, telemetry

        telemetry["target_symbol"] = target_symbol
        telemetry["target_symbol_source"] = "failed_search_text"

        # Confidence check: only proceed if symbol appears in source
        if target_symbol not in source_text:
            telemetry["target_symbol_confidence"] = "low"
            telemetry["ast_symbol_found"] = False
            return None, telemetry

        telemetry["target_symbol_confidence"] = "medium"

        # Parse AST and find the function/class definition
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            telemetry["ast_symbol_found"] = False
            return None, telemetry

        source_lines = source_text.splitlines()
        target_node = None

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == target_symbol:
                    target_node = node
                    break

        if not target_node:
            telemetry["ast_symbol_found"] = False
            return None, telemetry

        # Extract exact span from source lines
        start_line = target_node.lineno - 1  # 0-indexed
        end_line = getattr(target_node, "end_lineno", None)
        if end_line is None:
            # Fallback: find end by dedent
            base_indent = len(source_lines[start_line]) - len(source_lines[start_line].lstrip())
            end_line = start_line + 1
            for i in range(start_line + 1, min(start_line + 200, len(source_lines))):
                line = source_lines[i]
                if not line.strip():
                    end_line = i + 1
                    continue
                cur_indent = len(line) - len(line.lstrip())
                if cur_indent <= base_indent and line.strip():
                    break
                end_line = i + 1
        else:
            end_line = end_line  # already 1-indexed from AST

        # Extract canonical span (1-indexed lines to 0-indexed slice)
        canonical_lines = source_lines[start_line:end_line]
        canonical_text = "\n".join(canonical_lines)

        # Verify it's an exact substring
        if canonical_text not in source_text:
            telemetry["ast_symbol_found"] = False
            return None, telemetry

        span_hash = hashlib.sha256(canonical_text.encode()).hexdigest()[:16]

        telemetry["ast_symbol_found"] = True
        telemetry["ast_symbol_span_start"] = start_line + 1  # 1-indexed
        telemetry["ast_symbol_span_end"] = end_line  # 1-indexed
        telemetry["ast_symbol_span_hash"] = span_hash
        telemetry["start_line"] = start_line + 1
        telemetry["end_line"] = end_line
        telemetry["span_hash"] = span_hash

        return canonical_text, telemetry

    @staticmethod
    def _extract_target_symbol(failed_search: str) -> str | None:
        """Extract function/class name from failed_search_text."""
        import re
        if not failed_search:
            return None

        # Try to find def/async def/class name
        patterns = [
            r'(?:async\s+)?def\s+(\w+)',
            r'class\s+(\w+)',
        ]
        for pattern in patterns:
            m = re.search(pattern, failed_search)
            if m:
                return m.group(1)

        # Try to find function call name (e.g., separability_matrix(model))
        m = re.search(r'(\w+)\s*\(', failed_search)
        if m:
            return m.group(1)

        return None

    @staticmethod
    def _lines_match(a: str, b: str, threshold: float = 0.8) -> bool:
        """Check if two lines are similar enough to be considered matching."""
        a_stripped = a.strip()
        b_stripped = b.strip()
        if not a_stripped or not b_stripped:
            return False
        if a_stripped == b_stripped:
            return True
        # Normalized comparison
        a_norm = " ".join(a_stripped.split())
        b_norm = " ".join(b_stripped.split())
        if a_norm == b_norm:
            return True
        return difflib.SequenceMatcher(None, a_norm, b_norm).ratio() >= threshold

    @staticmethod
    def _line_similarity(a: str, b: str) -> float:
        """Compute similarity between two lines (normalized)."""
        a_norm = " ".join(a.strip().split())
        b_norm = " ".join(b.strip().split())
        if not a_norm or not b_norm:
            return 0.0
        if a_norm == b_norm:
            return 1.0
        return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()

    def preflight_check(self, intents: list, repo_dir: Path) -> tuple[bool, str, dict]:
        """
        Preflight check before patch apply.
        Returns (passed, error_reason, telemetry)
        """
        telemetry = {"preflight_checks": []}
        
        for intent in intents:
            target_path = repo_dir / intent.file_path
            
            # Check 1: File exists
            if not target_path.exists():
                # T1.2: Track path resolution attempts
                resolution_attempts = []
                found = list(repo_dir.rglob(Path(intent.file_path).name))
                if found:
                    target_path = found[0]
                    resolution_attempts.append({"strategy": "rglob_name", "result": str(found[0])})
                else:
                    # Try relative path from repo root
                    parts = Path(intent.file_path).parts
                    if len(parts) > 1:
                        alt = repo_dir / Path(*parts[-2:])
                        if alt.exists():
                            target_path = alt
                            resolution_attempts.append({"strategy": "relative_suffix", "result": str(alt)})

                if not target_path.exists():
                    # Classify path failure
                    path_subclass = "repo_not_mounted"
                    if "reproduce_bug" in intent.file_path or "repro" in intent.file_path:
                        path_subclass = "wrong_repro_path"
                    elif not intent.file_path.strip():
                        path_subclass = "empty_path"
                    elif not any(r.get("result") for r in resolution_attempts):
                        path_subclass = "generated_wrong_path"

                    telemetry["preflight_checks"].append({
                        "check": "file_exists",
                        "passed": False,
                        "file": intent.file_path,
                        "path_subclass": path_subclass,
                        "resolution_attempts": resolution_attempts,
                    })
                    return False, f"FILE_NOT_FOUND:{intent.file_path}", telemetry
            
            # Check 2: Search text is not empty
            if not intent.search.strip():
                telemetry["preflight_checks"].append({"check": "search_not_empty", "passed": False})
                return False, "EMPTY_SEARCH_TEXT", telemetry
            
            # Check 3: Replace text is not empty
            if not intent.replace.strip():
                telemetry["preflight_checks"].append({"check": "replace_not_empty", "passed": False})
                return False, "EMPTY_REPLACE_TEXT", telemetry
            
            # Check 4: Search text has no placeholders
            placeholders = ["# ...", "// ...", "... [truncated]", "...", "…"]
            if any(ph in intent.search for ph in placeholders):
                telemetry["preflight_checks"].append({"check": "no_placeholders", "passed": False})
                return False, "SEARCH_HAS_PLACEHOLDER", telemetry
            
            # T1.3A: Syntax check — try fragment first, then full patched file
            replace_hash = hashlib.sha256(intent.replace.encode()).hexdigest()[:16]
            try:
                ast.parse(intent.replace.strip())
                telemetry["preflight_checks"].append({
                    "check": "replace_syntax",
                    "passed": True,
                    "method": "fragment_parse",
                    "replace_preview_hash": replace_hash,
                })
            except SyntaxError as fragment_err:
                # T1.3A: Fragment parse failed — try full patched file
                # This handles indented blocks (inside functions/classes) that aren't valid modules
                try:
                    source_text_for_check = target_path.read_text(encoding="utf-8", errors="replace")
                    patched_full = source_text_for_check.replace(intent.search, intent.replace)
                    patched_hash = hashlib.sha256(patched_full.encode()).hexdigest()[:16]
                    ast.parse(patched_full)
                    # Full file parses OK — the fragment just lacked context
                    telemetry["preflight_checks"].append({
                        "check": "replace_syntax",
                        "passed": True,
                        "method": "full_file_parse",
                        "fragment_error": str(fragment_err)[:200],
                        "replace_preview_hash": replace_hash,
                        "patched_file_preview_hash": patched_hash,
                    })
                except SyntaxError as full_err:
                    # Both fragment and full file fail — real syntax error
                    # Compute indentation base for diagnostics
                    replace_lines = intent.replace.splitlines()
                    indentation_base = ""
                    for line in replace_lines:
                        stripped = line.lstrip()
                        if stripped and not stripped.startswith("#"):
                            indentation_base = line[:len(line) - len(stripped)]
                            break

                    telemetry["preflight_checks"].append({
                        "check": "replace_syntax",
                        "passed": False,
                        "method": "both_failed",
                        "fragment_error": str(fragment_err)[:200],
                        "full_file_error": str(full_err)[:200],
                        "syntax_error_line": full_err.lineno,
                        "syntax_error_offset": full_err.offset,
                        "syntax_error_msg": full_err.msg[:200],
                        "replace_preview_hash": replace_hash,
                        "patched_file_preview_hash": patched_hash if 'patched_hash' in dir() else "",
                        "indentation_base": repr(indentation_base),
                    })
                    return False, f"REPLACE_SYNTAX_ERROR:{full_err}", telemetry
                except Exception:
                    # Non-syntax error in full file parse — still fail
                    telemetry["preflight_checks"].append({
                        "check": "replace_syntax",
                        "passed": False,
                        "method": "full_file_exception",
                        "fragment_error": str(fragment_err)[:200],
                        "replace_preview_hash": replace_hash,
                    })
                    return False, f"REPLACE_SYNTAX_ERROR:{fragment_err}", telemetry
            
            telemetry["preflight_checks"].append({"check": "all_passed", "passed": True, "file": intent.file_path})
        
        return True, "", telemetry

    def apply_and_validate(
        self,
        intents: list,
        repo_dir: Path,
        localized_files: List[LocalizedFile],
        match_authority: MatchAuthority | None = None
    ) -> PatchApplicationResult:
        applied_diffs = []
        syntax_gate_passed = True
        preflight_telemetry = {}

        # Run preflight check first
        passed, error_reason, preflight_telemetry = self.preflight_check(intents, repo_dir)
        if not passed:
            return PatchApplicationResult(
                success=False,
                applied_diffs=applied_diffs,
                error_reason=error_reason,
                preflight_telemetry=preflight_telemetry
            )

        # T3: Authority accumulator — tracks the highest authority across all intents.
        # Precedence: CROSS_FILE_CORRECTION > CANONICAL_RECOVERY > VERBATIM
        # Initialized outside loop so multi-intent patches preserve attribution.
        _authority_precedence = {
            MatchAuthority.VERBATIM: 0,
            MatchAuthority.CANONICAL_RECOVERY: 1,
            MatchAuthority.CROSS_FILE_CORRECTION: 2,
        }
        accumulated_authority: MatchAuthority | None = None

        for intent in intents:
            target_path = repo_dir / intent.file_path
            
            # 輔助：處理相對路徑與模糊匹配
            if not target_path.exists():
                found = list(repo_dir.rglob(Path(intent.file_path).name))
                if found:
                    target_path = found[0]

            if not target_path.exists():
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason=f"FILE_NOT_FOUND:{intent.file_path}",
                    preflight_telemetry=preflight_telemetry
                )

            source_text = target_path.read_text(encoding="utf-8", errors="replace")

            # A. [MatchGate] 逐字匹配與占位符阻斷
            match_res = self.parser.validate(intent, source_text)
            intent_authority: MatchAuthority | None = None
            if not match_res.is_valid:
                # T1.2: Capture PatchError for telemetry
                patch_errors = []
                if match_res.error:
                    patch_errors.append(match_res.error)
                # P0-3b: Cross-file SEARCH fallback
                corrected = False
                for loc_file in localized_files:
                    alt_rel_path = loc_file.path
                    alt_path = repo_dir / alt_rel_path
                    if not alt_path.exists() or alt_path == target_path:
                        continue
                    alt_text = alt_path.read_text(encoding="utf-8", errors="replace")
                    alt_res = self.parser.validate(intent, alt_text)
                    if alt_res.is_valid:
                        intent = type(intent)(
                            file_path=alt_rel_path,
                            search=intent.search,
                            replace=intent.replace,
                            operation=intent.operation,
                        )
                        target_path = alt_path
                        source_text = alt_text
                        match_res = alt_res
                        corrected = True
                        patch_errors = []
                        intent_authority = MatchAuthority.CROSS_FILE_CORRECTION
                        break
                if not corrected:
                    # P0-3b: Same-file fuzzy auto-correction is FORBIDDEN.
                    # Fuzzy candidates (even with similarity >= 0.95) must NOT
                    # auto-apply patches. Only cross-file canonical authority
                    # (already handled above in the localized_files loop) is allowed.
                    # SEARCH_MISMATCH with requires_authority=True is the fail-closed path.
                    # No authority found — return SEARCH_MISMATCH
                    if match_res.error:
                        existing_telemetry = dict(getattr(match_res.error, "telemetry", None) or {})
                        existing_telemetry["requires_authority"] = True
                        match_res.error.telemetry = existing_telemetry
                    return PatchApplicationResult(
                        success=False,
                        applied_diffs=applied_diffs,
                        error_reason=match_res.error.kind.name if match_res.error else "SEARCH_MISMATCH",
                        preflight_telemetry=preflight_telemetry,
                        errors=patch_errors,
                    )

            # B. [SyntaxGate] 語法編譯檢查 (ast.parse)
            syntax_res = SyntaxGate.check(intent, source_text)
            syntax_gate_passed = syntax_res.is_valid
            if not syntax_res.is_valid:
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason=syntax_res.error.kind.name,
                    syntax_gate_passed=False,
                    preflight_telemetry=preflight_telemetry
                )

            # C. [SemanticsGate] 語意安全檢查 (空改動與 NameSanity)
            patched_content = source_text.replace(intent.search, intent.replace)
            
            is_effective, eff_err = validate_effective_change(source_text, patched_content)
            if not is_effective:
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason="NO_EFFECTIVE_CHANGE",
                    preflight_telemetry=preflight_telemetry
                )

            is_sane, sane_err = validate_name_sanity(patched_content)
            if not is_sane:
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason="NAME_SANITY_ERROR",
                    preflight_telemetry=preflight_telemetry
                )

            # D. 寫入檔案與紀錄 unified diff
            target_path.write_text(patched_content, encoding="utf-8")
            diff = self._build_file_diff(intent.file_path, source_text, patched_content)
            applied_diffs.append(diff)

            # T3: Determine match_authority if not already set (cross-file)
            # If caller explicitly passes match_authority, it takes precedence
            # (this ensures FUZZY_CANDIDATE_ONLY is never silently overridden)
            if match_authority is not None:
                intent_authority = match_authority
            elif intent_authority is None:
                if match_res.telemetry and "match_authority" in match_res.telemetry:
                    intent_authority = match_res.telemetry["match_authority"]
                elif match_res.telemetry and match_res.telemetry.get("canonical_span", {}).get("auto_corrected", False):
                    intent_authority = MatchAuthority.CANONICAL_RECOVERY
                else:
                    intent_authority = MatchAuthority.VERBATIM

            # T3: Accumulate highest authority across all intents
            if accumulated_authority is None:
                accumulated_authority = intent_authority
            elif intent_authority is not None:
                intent_prec = _authority_precedence.get(intent_authority, -1)
                accum_prec = _authority_precedence.get(accumulated_authority, -1)
                if intent_prec > accum_prec:
                    accumulated_authority = intent_authority

        # T3: Fail-closed invariant — FUZZY_CANDIDATE_ONLY must never appear on success=True
        if accumulated_authority == MatchAuthority.FUZZY_CANDIDATE_ONLY:
            raise AssertionError(
                "INVARIANT VIOLATION: FUZZY_CANDIDATE_ONLY cannot be set on success=True"
            )

        # T3: Success attribution invariant — authority must never be None on success
        if accumulated_authority is None:
            raise AssertionError(
                "INVARIANT VIOLATION: match_authority must not be None on success=True"
            )

        return PatchApplicationResult(
            success=True,
            applied_diffs=applied_diffs,
            syntax_gate_passed=syntax_gate_passed,
            preflight_telemetry=preflight_telemetry,
            match_authority=accumulated_authority,
        )

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
        ))
