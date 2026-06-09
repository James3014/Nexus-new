from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

class ApplyVerdict(str, Enum):
    """
    🛡️ ApplyVerdict: 補丁套用判決
    明確區分套用失敗的各種階段。
    """
    MATCHED_AND_APPLIED = "MATCHED_AND_APPLIED"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    NO_MATCH_FOUND = "NO_MATCH_FOUND"
    SYNTAX_ERROR_AFTER_APPLY = "SYNTAX_ERROR_AFTER_APPLY"
    FILE_UNCHANGED = "FILE_UNCHANGED"
    INVALID_BLOCK_ORDER = "INVALID_BLOCK_ORDER"

@dataclass
class SearchReplaceBlock:
    """
    🛡️ SearchReplaceBlock: Search/Replace 核心區塊
    """
    search: str
    replace: str
    index: int = 0
    is_fuzzy: bool = False

@dataclass
class PatchIntent:
    """
    🛡️ PatchIntent: 補丁意圖
    將原始輸出轉化為可執行的結構。
    """
    task_id: str
    target_file: str
    blocks: List[SearchReplaceBlock] = field(default_factory=list)
    raw_payload: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
