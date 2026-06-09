import re
from typing import List, Dict, Tuple, Any
from pathlib import Path

from nexus.services.local_heal.protocol import PatchIntent, ValidationResult
from nexus.services.local_heal.errors import PatchError, PatchErrorKind

class SearchReplaceParser:
    def _clean_content(self, text: str) -> Tuple[str, bool]:
        cleaned = re.sub(r'```[a-zA-Z0-9]*\n?', '', text).strip()
        has_placeholder = any(ph in cleaned for ph in ("# ...", "// ...", "... existing", "... [truncated]", "...", "…"))
        return cleaned, has_placeholder

    def parse_blocks(self, llm_output: str) -> List[Dict[str, Any]]:
        # 預處理：清理常見的格式錯誤
        llm_output = llm_output.replace("````python", "```python").replace("````", "```")
        # 處理模型誤用的自定義分隔符 (如 Attempt 2 中的情況)
        if "<<<<<<< SEARCH" in llm_output and ">>>>>>> REPLACE" in llm_output and "=======" not in llm_output:
            llm_output = llm_output.replace(">>>>>>> REPLACE", "\n=======\n>>>>>>> REPLACE")

        blocks = []

        create_pattern = re.compile(
            r'CREATE FILE:\s*([^\n]+)\s*\n<<<<<<< CONTENT\s*\n(.*?)\n>>>>>>>\s*CONTENT',
            re.DOTALL
        )
        for match in create_pattern.finditer(llm_output):
            content, has_placeholder = self._clean_content(match.group(2))
            blocks.append({
                "operation": "create",
                "file": match.group(1).strip(),
                "search": "",
                "replace": content,
                "has_placeholder": has_placeholder,
            })

        # 1. 支援 Aider 格式 (嚴格模式)
        aider_pattern = re.compile(r'FILE:\s*([^\n]+).*?<<<<<<< SEARCH\s*\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE', re.DOTALL)
        for match in aider_pattern.finditer(llm_output):
            search_content, has_ph_s = self._clean_content(match.group(2))
            replace_content, has_ph_r = self._clean_content(match.group(3))
            blocks.append({"operation": "replace", "file": match.group(1).strip(), "search": search_content, "replace": replace_content, "has_placeholder": has_ph_s or has_ph_r})

        if not blocks:
            # 2. 支援簡約格式
            simple_pattern = re.compile(r'FILE:\s*([^\n]+)\s*\nSEARCH:\s*(?:\n)?(.*?)\nREPLACE:\s*(?:\n)?(.*?)(?:\nEND\s*|$)', re.DOTALL)
            for match in simple_pattern.finditer(llm_output):
                search_content, has_ph_s = self._clean_content(match.group(2))
                replace_content, has_ph_r = self._clean_content(match.group(3))
                blocks.append({"operation": "replace", "file": match.group(1).strip(), "search": search_content, "replace": replace_content, "has_placeholder": has_ph_s or has_ph_r})

        if not blocks:
            # 3. 支援全檔替換格式 (Markdown Block after FILE:)
            # 排除已經含有 SEARCH/REPLACE 標記的區塊，避免重複解析
            block_pattern = re.compile(r'FILE:\s*([^\n]+).*?```[a-zA-Z0-9]*\n(.*?)\n```', re.DOTALL)
            for match in block_pattern.finditer(llm_output):
                if "<<<<<<< SEARCH" in match.group(2): continue
                content, has_placeholder = self._clean_content(match.group(2))
                blocks.append({
                    "operation": "replace",
                    "file": match.group(1).strip(),
                    "search": "WHOLE_FILE",
                    "replace": content,
                    "has_placeholder": has_placeholder
                })

        return blocks

    def parse(self, raw_output: str) -> List[PatchIntent] | PatchError:
        if not raw_output or not raw_output.strip():
            return PatchError(kind=PatchErrorKind.EMPTY_RESPONSE, message="LLM output is empty.")
            
        refusal_keywords = ["i apologize", "i cannot", "i'm sorry", "sorry", "as an ai", "unfortunately"]
        if any(kw in raw_output.lower() for kw in refusal_keywords) and "<<<<<<< SEARCH" not in raw_output:
            return PatchError(kind=PatchErrorKind.REFUSAL_DETECTED, message="LLM refused fix.")

        blocks = self.parse_blocks(raw_output)
        if not blocks:
            return PatchError(kind=PatchErrorKind.NO_BLOCKS_FOUND, message="No valid SEARCH/REPLACE blocks parsed.")
        
        intents = []
        for b in blocks:
            intents.append(PatchIntent(
                file_path=b["file"],
                search=b["search"],
                replace=b["replace"],
                operation=b.get("operation", "replace")
            ))
        return intents

    def validate(self, intent: PatchIntent, source_text: str) -> ValidationResult:
        placeholders = ["# ...", "// ...", "... [truncated]", "...", "…"]
        if any(ph in intent.search for ph in placeholders) or any(ph in intent.replace for ph in placeholders):
            return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SEARCH_HAS_PLACEHOLDER, message="Placeholders detected."))

        if intent.search == "WHOLE_FILE":
            return ValidationResult(is_valid=True)

        if intent.search not in source_text:
            if intent.search.rstrip() in source_text:
                intent.search = intent.search.rstrip()
                return ValidationResult(is_valid=True)
            return ValidationResult(is_valid=False, error=PatchError(kind=PatchErrorKind.SEARCH_MISMATCH, message=f"SEARCH mismatch in {intent.file_path}"))
            
        return ValidationResult(is_valid=True)

    def apply_and_diff(self, file_path: Path, search_text: str, replace_text: str) -> Tuple[bool, str]:
        """舊版相容接口，直接呼叫新版 Patcher"""
        from nexus.services.local_heal.patcher import Patcher
        patcher = Patcher()
        file_content = file_path.read_text(encoding="utf-8", errors="replace")
        res = patcher.apply_patch(file_content, search_text, replace_text)
        if res.success:
            file_path.write_text(res.new_content, encoding="utf-8")
            
            import difflib
            orig_lines = file_content.splitlines(keepends=True)
            new_lines = res.new_content.splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                orig_lines, new_lines,
                fromfile=f"a/{file_path.name}",
                tofile=f"b/{file_path.name}",
                lineterm='\n'
            ))
            return True, "".join(diff_lines)
        return False, res.error_message or "Verbatim mismatch"
