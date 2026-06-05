import re
from typing import List, Dict, Tuple, Any
from pathlib import Path

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
