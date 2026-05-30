from enum import Enum, auto
from dataclasses import dataclass

class PatchErrorKind(Enum):
    SYNTAX_ERROR = auto()        # REPLACE 區塊語法編譯錯誤
    SEARCH_MISMATCH = auto()     # SEARCH 區塊無法在原始檔案中匹配定位
    LOGIC_REGRESSION = auto()    # 測試執行失敗或退步
    FILE_NOT_FOUND = auto()      # 目標檔案不存在
    NO_BLOCKS_FOUND = auto()     # LLM 輸出中未包含任何有效的 SEARCH/REPLACE 區塊
    NO_EFFECTIVE_CODE_CHANGE = auto() # 變更僅涉及 docstrings、註解或排版，無實質邏輯代碼變更
    SEARCH_HAS_PLACEHOLDER = auto()   # SEARCH 區塊含有省略號 (如 '# ...')，導致匹配失敗


@dataclass
class PatchError:
    kind: PatchErrorKind
    message: str
    file_path: str | None = None
    line_number: int | None = None
    closest_match: str | None = None  # 最接近的匹配代碼（用於提供給模型的 HUD 微調提示）
