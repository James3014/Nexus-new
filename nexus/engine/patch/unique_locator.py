from typing import Tuple, List, Optional

class UniqueLocator:
    """
    🛡️ UniqueLocator: 唯一定位器
    確保 Search Block 在檔案中僅出現一次，防止歧義套用。
    """
    def find_unique_position(self, file_content: str, search_block: str) -> Tuple[bool, int, str]:
        """
        返回 (is_unique, start_index, error_message)
        """
        count = file_content.count(search_block)
        
        if count == 0:
            return False, -1, "SEARCH_BLOCK_NOT_FOUND"
        
        if count > 1:
            return False, -1, f"AMBIGUOUS_MATCH: Found {count} occurrences. Please provide more context."
            
        return True, file_content.find(search_block), ""

    def expand_context_if_needed(self, file_content: str, search_block: str) -> str:
        # TODO: 實作自動擴展上下文邏輯
        return search_block
