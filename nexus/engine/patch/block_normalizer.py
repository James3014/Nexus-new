import re

class SearchBlockNormalizer:
    """
    🛡️ SearchBlockNormalizer: 搜尋區塊正規化器
    處理換行符號差異、尾端空白與縮排一致性。
    """
    def canonicalize(self, text: str) -> str:
        # 1. 統一換行符號
        text = text.replace('\r\n', '\n')
        # 2. 移除每行末尾的多餘空白 (符合多數 Linter 規範)
        lines = [line.rstrip() for line in text.splitlines()]
        return '\n'.join(lines)
