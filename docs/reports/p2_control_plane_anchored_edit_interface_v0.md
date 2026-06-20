# Control-Plane Anchored Edit Interface Report (P2)

本報告總結 **P2 — Control-Plane Anchored Edit Interface** 的設計與實作。

## 1. 核心設計與實現
我們建立了 [anchored_edit.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/anchored_edit.py)，定義了 ACI 的 `AnchoredEdit` 資料結構。
控制平面會首先決定 exact source anchor，並為其分配 `anchor_id`、`source_hash` 及其行列資訊。模型不需要自主生成 `SEARCH` 區塊，控制平面透過 `SolidSearchReplaceProtocol.parse(..., anchor_text=...)` 將模型的 replacement 內容與此 anchor 綁定。

## 2. Invariants 與防禦機制
在 `validate()` 階段，我們實施了以下 invariants：
- **Stale hash 阻斷**: 當前的 source 檔案 hash 與 captured `source_hash` 不符時，回傳 `SOURCE_STALE` 錯誤，防止基於過期版本進行修復。
- **Empty replacement 阻斷**: 模型回覆為空或空白時，回傳 `PATCH_EMPTY` 錯誤。
- **Anchor 未發現阻斷**: 若控制平面指定的 `exact_source_text` 由於某些原因（例如工作目錄被修改）不在目前原始碼中，回傳 `SEARCH_MISMATCH` 錯誤。
- **歧義 Anchor 阻斷**: 當指定 anchor 在檔案中出現多次時，回傳 `NAME_SANITY_ERROR` 以免替換錯誤的位置。
- **防止模型發明 SEARCH**: 記錄 `model_generated_search=False`，並將 `match_authority` 指定為 `MatchAuthority.CONTROL_PLANE_VERBATIM`。

## 3. 單元測試驗證
新建了 [test_anchored_edit.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_anchored_edit.py) 進行完整驗證，包含：
- `test_anchored_edit_success`
- `test_anchored_edit_stale_hash`
- `test_anchored_edit_empty_replacement`
- `test_anchored_edit_anchor_not_in_source`
- `test_anchored_edit_ambiguous_anchor`
- `test_protocol_parse_anchored_edit_mode`
- `test_runbook_compliance_accepts_control_plane_verbatim`

所有的測試目前皆已 100% 通過，且沒有引入任何 regressions。

最終狀態：**`P2_ANCHORED_EDIT_INTERFACE_READY`**
