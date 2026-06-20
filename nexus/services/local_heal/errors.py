from enum import Enum, auto
from dataclasses import dataclass
from typing import Any

class PatchErrorKind(Enum):
    SYNTAX_ERROR = auto()        # REPLACE 區塊語法編譯錯誤
    SEARCH_MISMATCH = auto()     # SEARCH 區塊無法在原始檔案中匹配定位
    LOGIC_REGRESSION = auto()    # 測試執行失敗或退步
    FILE_NOT_FOUND = auto()      # 目標檔案不存在
    NO_BLOCKS_FOUND = auto()     # LLM 輸出中未包含任何有效的 SEARCH/REPLACE 區塊
    NO_EFFECTIVE_CODE_CHANGE = auto() # 變更僅涉及 docstrings、註解或排版，無實質邏輯代碼變更
    SEARCH_HAS_PLACEHOLDER = auto()   # SEARCH 區塊含有省略號 (如 '# ...')，導致匹配失敗
    NAME_SANITY_ERROR = auto()        # 補丁引入重複定義、佔位命名或其他 LLM 代碼衛生問題
    REFUSAL_DETECTED = auto()         # 模型明確拒絕提供補丁或道歉
    EMPTY_RESPONSE = auto()           # 模型回傳空內容
    PATCH_EMPTY = auto()              # Patch apply 後無實際檔案變更
    PATCH_FORMAT_INVALID = auto()     # Patch 格式不合法（非 SEARCH/REPLACE 結構）
    SOURCE_STALE = auto()             # SOURCE_CONTEXT 與實際檔案版本不一致


class PatchMismatchSubclass(Enum):
    """Patch mismatch 細分類 — 用於 receipt telemetry"""
    VERBATIM_SEARCH_MISMATCH = auto()      # 逐字匹配完全失敗
    WRONG_TARGET_SPAN = auto()             # 匹配到錯誤的 code span（跨函數/跨類別漂移）
    SEARCH_NORMALIZATION_DRIFT = auto()    # 歸一化後匹配但原始形式不符
    CLOSEST_SNIPPET_FALSE_FRIEND = auto()  # closest snippet 找到相似但不正確的片段
    PATCH_SYNTAX_INVALID = auto()          # patch apply 後語法無效


class MatchAuthority(Enum):
    """Authority source for a successfully applied patch.

    Used in PatchApplicationResult.match_authority and receipt telemetry.
    Fail-closed: fuzzy_candidate_only MUST NOT appear on success=True patches.
    """
    VERBATIM = "verbatim"                          # Exact SEARCH text found in source
    CROSS_FILE_CORRECTION = "cross_file_correction"  # Canonical span from a DIFFERENT localized file
    CANONICAL_RECOVERY = "canonical_recovery"      # Canonical span from line block extraction or AST symbol fallback
    FUZZY_CANDIDATE_ONLY = "fuzzy_candidate_only"  # FAIL-CLOSED: must never appear on success=True
    CONTROL_PLANE_VERBATIM = "control_plane_verbatim" # Exact SEARCH block provided or overridden by control plane


@dataclass
class PatchError:
    kind: PatchErrorKind
    message: str
    file_path: str | None = None
    line_number: int | None = None
    closest_match: str | None = None  # 最接近的匹配代碼（用於提供給模型的 HUD 微調提示）
    failed_search_text: str | None = None # 導致 Mismatch 的原始搜尋內容
    mismatch_subclass: PatchMismatchSubclass | None = None  # 細分類
    telemetry: dict | None = None  # T1.3: Enriched telemetry from validate()
    structured_packet: Any = None  # T3: Bounded structured packet for verifier failures
