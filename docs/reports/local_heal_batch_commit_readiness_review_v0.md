# Local Heal Batch Commit Readiness Review v0 任務報告

## 1. 執行摘要 (Executive Summary)
本報告為 `local_heal_batch_commit_readiness_review_v0`，對 10 個 local_heal modified 檔案進行純唯讀審核（不 stage、不 commit），評估是否能以 batch 或需要拆成子包進行提交。

**結論：SPLIT_REQUIRED** — 不可 batch commit，因為偵測到跨檔合約破壞點。

## 2. Source Validation
* **archive_status**: PAUSED_ARCHIVED
* **strategy_envelope_gate_accepted**: true (Commit: 064947d0)
* **task_is_review_only**: true
* **source_validation_status**: PASS

## 3. Candidate Inventory
| 檔案路徑 | diff_stat |
|---------|----------|
| context.py | +4/-0 |
| context_budget.py | +1/-1 |
| evidence_compactor.py | +121/-0 |
| interface.py | +2/-0 |
| localizer.py | +15/-237 |
| phases/planning.py | +34/-0 |
| phases/reproduction.py | +81/-1 |
| protocol.py | +144/-7 |
| repomap.py | +163/-1 |
| reproduction.py | +4/-0 |

**總計**：10 files changed, 553 insertions(+), 256 deletions(-)

## 4. Cross-file Contract Review
* **contract_breakage_detected**: TRUE
* **主要破壞點**：
  1. `localizer.py` — Localizer class 完全廢棄（-237 行）。依賴 `Localizer` 的呼叫方將在執行時失敗。
  2. `protocol.py` — 模糊匹配 fallback 行為反轉：相似度 0.75-0.85 現在返回 FAIL（原本 >0.85 才 pass，但此次改為候選紀錄而非自動修正）。
  3. `PatchSynthesisOutput.errors` 新增欄位可能影響消費端。

## 5. Test Pairing
* **available tests**: test_patch_protocol.py, test_evidence_compactor.py, test_env_taxonomy_and_preflight.py, test_decoupled_architecture_tdd.py, test_surgical_context_builder.py
* **tests_needed_before_commit**: protocol.py + evidence_compactor.py + reproduction phases 均需針對性測試通過
* **no_test_commit_acceptable**: FALSE

## 6. Split or Batch Decision
**決定：SPLIT_REQUIRED**

推薦 6 個子包進行逐一 gate：
| 子包 | 檔案 | 風險 | 需要測試？ |
|-----|------|-----|---------|
| SP1 | context.py, context_budget.py, reproduction.py | low | No |
| SP2 | protocol.py, interface.py | high | Yes |
| SP3 | evidence_compactor.py | medium | Yes |
| SP4 | localizer.py | high | Yes + caller audit |
| SP5 | repomap.py | high | Yes |
| SP6 | phases/planning.py, phases/reproduction.py | high | Yes |

## 7. Risk and Blast Radius
* **High-risk**: localizer.py (deprecation), protocol.py (behavior inversion), repomap.py (new subsystem), phases/reproduction.py (preflight guard)
* **Medium-risk**: evidence_compactor.py, context_budget.py, phases/planning.py
* **Failure modes**: Localizer callers break, patch failure rate increase, context token truncation

## 8. Recommended Owner Decision
**推薦**：先從 SP1（低風險 stub fields）開始，再進行 SP2（protocol/interface，最高 pipeline 影響力）。

可選決策：
- `APPROVE_LOCAL_HEAL_STUB_FIELDS_SUBPACKET_GATE` (SP1: low-risk, no test needed)
- `APPROVE_LOCAL_HEAL_PROTOCOL_INTERFACE_SUBPACKET_GATE` (SP2: high-risk, requires test gate)
- `APPROVE_LOCAL_HEAL_EVIDENCE_COMPACTOR_SUBPACKET_GATE` (SP3)
- `APPROVE_LOCAL_HEAL_LOCALIZER_DEPRECATION_SUBPACKET_GATE` (SP4: requires caller audit)
- `APPROVE_LOCAL_HEAL_REPOMAP_SUBPACKET_GATE` (SP5)
- `APPROVE_LOCAL_HEAL_PHASES_SUBPACKET_GATE` (SP6)
- `APPROVE_RUST_MAIN_PACKET_ONLY_COMMIT_GATE` (skip local_heal, handle Rust first)
- `REMAIN_PAUSED_NO_LOCAL_HEAL_COMMIT`

## 9. Governance Preservation
* archive_status: PAUSED_ARCHIVED (維持)
* 無 staging / commit / model calls / repair execution / verifier rerun / S2T / training export / public claim / runtime routing / StraTA S1
* .tmp_build dirty state 未觸碰
* nexus-core-rs/src/main.rs 未觸碰
