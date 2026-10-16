# Local 7B/14B Repair Capability Approval Packet v0

本報告旨在為 Local Qwen2.5 7B / 14B 模型進入 Nexus 修正能力實驗 (Repair Capability Experiment) 準備核准封包 (Approval Packet)。目前 3B Shadow Advisory Stage 3 已經封存，本階段將重點轉向真正的本地修補與驗證能力評估，此任務僅進行核准封包的設計與產出，不涉及任何模型調用、修補套用、運行時整合或公開宣稱。

---

## 1. 本地模型修補實驗目標 (Local Model Repair Objective)
* **評估對象**：本地部署的 Qwen2.5 7B 與 14B 模型。
* **主要目標**：評估其在 Nexus 受控測試套件 (Controlled Harness) 下執行錯誤修補 (Bug Repair) 的能力。
* **主要對比**：相較於 3B 僅具備 advisory-only (影子諮詢) 的限制，7B/14B 將被賦予候選修補規劃與修補提議的角色。
* **內部性質**：所有實驗輸出與指標僅限於內部評估與統計，嚴格禁止用於任何公開 benchmark 宣稱或訓練資料導出。

---

## 2. 模型角色劃分 (Model Roles)
為了在安全與效能之間取得平衡，定義以下模型角色：
* **Qwen2.5 3B**：
  * **角色**：諮詢、評分與主動棄權 (Advisory / Scoring / Abstention only)。
  * **允許動作**：生成諮詢信號、計算程式碼切片得分、評估棄權防護。
  * **禁止動作**：禁止提議 Patch、禁止路由任務、禁止 Verifier 覆寫、禁止修改原始碼。
* **Qwen2.5 7B**：
  * **角色**：候選修補規劃者與小型錯誤修補提議者 (Candidate Patch Planner / Small Repair Proposer)。
  * **允許動作**：提議小型錯誤修補 Patch、規劃 Patch 形狀、生成上下文邊界。
  * **禁止動作**：禁止修改路由、禁止 Verifier 覆寫、禁止自動運行時套用、禁止公開宣稱。
* **Qwen2.5 14B**：
  * **角色**：強力修補提議者與 Verifier 解釋生成器 (Strong Repair Proposer / Verifier-Facing Explanation Generator)。
  * **允許動作**：提議複雜修補 Patch、生成 Verifier 解釋、診斷編譯錯誤。
  * **禁止動作**：禁止修改路由、禁止 Verifier 覆寫、禁止自動運行時套用、禁止公開宣稱。

---

## 3. 修補實驗範圍 (Repair Experiment Scope)
* **初始規模**：6 至 12 個修補任務 (初始方案選定 6 個 Nexus 相容任務)。
* **限制條件**：
  * 僅限於已知的 Nexus 相容錯誤。
  * 禁止向外擴展測試基準 (Benchmark)。
  * 禁止在受控工作區 (Controlled Worktree) 之外進行任何代碼變更。
* **精選任務列表** (對應 `task_selection_plan.jsonl`)：
  1. `astropy_13236`：FITS reader header parsing failure (測試命令：`pytest tests/unit/verifiers/astropy/test_fits_reader.py`)
  2. `astropy_12907`：FITS reader lock helper regression (測試命令：`pytest tests/unit/verifiers/astropy/test_lock_helpers.py`)
  3. `sympy_13031`：Matrices expression evaluation issue (測試命令：`pytest tests/unit/verifiers/sympy/test_matrices.py`)
  4. `django_core_01`：Django migration guard exception (測試命令：`pytest tests/unit/verifiers/django/test_migration_guard.py`)
  5. `concurrency_bug_01`：Buggy targets batch b01 deadlock (測試命令：`pytest tests/unit/verifiers/concurrency/test_deadlock.py`)
  6. `concurrency_bug_02`：Buggy targets batch b02 race condition (測試命令：`pytest tests/unit/verifiers/concurrency/test_race.py`)

---

## 4. 測試套件評估計畫 (Harness Evaluation Plan)
評估模型在 Nexus 控制套件中的以下表現：
* **定位品質 (Localization Quality)**：定位程式碼錯誤點的精準度。
* **修補意圖品質 (Patch Intent Quality)**：修補語義是否符合預期。
* **修補格式有效性 (Patch Format Validity)**：Patch 格式是否符合語法標準。
* **來源定位正確性 (Source Anchor Correctness)**：Patch 錨點是否正確。
* **驗證器結果 (Verifier Result)**：測試套件的編譯與執行結果。
* **重試行為 (Retry Behavior)**：面對驗證失敗時的調整策略。
* **棄權正確性 (Abstention Correctness)**：面對無法修補的錯誤時是否正確選擇棄權。
* **憑證完整性 (Receipt Completeness)**：修補紀錄與證據的完整性。

---

## 5. 成功指標 (Success Criteria)
不使用模糊的「接近 GPT/Gemini」作為直接指標，而是採用以下可量化的內部指標：
* `patch_format_valid_count`：修補格式有效的次數。
* `source_anchor_valid_count`：來源錨點正確的次數。
* `verifier_pass_count`：驗證器通過的任務數。
* `semantic_wrong_count`：語意錯誤（格式正確但邏輯錯誤）的次數。
* `abstention_correct_count`：正確棄權的次數。
* `unsafe_patch_count`：產生不安全程式碼修補的次數。
* `hallucinated_file_count`：虛構檔案的次數。
* `runtime_boundary_violation_count`：違反運行時邊界的次數。
* `average_latency_seconds`：平均修補延遲。
* `average_token_cost`：平均 Token 消耗。

---

## 6. 對照實驗設計 (Comparison Design)
為本地評估準備以下 4 種對照實驗組 (Arm)：
1. **7B Alone**：僅評估 Qwen2.5 7B 的修補能力。
2. **14B Alone**：僅評估 Qwen2.5 14B 的修補能力。
3. **3B Advisory + 7B Repair**：3B 作為諮詢與棄權過濾器，7B 負責提議修補。
4. **3B Advisory + 14B Repair**：3B 作為諮詢與棄權過濾器，14B 負責提議修補。
* **注意**：禁止將任何對照結果用於外部公開宣稱，全部統計數據保持內部封閉。

---

## 7. 終止條件 (Abort Conditions)
一旦觸發以下任一條件，實驗必須立即強制終止：
* 模型試圖編輯未核准的檔案。
* 模型虛構/發明不存在的檔案。
* 模型繞過 Verifier 驗證。
* 模型在 Verifier 未通過時聲稱已解決錯誤。
* 模型要求運行時權限 (Runtime Authority)。
* 模型試圖進行訓練資料導出 (Training Export)。
* 模型產生大範圍、不相關的程式碼重寫。
* 模型觸碰或試圖修改已封存的 M5 / Stage 3 歷史紀錄。

---

## 8. 治理與核准狀態 (Governance Summary)
* **Model Calls Executed**: `false` (無模型調用)
* **Verifier Rerun / Eval Rerun**: `false` (無驗證器重跑)
* **Source Mutation / Patch Apply**: `false` (無原始碼變更或修補套用)
* **Routing / Runtime Connection**: `false` (無路由或運行時連接)
* **Training Export Allowed**: `false` (禁止訓練資料導出)
* **Public Claim Allowed**: `false` (禁止公開宣稱)
* **Execution Approved**: `false` (執行未核准)
* **Human Review Required for Packet Creation**: `false` (此核准封包的建立無需人工審查阻塞)

---

## 9. 決策選項 (Owner Decision Options)
提供給 Owner 決策的 5 個選項（預設決策為拒絕並保持封存）：
1. `APPROVE_LOCAL_7B_14B_REPAIR_CAPABILITY_EXPERIMENT` (核准完整 7B/14B 修補實驗)
2. `APPROVE_14B_ONLY_REPAIR_CAPABILITY_EXPERIMENT` (僅核准 14B 修補實驗)
3. `APPROVE_7B_ONLY_REPAIR_CAPABILITY_EXPERIMENT` (僅核准 7B 修補實驗)
4. `REQUEST_SMALLER_SCOPE` (要求縮小實驗範圍)
5. `REJECT_AND_KEEP_ARCHIVED` (拒絕並保持封存 - 預設)
