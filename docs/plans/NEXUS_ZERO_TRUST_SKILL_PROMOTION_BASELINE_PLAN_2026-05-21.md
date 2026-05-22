# Nexus 零信任技能推廣基準計劃 (2026-05-21)

## 目的

這份文件是後續討論與實作的共同基準。
用途是讓你和其他 agent 在同一份計劃上對齊，不要把「政策文件」、「程式合約」、「runner 隔離」、「runtime 推廣」混在一起。

主要政策目標：

- `docs/arch/NEXUS_SKILL_SELECTION_ZERO_TRUST_PROMOTION_POLICY.md`

主要實作目標：

- `nexus/learning/skill_fit_ablation_core.py`
- `nexus/learning/skill_fit_promotion.py`
- `tests/learning/test_zero_trust_execution_security.py`

## 目前問題

現有 zero-trust skill promotion 政策方向是對的，但目前比較像「治理流程」，還不夠像「執行安全模型」。

紅隊審查指出 4 個必須防住的攻擊路徑：

1. 公開 deterministic exploration hash 可能被惡意技能作者預先計算，強行擠進 exploration arm。
2. Shadow / ablation 如果執行未信任 executable skill，可能外洩資料或消耗資源。
3. Skill 自己產生的 receipt 可能偽造歸因，讓無效技能取得安全角色功勞。
4. 多個 arm 若共享 runtime state，惡意 skill 可能污染 `capability_only` baseline，製造假的正向 delta。

05-21 物理掃描補充了 3 個工程訊號：

1. `graphify-archives/diff_report.md` 顯示 tests 新增 AST 靜態驗證、Case B 違規依賴 Veto、Case D Slop/空函式 Veto。
2. `repomix/diff_report.md` 顯示 `docs/reports/` 造成 docs 打包體量暴增，execution receipt / matrix 不宜無限制寫入 Git。
3. `graphify-archives/diff_report.md` 顯示 Nexus 新增 `Fdiversity_selection` TODO 與 LanceDB delete+add 原子更寫訊號，代表多樣性選臂與大型 evidence storage 需要正式納入設計。

05-21 final compare / settlement 報告再補充 4 個落地缺口：

1. `NEXUS_SF_FINAL_COMPARE_REPORT_2026-05-21.json` 與 `NEXUS_SF_FINAL_CAPABILITY_SKILL_SETTLEMENT_2026-05-21.json` 仍有 264 筆 `run_flash_nexus_live_compare` / `PENDING_LIVE_COMPARE`，代表 live compare 前必須先有 pre-live policy barrier。
2. `NEXUS_SKILL_FIT_CATALOG_REPAIR_AND_CODING_2026-05-15.json` 已將 `addy-browser-testing-with-devtools` 與 `browserbase-fetch` 標記為 `verdict=reject`、`runtime_eligible=false`，但 `failed_security_contract_rules` 尚未結構化填入。
3. `baseline_delta_status=POLLUTED` 目前只描述 arm 無效，還缺 runner cleanup attestation 與 runner quarantine 決策。
4. 歷史 v1 evidence 與 security v2 evidence 若在 settlement schema 中混合累加，會把診斷資料誤當推廣信用。
5. Runtime apply 已出現同一 `skill_id` 在不同 capability 裁決不一致的情境；例如 `browserbase-fetch` 在 `research_control_plane` 被 live-approved，但在 `xray` catalog verdict 被 reject。
6. 多數 applied replacement 仍是 `external_reference_candidate`，必須標記為 `overlay_only_requires_curation`，避免被誤讀為完整 runtime default promotion。
7. P2-lite 先建立 schema-only v2 gate：現有 overlay 全部標記為 `security_contract_version=v1_diagnostic_only`、`promotion_credit_source=none`，讓後續 v2 pipeline 與現有 runtime 路徑分帳。

## 基準決策

後續硬化順序固定如下：

```text
P0：先更新政策文件
P1：再加 fail-closed contract gate
P2：再加 control-plane HMAC
P3：再做 runner isolation
P4：同步 promotion threshold
```

不要一開始就做完整物理 sandbox。
在 runner 能提供可驗證 sandbox attestation 之前，未信任 executable skill arm 必須 fail-closed。

## 架構定位

Skill selection 必須從屬於 capability routing，不能反過來主導 runtime。

```text
Capability Routing
  -> planned skill mount contract
  -> controlled skill ablation / shadow evidence
  -> runtime-signed receipt
  -> promotion threshold contract
  -> manual runtime apply gate
```

Skill selection 不得直接寫入 runtime default。

## 必要生命週期

```text
Candidate
  -> Static Safety Scan
  -> Isolated Offline Exploration
  -> Clean-Slate Ablation
  -> Sandbox Shadow
  -> Signed Promotion Candidate
  -> Manual Runtime Apply Gate
  -> Runtime Default
```

## 非目標

- 不讓 owner-created local skill 自動升級。
- 不把內部 SF/HEEP evidence 當成 public benchmark claim。
- 不把 `selected` 或 `injected` 單獨視為 skill 有效。
- 不透過 `runner_env` 傳遞 secret、signature、privileged proof。
- 不把環境變數 flag 當作 sandbox 已生效的證明。
- 不要求歷史 v1 rows 立刻符合 v2 security contract，但 v1 rows 不得用於 promotion。

## 安全合約

### 0. X-Ray Static Safety Gate

Candidate 進入 Exploration Arm 之前，必須先通過 X-Ray 靜態安全檢查。

最低掃描範圍：

- AST import graph；
- 危險呼叫，例如 `eval`、`exec`、`subprocess`、裸網路請求、未授權檔案寫入；
- 空函式、slop placeholder、無效 wrapper；
- capability mount 與 skill 內容是否語義相符；
- quarantine / vendor / archive / worktree-copy 來源是否被誤標為 runtime-ready。

Veto 規則：

- Case B：違規依賴或未授權外部能力，直接 `FAIL_CLOSED`。
- Case D：空函式、slop、假實作，直接 `FAIL_CLOSED`。
- X-Ray Gate 失敗的技能不得寫入 promotion-eligible matrix。
- X-Ray Gate 可允許 non-promotion diagnostics，但必須標記為 `promotion_eligible=false`。

### 1. Control-Plane HMAC Exploration

Exploration quota assignment 必須在 control-plane 使用 secret-backed HMAC：

```text
HMAC-SHA256(NEXUS_SYSTEM_SALT, capability|skill_id|commit|epoch)
```

規則：

- `NEXUS_SYSTEM_SALT` 不得寫入 repo。
- `NEXUS_SYSTEM_SALT` 不得放入 `runner_env`。
- Matrix / artifact rows 只能保存非敏感資訊：
  - `exploration_bucket_id`
  - `salt_epoch`
  - `digest_prefix`
- production 或 CI security mode 缺 salt 時必須 fail-closed。
- local development 可使用明確的 non-production test salt，但輸出必須標記為 non-promotion-eligible。
- 多樣性選臂，例如 `Fdiversity_selection`，必須共用同一套 HMAC bucket，不得另開公開 deterministic shuffle。
- HMAC input 必須包含 capability、skill_id、commit、epoch，以及 diversity lane id，避免候選人透過調整 capability mount 或名稱後綴操控分桶。

### 2. Sandbox Attestation

Matrix row 只能宣告「需要 sandbox attestation」：

```json
{
  "requires_sandbox_attestation": true
}
```

只有 runner result row 可以提供實際觀測到的 sandbox attestation：

```json
{
  "sandbox_attestation": {
    "issuer": "nexus.runner",
    "sandbox_mode": "macos_sandbox|linux_cgroup|mocked_non_promotion",
    "network_disabled": true,
    "workspace_isolated": true,
    "tmp_isolated": true,
    "env_allowlist_hash": "...",
    "resource_limits": {
      "cpu": "...",
      "memory_mb": 512,
      "timeout_sec": 3
    },
    "teardown_status": "PASS",
    "artifact_hash": "...",
    "signature": "..."
  }
}
```

規則：

- skill 不能自證 sandbox 狀態。
- macOS 若沒有可驗證 sandbox 路徑，未信任 executable shadow / ablation arm 必須 fail-closed。
- prompt-only、metadata-only、mock-backed 的 non-promotion evaluation 可以不要求 executable sandbox attestation，但必須明確標記為 non-promotion-eligible。

### 3. Runtime-Signed Receipt Provenance

Skill output 只能視為 raw observation。
Promotion evidence 必須使用 runtime-signed receipt provenance。

v2 promotion eligibility 需要以下欄位：

```json
{
  "receipt_provenance": "runtime_signed",
  "receipt_signature": "...",
  "receipt_signature_inputs": {
    "row_id": "...",
    "arm_id": "...",
    "artifact_hash": "...",
    "receipt_hash": "..."
  }
}
```

規則：

- `receipt_signature` 必須由 runtime observer 在執行後產生。
- `receipt_signature` 不得透過環境變數注入。
- skill-supplied receipt 只能保存為 raw observation。
- skill-supplied attribution 不能取得 safety-role veto 或 promotion credit。

### 4. Clean-Slate Isolation 與 Baseline Sandwich

Baseline pollution 必須由 runtime observer 判斷，不能由 skill output 自填。

建議 row shape：

```json
{
  "baseline_sandwich": {
    "enabled": true,
    "baseline_before_hash": "...",
    "skill_arm_hash": "...",
    "baseline_after_hash": "...",
    "baseline_delta_status": "CLEAN|POLLUTED|INCONCLUSIVE",
    "pollution_detector_provenance": "runtime_observer"
  }
}
```

規則：

- promotion-eligible executable arm 必須有 `baseline_before -> skill_arm -> baseline_after`。
- `baseline_delta_status=POLLUTED` 必須讓該 skill arm 無效。
- `baseline_delta_status=INCONCLUSIVE` 可用於診斷，但不能用於 promotion。
- 每個 arm 應使用獨立 workspace、tmp dir、env allowlist、artifact dir、memory/cache namespace。

### 5. Evidence Storage Boundary

大型 execution receipts、matrix rows、raw replay rows 不應無限制寫入 Git-tracked `docs/reports/`。

規則：

- Git-tracked reports 優先保存 summary、decision packet、diff report、hash locator。
- Raw execution receipts 優先保存到隔離 evidence store，例如 LanceDB 或本地 SQLite。
- 若使用 LanceDB，更新策略必須保留 delete+add 原子語義，避免半寫入污染檢索結果。
- Manual Gate 需要人工審核時，才從 evidence store 導出最小可讀 report。
- promotion evidence 必須保存 artifact hash 與 evidence locator，讓後續可重播、可審計，但不把所有 raw matrix 長期塞進 Git。

### 6. Pre-Live Zero-Trust Barrier

所有 `PENDING_LIVE_COMPARE` 在發起實體 live compare 前，必須先通過 pre-live policy barrier。

建議 row shape：

```json
{
  "pre_live_gate": {
    "status": "PASS|BLOCKED_BY_POLICY",
    "blocked_reason": "missing_sandbox_attestation|xray_failed|missing_runtime_signed_receipt|security_contract_version_mismatch",
    "requires_sandbox_attestation": true,
    "executable_skill": true,
    "promotion_eligible": false
  }
}
```

規則：

- executable candidate 缺 sandbox attestation contract 時，不得進入 `run_flash_nexus_live_compare`。
- blocked candidate 應寫入 matrix / settlement 為 `BLOCKED_BY_POLICY`，而不是排隊等待 live compare。
- prompt-only 或 metadata-only diagnostic 可以進入 non-promotion compare，但必須標記 `promotion_eligible=false`。
- pre-live barrier 必須在 runner 啟動前執行，不能依賴 runner 執行後才回報 blocked。
- runtime apply 必須檢查 catalog reject conflict：同 capability reject 直接 blocker，跨 capability reject 寫入 warning。
- runtime apply 必須計算 `external_reference_applied_count`、`requires_curation_count`，並把外部候選標記為 `runtime_review_scope=overlay_only_requires_curation`。
- runtime apply 必須輸出 schema-only v2 gate 欄位：`security_contract_version`、`promotion_credit_source`、`v1_evidence_count`、`v2_evidence_count`、`v2_trust_mismatch_count`、`v2_promotion_eligible`。

### 7. Reject Verdict Attribution 與 Arm Integrity

所有 reject verdict 必須包含結構化安全歸因，避免日後只看到 `runtime_eligible=false`，卻不知道是 X-Ray、HMAC、sandbox、receipt、baseline 哪個合約失敗。

建議 verdict shape：

```json
{
  "verdict": "reject",
  "runtime_eligible": false,
  "failed_security_contract_rules": [
    "XRAY_DEPENDENCY_VETO",
    "MISSING_SANDBOX_ATTESTATION",
    "MISSING_RUNTIME_SIGNED_RECEIPT"
  ],
  "arm_integrity": {
    "salt_epoch": "2026-05-21",
    "digest_prefix": "...",
    "digest_signature_status": "PASS|FAIL|MISSING"
  }
}
```

規則：

- `failed_security_contract_rules` 不能為空陣列或 `null`。
- HMAC helper 完成後，reject / blocked / promoted verdict 都必須保存 `salt_epoch`、`digest_prefix`、`digest_signature_status`。
- `digest_prefix` 只能作為 audit locator，不能作為可逆 secret。
- `digest_signature_status != PASS` 的 arm 不得取得 exploration credit 或 promotion credit。
- reject / blocked / applied verdict 若與其他 capability verdict 衝突，decision artifact 必須保存 `reject_conflict_warnings`。
- `verdict=reject` 或 `runtime_eligible=false` 的 catalog row 必須填入非空 `failed_security_contract_rules`。

### 8. Cleanup Attestation 與 Runner Quarantine

`baseline_delta_status=POLLUTED` 不只代表該 arm 無效，也代表 runner 可能已被污染。

建議 cleanup shape：

```json
{
  "cleanup_attestation": {
    "required": true,
    "teardown_status": "PASS|FAIL|INCONCLUSIVE",
    "runner_quarantine_status": "NONE|QUARANTINED",
    "cleanup_observer": "nexus.runner",
    "artifact_hash": "...",
    "signature": "..."
  }
}
```

規則：

- `POLLUTED` 後必須執行 clean-slate reset。
- reset 成功才可繼續使用該 runner node。
- `teardown_status != PASS` 時，runner node 必須標記為 `QUARANTINED`。
- quarantine runner 不能承接後續 live compare、shadow、ablation 任務。

### 9. v1/v2 Evidence Isolation

Settlement schema 必須把 v1 診斷 evidence 與 v2 promotion evidence 物理分離。

建議 settlement shape：

```json
{
  "evidence_accounting": {
    "v1_evidence_count": 0,
    "v2_evidence_count": 0,
    "v2_trust_mismatch_count": 0,
    "promotion_credit_source": "v2_only"
  }
}
```

規則：

- `v1_evidence_count` 可用於診斷與回放優先級，不得折算 promotion credit。
- promotion 判定必須單獨要求 `v2_evidence_count >= N`。
- promotion 判定必須要求 `v2_trust_mismatch_count == 0`。
- settlement summary 必須同時輸出 v1/v2 數字，讓 reviewer 看見歷史資料與合格資料的差距。

## Security V2 適用範圍

新的 v2 checks 只在以下條件同時成立時套用：

```text
security_contract_version >= v2
arm_type in ("skill_ablation", "wrong_or_quarantined_skill", "shadow_arm")
executable_skill == true
promotion_eligible == true
```

歷史 v1 rows：

- 可以繼續讀取；
- 可以用於診斷；
- 不得變成 promotion evidence，除非用 v2 contracts 重新 replay。
- settlement 可以統計 `v1_evidence_count`，但 `promotion_credit_source` 必須是 `v2_only`。
- P2-lite 階段的 runtime overlay artifact 必須明確標記 `promotion_credit_source=none`，代表此路徑不產生 promotion credit。

## 實作計劃

### P0 - Policy Update

修改：

- `docs/arch/NEXUS_SKILL_SELECTION_ZERO_TRUST_PROMOTION_POLICY.md`

內容：

- 將公開 deterministic hash 改成 control-plane HMAC。
- 新增 sandbox attestation contract。
- 新增 runtime-signed receipt provenance contract。
- 新增 clean-slate isolation 與 baseline sandwich contract。
- 新增 X-Ray static safety gate，包含 Case B / Case D veto。
- 新增 evidence storage boundary，避免 raw receipts / matrix 無限制寫入 Git。
- 新增 v1/v2 compatibility boundary。
- 新增 pre-live barrier，讓不合格 executable candidate 在 live compare 前 `BLOCKED_BY_POLICY`。
- 新增 reject verdict attribution，強制 `failed_security_contract_rules` 與 HMAC arm integrity metadata。
- 新增 cleanup attestation 與 runner quarantine rule。
- 新增 v1/v2 evidence accounting schema，防止 v1 診斷資料被當成 v2 推廣信用。
- 明確寫出：未信任 executable shadow / ablation arm 若沒有 sandbox attestation，必須 fail-closed。

驗收：

- policy 明確寫出 salt 不得進 `runner_env`。
- policy 明確寫出 skill 不能自證 sandbox 或 receipt provenance。
- policy 明確寫出 v1 rows 不能 promotion。
- policy 明確寫出 X-Ray Veto 失敗不得進 promotion-eligible matrix。
- policy 明確寫出 raw execution evidence 預設走隔離 store，Git 只保留 summary / locator / hash。
- policy 明確寫出 `PENDING_LIVE_COMPARE` 之前先跑 pre-live gate。
- policy 明確寫出 `failed_security_contract_rules` 不能為 null。
- policy 明確寫出 `POLLUTED` 需要 cleanup attestation，cleanup 失敗要 quarantine runner。
- policy 明確寫出 promotion credit 只能來自 v2 evidence。

### P1 - Ablation Row Gate

修改：

- `nexus/learning/skill_fit_ablation_core.py`

內容：

- 在 `evaluate_skill_fit_ablation_rows` 新增 row-level v2 security gate。
- promotion-eligible executable skill rows 在以下狀況必須 RETURN：
  - `xray_gate_status != "PASS"`
  - `receipt_provenance != "runtime_signed"`
  - `baseline_sandwich.baseline_delta_status != "CLEAN"`
  - `requires_sandbox_attestation=true` 但 `sandbox_attestation` 缺失或無效
  - `trust_mismatch=true`
- live compare dispatch 前新增 pre-live gate：
  - executable candidate 缺 sandbox attestation contract 時，標記 `BLOCKED_BY_POLICY`
  - `security_contract_version` 缺失或低於 v2 時，標記 non-promotion 或 `BLOCKED_BY_POLICY`
  - reject / blocked rows 必須填入 `failed_security_contract_rules`
- runtime apply 前新增 reject conflict gate：
  - same capability `verdict=reject` 或 `runtime_eligible=false` 時，標記 blocker
  - cross capability reject 時，寫入 `reject_conflict_warnings`，不自動阻擋
- runtime apply artifact 新增審計 summary：
  - `reject_conflict_warning_count`
  - `external_reference_applied_count`
  - `requires_curation_count`
  - `runtime_review_scope=overlay_only`
- runtime apply artifact 新增 schema-only v2 gate：
  - `security_contract_version=v1_diagnostic_only`
  - `promotion_credit_source=none`
  - `v1_evidence_count=<applied replacement count>`
  - `v2_evidence_count=0`
  - `v2_trust_mismatch_count=0`
  - `requires_sandbox_attestation=true`
  - `sandbox_attestation_status=missing_not_required_for_overlay_only`
  - `v2_promotion_eligible=false`
- `baseline_delta_status=POLLUTED` 時要求 `cleanup_attestation.teardown_status == "PASS"`；否則標記 runner quarantine。
- 保留歷史 v1 row 可讀，但不能 promotion。

驗收：

- 缺 runtime-signed receipt 會 RETURN。
- X-Ray Case B / Case D veto 會 RETURN。
- baseline pollution 會 RETURN。
- executable promotion-eligible arm 缺 sandbox attestation 會 RETURN。
- pending live compare 缺 pre-live contract 會變成 `BLOCKED_BY_POLICY`。
- reject verdict 的 `failed_security_contract_rules` 不再為 null。
- same capability reject conflict 會阻止 runtime apply。
- cross capability reject conflict 會寫入 warning。
- external reference applied winner 會標記 `requires_curation=true`。
- reject verdict 會輸出非空 `failed_security_contract_rules`。
- schema-only v2 gate 會把現有 overlay 標記為 v1 diagnostic only，且不給 promotion credit。
- cleanup 失敗會產生 runner quarantine 狀態。

### P2 - Control-Plane HMAC Helper

修改：

- `nexus/learning/skill_fit_ablation_core.py`

內容：

- 新增 `_secure_explore_digest(capability, skill_id, commit, epoch, salt)`。
- 只在 control-plane selection 階段使用。
- Matrix rows 只輸出非敏感 digest metadata。
- 測試確認 `runner_env` 不含 `NEXUS_SYSTEM_SALT`。
- `Fdiversity_selection` 必須使用同一個 HMAC helper，並把 diversity lane id 納入 input。

驗收：

- 測試證明 salt 會改變 bucket assignment。
- 測試證明 matrix row 不包含 raw salt。
- 測試證明 diversity selection 不使用公開 deterministic shuffle。

### P3 - Promotion Threshold Sync

同步修改：

- `nexus/learning/skill_fit_ablation_core.py`
- `nexus/learning/skill_fit_promotion.py`

對 `build_skill_promotion_threshold_contract` 新增 threshold requirements：

```text
requires_runtime_signed_receipt = true
requires_clean_slate_isolation = true
requires_sandbox_attestation = true for executable promotion-eligible arms
requires_trust_mismatch_zero = true
requires_failed_security_contract_rules = true for reject/block verdicts
promotion_credit_source = v2_only
min_v2_evidence_count = N
```

驗收：

- 兩個 module 回傳一致的 threshold fields。
- positive skill verdict 若沒有 security v2 evidence，不能進入 validation-ready。
- v1 evidence 不得讓 candidate 滿足 promotion threshold。
- `v2_trust_mismatch_count > 0` 必須阻止 promotion。

### P4 - Test Coverage

新增：

- `tests/learning/test_zero_trust_execution_security.py`

必要測試：

- HMAC helper 不需要透過 `runner_env` 傳 salt。
- 產生的 matrix rows 不包含 `NEXUS_SYSTEM_SALT`。
- 缺 `runtime_signed` receipt 會 fail-closed。
- `baseline_delta_status=POLLUTED` 會 fail-closed。
- executable promotion-eligible arm 缺 sandbox attestation 會 fail-closed。
- 歷史 v1 row 可讀但不可 promotion。
- 兩邊 `build_skill_promotion_threshold_contract` fields 一致。
- `PENDING_LIVE_COMPARE` executable candidate 缺 pre-live contract 時輸出 `BLOCKED_BY_POLICY`。
- reject verdict 必須包含非空 `failed_security_contract_rules`。
- same capability reject conflict 必須 RETURN。
- cross capability reject conflict 必須出現在 `reject_conflict_warnings`。
- external reference winner 必須出現在 `requires_curation_count`，且單筆 row 標記 `runtime_review_scope=overlay_only_requires_curation`。
- schema-only v2 gate 必須輸出 `security_contract_version=v1_diagnostic_only`、`promotion_credit_source=none`、`v2_promotion_eligible=false`。
- `baseline_delta_status=POLLUTED` 且 cleanup 失敗時 runner 進入 quarantine。
- `v1_evidence_count > 0` 但 `v2_evidence_count < N` 不得 promotion。

驗證指令：

```bash
uv run pytest tests/learning/test_zero_trust_execution_security.py
```

### P5 - Runner Isolation Follow-Up

P0-P4 不等待完整物理 sandbox 實作。

另開後續 runner 任務：

- macOS sandbox launcher 調研；
- Linux cgroup / network namespace mode；
- env allowlist hashing；
- per-arm tmp / workspace / artifact namespace；
- runtime observer signature generation；
- teardown proof。
- cleanup attestation signature；
- runner quarantine registry。

在上述能力完成前，未信任 executable shadow / ablation arm 保持 fail-closed。

### P6 - Evidence Store Follow-Up

另開後續 storage 任務：

- 定義 raw execution receipt 的 SQLite / LanceDB schema。
- 建立 Git summary report 與 evidence store locator 的對應格式。
- 建立 delete+add 原子更新測試，避免 LanceDB 版本差異造成半寫入。
- 建立 `docs/reports/` 大型 JSON 輸出限制，避免重複膨脹 repo。
- settlement schema 物理分離 `v1_evidence_count`、`v2_evidence_count`、`v2_trust_mismatch_count`、`promotion_credit_source`。
- reject / blocked / promoted verdict 都保存最小 arm integrity metadata。

P6 不阻塞 P0-P4，但 Manual Gate 前必須能從 evidence locator 導出最小審計報告。

## Agent 協作規則

實作本計劃的 agent 必須回報：

```text
retrieved lesson:
source path:
applicability:
plan change:
```

不得 full-read 所有歷史 reports。
只能 targeted retrieval。

編輯前必須檢查：

- `AGENTS.md`
- `MUSE_PROTO.md`
- 本計劃
- `docs/arch/NEXUS_SKILL_SELECTION_ZERO_TRUST_PROMOTION_POLICY.md`
- `tests/learning/` 下相關測試
- `/Users/jameschen/Workspace/nexus-perplexity/repomix/diff_report.md`
- `/Users/jameschen/Workspace/nexus-perplexity/graphify-archives/diff_report.md`

## 最終證據要求

實作完成時必須回報：

- Change log 與 touched files。
- 測試指令與結果。
- `NEXUS_SYSTEM_SALT` 是否出現在任何 matrix `runner_env`。
- X-Ray Gate 是否阻止 Case B / Case D 類候選進入 promotion-eligible matrix。
- v1 rows 是否在 v2 下 non-promotable。
- executable promotion-eligible arms 是否需要 sandbox attestation。
- 兩邊 promotion threshold contracts 是否同步。
- raw execution evidence 是否避免無限制寫入 Git-tracked `docs/reports/`。
- `PENDING_LIVE_COMPARE` 是否先經過 pre-live gate，缺合約時是否 `BLOCKED_BY_POLICY`。
- reject verdict 是否填入非空 `failed_security_contract_rules`。
- `POLLUTED` 是否要求 cleanup attestation，cleanup 失敗是否 quarantine runner。
- settlement 是否物理分離 v1/v2 evidence count，且 promotion credit 是否 `v2_only`。

## 殘餘風險

這份計劃只建立 fail-closed gates 與政策邊界。
它本身不等於完整物理 sandbox。

在 runner-level sandbox attestation 與 runtime observer signing 實作並測試前，public 或 production promotion 必須保持 blocked。
