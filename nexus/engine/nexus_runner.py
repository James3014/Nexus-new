from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging
import re
import asyncio

logger = logging.getLogger(__name__)

class NexusRunner:
    """
    🏃 Nexus 任務執行器 (v22 Stream Optimized)
    負責管理指令流與異步預取。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.preload_cache = {}

    async def stream_preload(self, partial_text: str):
        """
        🧬 P3: 串流預執行 (Stream Preload)
        在 LLM 生成過程中預判 I/O 需求。
        """
        # 尋找 "read [file]" 或 "view_file(path=...)" 模式
        file_patterns = [
            r"read(?:ing)?\s+([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]+)",
            r"view_file\(['\"]?path['\"]?[:=]\s*['\"]?([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]+)['\"]?",
            r"viewing\s+file\s+([a-zA-Z0-9_\-\./]+\.[a-zA-Z0-9]+)"
        ]
        
        found_files = []
        for pattern in file_patterns:
            matches = re.findall(pattern, partial_text)
            found_files.extend(matches)
            
        for file_path in set(found_files):
            if file_path not in self.preload_cache:
                await self._preload(file_path)

    async def _preload(self, file_path: str):
        """實施物理預取"""
        full_path = self.project_root / file_path
        if full_path.exists() and full_path.is_file():
            logger.info("⚡ [Preload] Pre-fetching file content: %s", file_path)
            try:
                # 執行物理異步預讀
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read(4096) # 預讀前 4K
                    self.preload_cache[file_path] = content
            except Exception as e:
                logger.debug("Preload failed for %s: %s", file_path, e)
