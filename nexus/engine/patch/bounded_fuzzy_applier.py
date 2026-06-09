import difflib
from typing import Tuple, Optional

class BoundedFuzzyApplier:
    """
    🛡️ BoundedFuzzyApplier: 受限模糊套用器
    限制最大漂移行數與修改面，防止 patch 跑位。
    """
    def fuzzy_match_and_replace(self, content: str, search: str, replace: str) -> Tuple[bool, str, str]:
        # 使用 difflib 進行模糊比對
        s = difflib.SequenceMatcher(None, content, search)
        match = s.find_longest_match(0, len(content), 0, len(search))
        
        if match.size > len(search) * 0.8: # 要求 80% 以上匹配度
            start = match.a
            end = match.a + match.size
            new_content = content[:start] + replace + content[end:]
            return True, new_content, f"Fuzzy matched with size {match.size}"
            
        return False, content, "FUZZY_MATCH_LOW_CONFIDENCE"
