# Literature-to-Nexus Design Mapping (P1)

本文件梳理學術文獻中的軟體工程 Agent 設計原則，並將其映射至 Nexus 的控制平面具體實作決策。

## 1. Agentless Mapping
- **文獻原則**: 避免設計過於複雜的自主 Agent 迴圈（例如帶有 self-planning 或複雜工具呼叫的 LLM 迴圈），而應使用結構清晰的 pipeline：定位（Localization） -> 修復（Repair） -> 驗證（Validation）。
- **Nexus 實作對應**:
  - **定位**: 採用 AST Slicing 與 Surgical Slicer 將語意相關的 code 裁剪為緊湊、準確的 symbol-level context，直接提供給 LLM 作為 localised context。
  - **修復**: LLM 是一個單純的補丁生成器，不提供自主執行 terminal 的工具，保持其無狀態（Stateless）與解耦性。
  - **驗證**: 由控制平面接管，自動將 patch 套用至獨立的工作目錄（Worktree），執行 pytest verifier 判定語意正確性。
- **簡化決策**: Nexus 應進一步移除模型在 retry 時自主探索工具的幻想，全面由控制平面接管工作區衛生、還原與重試流程。

## 2. SWE-agent / ACI (Agent-Computer Interface) Mapping
- **文獻原則**: LLM 表現極大程度取決於其編輯/操作介面。目前的 "SEARCH/REPLACE" 介面強迫小模型去生成 exact 的 SEARCH 區塊，對小模型（7B）的 parametric memory 是一大考驗，容易因為細微的版本差異或語法不吻合導致 `SEARCH_MISMATCH`。
- **Nexus 實作對應**:
  - **脆弱介面**: 舊有介面中模型需要自行產生 SEARCH 區塊，導致 7B 因腦補直接失敗。
  - **改進介面 (Anchored Edit)**: 改由控制平面主導。控制平面首先定位出精準的程式碼 span (Anchor)，分配 `anchor_id` 並提供 `exact_source_text`。模型不再需要產生 SEARCH 區塊，仅提供 replacement text (意圖)，由控制平面完成與 verbatim anchor 的合併與套用。
  - **對 7B 影響**: 徹底消除 7B 的 `SEARCH_MISMATCH` 機率，將修復核心聚焦於 Replacement 程式碼的生成品質。

## 3. Assured LLM-Based Software Engineering Mapping
- **文獻原則**: LLM 產生的程式碼有幻覺風險，必須透過多候選生成（Candidate generation）並由語意/測試過濾門禁進行篩選，不符合的 candidate 必須一律丟棄。
- **Nexus 實作對應**:
  - **候選生成**: 一次性請求模型產生 $N$ 個修復候選（例如 $N=3$）。
  - **語意/Verifier 過濾器**: 控制平面套用補丁後，強制跑 `pytest` 等測試門禁，唯有通過所有 verifier 且無 regressions 的候選才能被採信。
  - **Compliance Checker**: 自動化檢查補丁的代碼衛生（NameSanity, Effective change）。

## 4. SCoRe Mapping
- **文獻原則**: 模型無法單純透過 self-prompting 實現自我糾錯（Self-correction），容易發生行為崩潰（Behavior collapse，即重試時生成完全相同的錯誤補丁，或者越改越錯）。
- **Nexus 實作對應**:
  - **軌跡收集**: 將每次的 attempt、error feedback 以及 correction 套用過程記錄至 telemetry trace。
  - **避免崩潰**: 限制重試階段的 edit span，禁止模型擴大修改範圍，且在 retry 階段直接拒絕模型修改 SEARCH 錨點。若模型在 attempt 2 輸出了與 attempt 1 相同的 patch，直接阻斷並判定為 `behavior_collapse`。

## 5. SWE-Search Mapping
- **文獻原則**: 補丁搜尋效能顯著優於單一軌跡探索。應基於 Bounded candidates 進行 search，並由確定性 verifier 的結果決定最優補丁，而不是依靠 LLM 自評的信心值。
- **Nexus 實作對應**:
  - **無自評信賴**: 排除模型在 token 中輸出的自評信心度，完全以 verifier 測試是否通過作為晉升的唯一指標。
  - **確定性選擇**: 第一個通過所有語意門禁的 candidate 即被選定。

---

## 決定：P2 實作目標
我們選擇 **`P2_CONTROL_PLANE_ANCHORED_EDIT_INTERFACE`** 作為 P2 的第一階段實作，這直接解決了 7B 當前最嚴重的 `SEARCH_MISMATCH` 瓶頸。
