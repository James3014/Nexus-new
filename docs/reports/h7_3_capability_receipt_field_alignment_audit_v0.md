# H7-3 Capability Receipt Field Alignment Audit v0

**日期**: 2026-06-25  
**狀態**: `H7_3_CAPABILITY_RECEIPT_FIELD_ALIGNMENT_AUDIT_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `NO_RUNTIME_BEHAVIOR_CHANGE`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_PROCESS_SPAWN`, `NO_NETWORK_CALL`, `PUBLIC_CLAIM_ALLOWED=false`  

> **安全聲明**: 本報告為純 audit/report-only 產出。本任務期間未新增任何 runtime routing behavior、未啟用 learned policy、未啟動 provider/model/network/model-load/model-call。H7 仍處於 planning-only 階段。

---

## 0. Status / Safety Boundary

本報告嚴格遵守以下安全防禦邊界：
* **status**: `H7_3_CAPABILITY_RECEIPT_FIELD_ALIGNMENT_AUDIT_DRAFT_READY_FOR_REVIEW`
* **no runtime behavior change** (不改變執行期行為)
* **no provider call** (不呼叫 provider)
* **no model call** (不進行模型調用)
* **no network call** (不啟用網路)
* **no model load** (不載入模型)
* **no model execution** (不執行模型)
* **no learned policy adoption** (不啟用學習策略)
* **no new router** (不新增路由器)
* **production_ready=false**
* **public_claim_allowed=false**
* **H7 runtime not started** (H7 執行期尚未啟動)

---

## 1. Scope

本報告專注於靜態審計（Static Audit）與對齊現行 Nexus 選路、憑證、學習、治理與自癒相關 primitives 欄位之強型別與語義對齊，以為未來 test-only gate 鋪路。
* **H7-3 is report-only**: 本任務不包含任何 runtime 程式與測試修改。
* **H7-3 does not modify production code**: 不修改任何 `nexus/**/*.py` 程式。
* **H7-3 does not modify tests**: 不修改任何 `tests/**/*.py` 測試。
* **H7-3 does not change routing behavior**: 不變更任何執行期分發路徑。
* **H7-3 does not adopt learned policy**: 排除 runtime 採用 learned policy，保持 shadow-only 狀態。
* **H7-3 does not authorize provider/model runtime**: Provider 邊界維持 deny-by-default。
* **H7-3 prepares field alignment for future test-only gates**: 本報告為後續 schema 測試奠定基礎。

---

## 2. Field Alignment Matrix

本表格靜態審查與對齊 26 個核心欄位與狀態特徵：

| Object / receipt | Owner module | Exists? yes/no/missing_or_moved | Field name | Field semantic | Current type if visible | Truth role | Required for H7? | Required for H8? | Required for H7-R / recovery? | Missing / ambiguous? | Recommended action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **RouteDecision** | `missing_or_moved` | no | `decision_id` | 標識每一次 planner settlements 決策唯一 ID | `str` (規劃中) | `route_truth`, `recovery_projection_candidate` | no | yes | yes | yes (contracts 無此屬性) | H8 新增以標識 unique settlement |
| **RouteDecision** | `missing_or_moved` | no | `route_id` | 決策路由路徑唯一標識 | `str` (規劃中) | `route_truth` | no | yes | yes | yes (無此屬性) | H8 引入對齊 |
| **RouteDecision** | `nexus/engine/capability_contracts.py` | yes | `task_id` | 標識當前執行的任務 ID | `str` | `route_truth`, `receipt_truth`, `learning_trace` | yes | yes | yes | no | 保持為跨模組唯一任務標識關聯 |
| **CapabilityReceipt** | `missing_or_moved` | no | `capability_id` | 選路能力唯一標識 ID | `str` (規劃中) | `route_truth` | yes (目前以 name 代替) | yes | yes | yes (目前使用 name 字串) | H8 統一重命名對齊，避免與 skill_id 格式不對稱 |
| **RouteDecision** | `nexus/engine/capability_contracts.py` | yes | `selected_capabilities` | 當前選中的執行能力清單 | `tuple[str, ...]` / `list[str]` | `route_truth` | yes | yes | yes | no | Plan 中是 list，RouteDecision 中是 tuple，H8 應對齊為 tuple |
| **RouteDecision** | `nexus/engine/capability_contracts.py` | yes | `required_capabilities` | 治理或合約強制要求的能力清單 | `tuple[str, ...]` / `list[str]` | `route_truth` | yes | yes | yes | no | H8 統一對齊為 tuple[str, ...] |
| **RouteDecision** | `nexus/engine/capability_contracts.py` | yes | `forbidden_capabilities` | 禁止執行的能力清單 | `tuple[str, ...]` / `list[str]` | `route_truth`, `governance_gate` | yes | yes | yes | no | 保持為禁止邊界真值 |
| **CapabilityReceipt** | `nexus/engine/capability_contracts.py` | yes | `invoked` | 標識能力是否被實際執行呼叫 | `bool` | `receipt_truth` | yes | yes | yes | no | 必須由測試確保其與實際 Provider 執行狀態完全一致 |
| **CapabilityReceipt** | `nexus/engine/capability_contracts.py` | yes | `gate_passed` | 治理閘或驗證器是否通過 | `bool` | `receipt_truth`, `governance_gate` | yes | yes | yes | no (不同對象中微小語意差異) | 統一 settlements 機制中此欄位的判定語義 |
| **CapabilityReceipt** | `nexus/engine/capability_contracts.py` | yes | `public_claim_safe` | 標識憑證是否滿足公開宣告安全門檻 | `bool` (property) | `receipt_truth`, `governance_gate` | yes | yes | yes | no | 測試必須針對 dependencies 進行 fail-closed 驗證 |
| **CapabilityReceipt** | `nexus/engine/capability_contracts.py` | yes | `evidence_refs` | 驗證憑證之物理雜湊或檔案鏈結引用 | `tuple[str, ...]` | `evidence_ref`, `receipt_truth` | yes | yes | yes | no (S2T 中為 list) | H8 統一 schema 為 tuple[str, ...] |
| **EvidenceVerifier** | `missing_or_moved` | no | `artifact_refs` | 產出代碼/測試 artifacts 雜湊與路徑對齊 | `tuple[str, ...]` (規劃中) | `evidence_ref` | no | yes | yes | yes (contracts 無此屬性) | 統一為 evidence_refs 以免重複 |
| **CapabilityReceipt** | `missing_or_moved` | no | `receipt_id` | 憑證唯一識別碼 | `str` (規劃中) | `receipt_truth` | no | yes | yes | yes (無此屬性) | H8 新增以利自癒與復原識別 |
| **RouteDecision** | `missing_or_moved` | no | `trace_id` | 學習軌跡 Episode 唯一關聯識別碼 | `str` (規劃中) | `learning_trace` | no | yes | yes | yes (無此屬性) | 引入以關聯 OutcomeMemory |
| **rlm_controller** | `missing_or_moved` | no | `phase_id` | 執行中斷的具體階段識別 | `str` (規劃中) | `learning_trace`, `recovery_projection_candidate` | no | yes | yes | yes (嚴重缺失，目前僅有 loop_phase) | H8 引進 phase_pointer，否則無法恢復 |
| **S2TCandidate** | `nexus/contracts/s2t_policy.py` | yes | `candidate_id` | 標識候選 patch 的唯一識別碼 | `str` | `learning_trace`, `recovery_projection_candidate` | no | yes | yes | yes (與 local_heal 對齊脆弱) | H8 / U3-1 進行標準對齊 |
| **RouteDecision** | `missing_or_moved` | no | `selected_candidate_hash` | 被選中的候選 patch 原始 sha256 雜湊 | `str` (規劃中) | `recovery_projection_candidate`, `unsafe_for_runtime_route` | no | yes | yes | yes (U3 Blockers，contracts 無此屬性) | 必須在 U3-1 新增，H7 禁止進入 runtime 選路 |
| **RouteDecision** | `missing_or_moved` | no | `applied_patch_hash` | 實際套用到工作區的 patch 實體 sha256 | `str` (規劃中) | `recovery_projection_candidate`, `unsafe_for_runtime_route` | no | yes | yes | yes (U3 Blockers，同上) | 必須在 U3-1 新增，以防止 replay 漂移 |
| **CapabilityReceipt** | `missing_or_moved` | no | `model_call_executed` | 是否實際執行過模型調用 | `bool` (規劃中) | `telemetry_only` | yes | yes | yes | yes (目前由 telemetries 封裝) | H7/H8 tests 必須確保其保持為 False/0 |
| **rlm_controller** | `missing_or_moved` | no | `runtime_effect` | 標識政策是否具有 runtime 選路修改效用 | `bool` (規劃中) | `governance_gate` | yes | yes | yes | yes (目前為 runtime_update_allowed) | 確保其保持為 False，防範自動模式變更 |
| **reports** | `missing_or_moved` | no | `production_ready` | 標識系統是否達到生產就緒狀態 | `bool` (規劃中) | `governance_gate` | yes | yes | yes | yes (僅在 reports 中以文字形式存在) | 嚴禁進入 runtime 程式，保持規劃審計 |
| **reports** | `missing_or_moved` | no | `public_claim_allowed` | 標識是否允許進行公開 benchmark 宣稱 | `bool` (規劃中) | `governance_gate` | yes | yes | yes | yes (目前由 public_benchmark_allowed 封裝) | 僅在 reports 中聲明，嚴禁 runtime 提權 |
| **learning_policy_loader** | `nexus/engine/learning_policy_loader.py` | yes | `policy_source` | 政策之檔案或來源路徑 | `str` | `learning_trace`, `policy_input` | yes | yes | yes | yes (目前為 dict 鍵值，非 dataclass) | H8 移入 CapabilityPlan 屬性 |
| **CapabilityPlan** | `missing_or_moved` | no | `policy_mode` | 政策所運行的規劃模式 | `str` (規劃中) | `route_truth` | yes | yes | yes | yes (目前使用 planner_mode) | 統一收斂至 planner_mode |
| **s2t_policy** | `nexus/contracts/s2t_policy.py` | yes | `shadow_only` | 政策僅允許在 shadow 模式下運作，無 runtime 效用 | `str` (狀態值) | `governance_gate`, `learning_trace` | yes | yes | yes | no | 保持此狀態，作為 shadow 執行期邊界保護 |
| **s2t_policy** | `missing_or_moved` | no | `adoption_allowed` | 標識是否核准政策晉升至 runtime 執行 | `bool` (規劃中) | `governance_gate` | yes | yes | yes | yes (目前使用 strict_opt_in 狀態) | 確保其在 H7/H8 中被強制攔截為 False |

---

## 3. Required False Assertions

為鎖定安全防禦邊界，以下欄位在 H7/H8 tests 中必須被強制斷言（assert）為 **`False`**（或零值）：

```python
# 🛡️ Nexus Safety False Assertions Block
model_call_executed = False          # 嚴禁執行 LLM 模型呼叫
runtime_effect = False               # 嚴禁對 runtime 狀態產生寫入變更
production_ready = False             # 生產就緒宣告必須為 False
public_claim_allowed = False         # 嚴禁自動進行公開宣稱
provider_invoked = False             # 預設 Provider 未被呼叫
provider_probe_allowed = False       # 封鎖 Provider 自發性探測
provider_invocation_allowed = False  # 封鎖 Provider 調用授權
provider_execution_allowed = False   # 封鎖 Provider 執行授權
network_allowed = False              # 封鎖網路存取
process_spawn_allowed = False        # 封鎖子行程衍生 (spawning)
model_load_allowed = False           # 封鎖模型載入行為
model_call_allowed = False           # 封鎖模型調用授權
```

---

## 4. Missing Recovery Fields

在自癒與任務復原方面，目前 Nexus 在 `local_heal` 中仍有以下致命 blocker（如 U3 Preflight 審計所示）：
1. **`candidate_id` 缺乏強連結**: 目前 `candidate_key` (使用 `#` 符號) 與 `winner_id` (使用 `-` 符號) 格式不對稱，對齊脆弱。
2. **缺少 `selected_candidate_hash`**: 未計算或儲存被選中候選的 patch hash。
3. **缺少 `applied_patch_hash`**: 未計算或儲存實際套用到工作區的實體 patch hash。
4. **缺少 `hash_mismatch_detected`**: 無雜湊比對邏輯，無法發現程式碼偏差。
5. **缺少 `hash_mismatch_closed_gate`**: 當發生雜湊不符時，無法進行 fail-closed 安全阻斷。
6. **缺少 `phase_pointer`**: 計數器（`x_iteration` / `r_iteration`）未指示具體中斷的 execution phase，重啟面臨 blind resume 隱患。
7. **缺少 `next_action_pointer`**: 熔斷後直接返回 False，無法指引 fallback 行動。

### 審計結論
* **H7-3 不解決 U3**。U3 候選隔離與雜湊匹配仍未就緒。
* **因 `selected_candidate_hash` 與 `applied_patch_hash` 缺失，當前的自癒只能保持唯讀投影（projection-only）**，即只能輸出 TaskRecoveryState 的唯讀評估，不可執行實際自癒重試。
* **`RecoveryState / TaskRecoveryState` 不得作為 route truth source**。它們的屬性不能干涉或覆寫 `RouteDecision` 的 Settlements 真值。
* **No resume runtime until candidate isolation is closed** (在候選隔離完全閉合前，不啟用任何 resume 執行期 runtime)。

---

## 5. Alignment Decision

本 field alignment 審計確立以下五大欄位歸屬真值決策：

1. **`RouteDecision` 擁有選路真值 (Route Truth)**: 所有決定 executor 狀態的選路屬性均以 `RouteDecision` 為唯一 settlements 真值。
2. **`CapabilityReceipt / SkillReceipt` 擁有憑證真值 (Receipt Truth)**: 記錄執行的客觀事實，決定該憑證是否 public_claim_safe。
3. **`EvidenceBundle` 與 verifier 輸出擁有證據真值 (Evidence Truth)**: 作為事後驗證證據，提供給治理閘判定。
4. **`OutcomeMemory / S2TTraceEvent` 僅擁有學習軌跡 (Learning Trace Only)**: 僅作為 shadow 學習評分，預設 enforce_penalties=false，無 runtime 修改權利。
5. **`learning_policy_loader` 僅是政策輸入 (Policy Input Only)**: 僅以唯讀方式載入 policy parameters，不得改變 routing 結構。
6. **治理閘可以進行阻斷（Block），但不能重寫路由（Rewrite）**: 治理閘（如 HallucinationGuard、verifier）若判定失敗必須直接拋出 exception 並 fail-closed，絕不能以「修復」之名將 mode 重新設定為非安全狀態。
7. **復原狀態投影（Recovery Projection）可以讀取 receipts，但不能主導選路**: 復原狀態必須是 RouteDecision 與 CapabilityReceipt 的 shadow 投影，不能成為新的 settlements 真值源。

---

## 6. Recommended Test Gates

規劃下一階段 schema 與 consistency 測試（僅規劃，本任務不實作）：
* **RouteDecision schema consistency test**: 驗證 Plan (list) 與 RouteDecision (tuple) 欄位類型轉換之強型別一致性。
* **CapabilityReceipt required false assertion test**: 驗證 `invoked=False` 時，其 telemetries 內之 `model_calls`、`token_usage`、`provider_costs` 是否亦強制為零。
* **SkillReceipt selected/invoked consistency test**: 驗證 Skill 被 selected 但未 was_injected 時，必拋出 `selected_without_injection` 錯誤。
* **public_claim_safe fail-closed test**: 驗證當 telemetries 丟失或為 `estimated`/`unknown` 時，`public_claim_safe` 必定計算回傳 `False`。
* **evidence_refs required when public_claim_safe=true**: 驗證若允許公開宣告，`evidence_refs` 必須非空。
* **model_call_executed must remain false under H7**: 斷言 H7 期間任何測試跑完後，模型呼叫次數皆為零。
* **provider/network/model-load fields must remain false**: 斷言所有與 provider 及網路相關的 feature flags 與 permissions 均鎖死在 False。
* **selected_candidate_hash / applied_patch_hash missing must block recovery readiness**: 驗證若這兩個 hash 丟失，系統必回傳 `RECOVERY_UNSAFE` 並禁止自癒程序啟動。

---

## 7. Acceptance Criteria

* `docs/reports/h7_3_capability_receipt_field_alignment_audit_v0.md` 檔案確實存在。
* 未修改任何 production code（`nexus/**/*.py` 均未修改）。
* 未修改任何 tests（`tests/**/*.py` 均未修改）。
* 未執行任何 provider / model / network / model-load / model-call。
* 未新增任何路由器。
* 未變更執行期選路行為。
* 未啟用 learned policy。
* 未新增 checkpoint / resume CLI。
* 未將任何 unrelated dirty files 混入 commit。
* 最終狀態字串為：`H7_3_CAPABILITY_RECEIPT_FIELD_ALIGNMENT_AUDIT_DRAFT_READY_FOR_REVIEW`。

---

## 8. Recommended Next Task

### H7-4 RouteDecision / CapabilityReceipt Schema Consistency Test Plan
* **原因**:  
  我們在 H7-3 完成了所有選路與自癒憑證的欄位對齊靜態審計，並找出了 key findings 與自癒 blockers。下一步（H7-4）應撰寫具體的可執行測試計畫（Test Plan），設計如何對上述 schema 與 required false assertions 進行 test gate 檢驗，確保程式在編譯與靜態測試期便能 100% 阻斷 provider 調用與選路雙真值衝突。

---

## 9. Final State

`H7_3_CAPABILITY_RECEIPT_FIELD_ALIGNMENT_AUDIT_DRAFT_READY_FOR_REVIEW`
