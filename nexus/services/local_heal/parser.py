import re
from typing import List, Dict

class SearchReplaceParser:
    """單一功能：解析 LLM 輸出的 SEARCH/REPLACE 語法區塊 (SRP)"""

    def _clean_content(self, text: str) -> Tuple[str, bool]:
        # 深度清洗 markdown fence
        cleaned = re.sub(r'```[a-zA-Z0-9]*\n?', '', text)
        cleaned = cleaned.strip()
        
        # 檢測 placeholder 省略號
        has_placeholder = False
        if any(ph in cleaned for ph in ("# ...", "// ...", "/* ...", "... existing", "existing code")):
            has_placeholder = True
        elif "..." in cleaned:
            if not re.search(r'=\s*\.\.\.', cleaned) and not re.search(r'\[\s*\.\.\.\s*\]', cleaned):
                has_placeholder = True
                
        return cleaned, has_placeholder

    def parse_blocks(self, llm_output: str) -> List[Dict[str, Any]]:
        blocks = []
        
        # 1. Custom 格式解析
        custom_pattern = re.compile(
            r'FILE:\s*([^\n]+)\s*\n'
            r'SEARCH:\s*\n(.*?)\nREPLACE:\s*\n(.*?)\nEND',
            re.DOTALL
        )
        for match in custom_pattern.finditer(llm_output):
            raw_search = match.group(2)
            raw_replace = match.group(3)
            
            search_content, has_ph_search = self._clean_content(raw_search)
            replace_content, has_ph_replace = self._clean_content(raw_replace)
            
            blocks.append({
                "file": match.group(1).strip(),
                "search": search_content,
                "replace": replace_content,
                "has_placeholder": has_ph_search or has_ph_replace
            })
            
        # 2. Aider 格式解析 (SOTA Fuzzy Parser)
        aider_block_pattern = re.compile(
            r'<<<<<<< SEARCH\s*\n(.*?)\n=======\n(.*?)\n>>>>>>>(?:\s*REPLACE)?',
            re.DOTALL
        )
        for match in aider_block_pattern.finditer(llm_output):
            raw_search = match.group(1)
            raw_replace = match.group(2)
            
            search_content, has_ph_search = self._clean_content(raw_search)
            replace_content, has_ph_replace = self._clean_content(raw_replace)
            
            # 尋找該區塊前方最近的 "FILE: ..." 或看起來像路徑的檔名
            start_pos = match.start()
            prefix = llm_output[:start_pos]
            
            # 從字尾往前找匹配的檔名
            file_match = re.findall(r'(?:FILE|File):\s*([a-zA-Z0-9_\-\./\+]+)', prefix)
            file_name = ""
            if file_match:
                file_name = file_match[-1].strip().strip('`*# ')
            
            # 容錯：如果找不到 FILE:，但 prefix 裡面有顯式的 python 檔案路徑
            if not file_name:
                path_match = re.findall(r'([a-zA-Z0-9_\-\./\+]+\.py)', prefix)
                if path_match:
                    file_name = path_match[-1].strip().strip('`*# ')
                    
            if file_name:
                blocks.append({
                    "file": file_name,
                    "search": search_content,
                    "replace": replace_content,
                    "has_placeholder": has_ph_search or has_ph_replace
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


