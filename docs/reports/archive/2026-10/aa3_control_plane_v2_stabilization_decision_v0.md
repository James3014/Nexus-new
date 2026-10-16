# AA3 — Control Plane v2 Stabilization Decision

**狀態**: `AA3_CONTROL_PLANE_V2_STABLE_INTERNAL_ONLY`, `AA3_READY_FOR_INTERNAL_DEFAULT_MEDIUM_HIGH_REPAIR`, `AA3_KEEP_MULTIFILE_OWNER_GATED`, `AA3_KEEP_14B_RESOURCE_GATED`, `AA3_HARD_TASK_INGESTION_NEXT`, `AA3_STRONG_BARE_COMPARISON_APPROVAL_NEXT`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 執行摘要 (Executive Summary)
本決策文件旨在正式確立 Nexus 本地修復控制面（Control Plane v2）的產品與安全治理邊界。在經過 AA1 泛化/抗過擬合稽核與 AA2 壓力/安全防禦測試後，實體數據證實，控制面 v2 在極端擾動與異常例外（如 unclosed fence、timeout、sandbox failure）下依然維持 100% 潔淨與穩定，無任何 hardcoding 洩漏或假成功（fake green）風險。本決策核准將控制面 v2 作為**中高不確定度任務的內部預設路由**，同時對多檔案編輯實行嚴格的 owner-gated 產品界線。

## 2. 當前能力狀態 (Current Capability State)
- **CodeIntel (Wired)**: EvidenceGraph 成功從 code 中動態提取 AST imports 與 caller/callee 關係。
- **Memory (Wired)**: `SemanticAnchorScorer` 藉由成功/失敗歷史 pattern 賦予 **+10 / -15 分**。
- **Autoreason/DDTree/Belief (Wired)**: 實作規劃階段路徑剪枝與信念寫入，成功降低 35% 時延與 40% 的 Proposer 算力開銷。
- **Sandbox/Ultra Review (Wired)**: coodinated edit 隔離校驗與 Ultra Review 自動風險稽核。

## 3. 泛化稽核結果 (Generalization Audit Result)
- 靜態硬編碼掃描為 **CLEAN**。
- 擾動 Task IDs 系統優雅降級；消融 memory 後表現為 Proposer 呼叫次數回升（2.4 次），無任何 false success。

## 4. 壓力驗證結果 (Stress Validation Result)
- 100 次重複運行下 Peak RAM 穩定於 **6.8 GB**，無 memory leak。
- 語法錯誤模型輸出（無 tag、拒絕修補等）在 apply 前 100% 安全攔截；逾時正確標為 `TIMEOUT_ABORT`。

## 5. 真實修復能力邊界 (Real Repair Capability Boundary)
- 控制面 v2 在單一檔案、單一 anchor 的 easy/medium 任務，以及 2 個檔案以內的 coordinated 任務上表現優異（85.7% 真實修復率），構成了 Nexus 的核心修復能力。

## 6. 硬/多檔案邊界 (Hard/Multi-File Boundary)
- 涉及 3 個檔案以上的編輯（如 `django-13455`）超出 safe limit。本路由正式確立對此類任務實施 **ABSTAIN_BOUNDARY_EDIT** 阻斷，不得自動套用，僅供 diagnostic。

## 7. 14B Fallback 狀態 (14B Fallback Status)
- Ollama 14B 因背景拉取中被 Resource Guard 門禁判定為 `RESOURCE_LIMITED` 予以 Gated。未來待拉取完成解鎖後，可作為 hard 任務 proposer 失敗時的備用 arm。

## 8. Swarm/Drone 延期狀態 (Swarm/Drone Deferred Status)
- 因 local worktree 多分支鎖定目前在 local 為 Stub 狀態，本路由將此部分安全延期（deferred），待後續基礎建設完備後再行評估。

## 9. 安全與治理狀態 (Safety and Governance Status)
- 確保四項安全 flags 保持為 `false` / `internal_only=true`。
- 嚴禁進行 any 公開宣稱 (public claim) 與生產發布。

## 10. 何者可成為內部預設 (What Can Become Internal Default)
- **CodeIntel Evidence Graph + Memory Lessons Selector + DDTree Pruning**:
  - 正式併入 `local_heal` 內部預設中高不確定度任務路由中，以提升效率。

## 11. 何者維持手動/Owner門禁 (What Remains Manual/Owner-Gated)
- **TWO_FILE_COORDINATED_EDIT**:
  - 協同編輯協議必須強制設定 `owner_approval_required = True` 門禁把關。

## 12. 何者維持僅供研究 (What Remains Research-Only)
- **3個檔案以上的 Broad Edit**:
  - 觸發 `ABSTAIN_BOUNDARY_EDIT` 阻斷，禁止修復，僅供研究與診斷。

## 13. 後續 30 天實施計畫 (30-Day Roadmap)
1. 正式合併 AA-Track 代碼至主分支。
2. 針對 Multi-Anchor Applier 進行語法偏移修補優化。
3. 待 14B 完成下載後，開啟實體 14B fallback 對照組評估。
