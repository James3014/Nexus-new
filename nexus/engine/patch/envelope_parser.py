import re
from typing import List
from nexus.engine.contracts.patch import PatchIntent, SearchReplaceBlock

class PatchEnvelopeParser:
    """
    🛡️ PatchEnvelopeParser: 補丁信封解析器
    負責從模型產出的原始字串中提取 Search/Replace 結構，並剝離 Markdown 包裝。
    """
    def parse(self, task_id: str, raw_text: str) -> PatchIntent:
        # 1. 剝離 Markdown Code Fences
        cleaned_text = self._strip_fences(raw_text)
        
        # 2. 提取 Search/Replace Blocks
        # 這裡我們支援 Aider 格式: <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE
        blocks = []
        # 允許分隔符前有空白，並自動去除內容的共通縮排
        pattern = r'^\s*<<<<<<< SEARCH\s*\n(.*?)\n\s*=======\n(.*?)\n\s*>>>>>>> REPLACE'
        matches = re.finditer(pattern, cleaned_text, re.DOTALL | re.MULTILINE)
        
        for i, match in enumerate(matches):
            blocks.append(SearchReplaceBlock(
                search=match.group(1),
                replace=match.group(2),
                index=i
            ))
            
        return PatchIntent(
            task_id=task_id,
            target_file="", # 需要從 context 或 header 提取
            blocks=blocks,
            raw_payload=raw_text
        )

    def _strip_fences(self, text: str) -> str:
        text = re.sub(r'^```[a-zA-Z]*\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\n?', '', text, flags=re.MULTILINE)
        return text.strip()
