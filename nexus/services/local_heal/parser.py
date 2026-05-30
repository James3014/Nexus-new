import re
from typing import List, Dict

class SearchReplaceParser:
    """單一功能：解析 LLM 輸出的 SEARCH/REPLACE 語法區塊 (SRP)"""

    def parse_blocks(self, llm_output: str) -> List[Dict[str, str]]:
        blocks = []
        
        # 1. Custom 格式解析
        custom_pattern = re.compile(
            r'FILE:\s*([^\n]+)\s*\n'
            r'SEARCH:\s*\n(.*?)\nREPLACE:\s*\n(.*?)\nEND',
            re.DOTALL
        )
        for match in custom_pattern.finditer(llm_output):
            search_content = match.group(2)
            replace_content = match.group(3)
            search_content = re.sub(r'^```[a-zA-Z0-9]*\n', '', search_content)
            search_content = re.sub(r'\n```$', '', search_content)
            replace_content = re.sub(r'^```[a-zA-Z0-9]*\n', '', replace_content)
            replace_content = re.sub(r'\n```$', '', replace_content)
            blocks.append({
                "file": match.group(1).strip(),
                "search": search_content,
                "replace": replace_content
            })
            
        # 2. Aider 格式解析
        aider_pattern = re.compile(
            r'FILE:\s*([^\n]+)\s*\n'
            r'<<<<<<< SEARCH\s*\n(.*?)\n=======\n(.*?)\n>>>>>>>(?:\s*REPLACE)?',
            re.DOTALL
        )
        for match in aider_pattern.finditer(llm_output):
            search_content = match.group(2)
            replace_content = match.group(3)
            search_content = re.sub(r'^```[a-zA-Z0-9]*\n', '', search_content)
            search_content = re.sub(r'\n```$', '', search_content)
            replace_content = re.sub(r'^```[a-zA-Z0-9]*\n', '', replace_content)
            replace_content = re.sub(r'\n```$', '', replace_content)
            blocks.append({
                "file": match.group(1).strip(),
                "search": search_content,
                "replace": replace_content
            })
            
        return blocks

    def apply_and_diff(self, file_path: Path, search_text: str, replace_text: str) -> Tuple[bool, str]:
        """舊版相容接口，直接呼叫新版 Patcher"""
        from nexus.services.local_heal.patcher import Patcher
        patcher = Patcher()
        file_content = file_path.read_text(encoding="utf-8", errors="replace")
        res = patcher.apply_patch(file_content, search_text, replace_text)
        if res.success:
            file_path.write_text(res.new_content, encoding="utf-8")
            
            # 使用真正檔案名產生 diff，以滿足舊單元測試對 a/dummy.py b/dummy.py 的 assert 預期
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


