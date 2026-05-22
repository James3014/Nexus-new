# Nexus Zero-Trust V2 Promotion Implementation Plan (2026-05-21)

## 目的

這份文件定義 Zero-Trust V2 promotion 的實作路徑。

它不是取代目前 runtime overlay 的立即切換計劃，而是建立第二條更嚴格的 promotion pipeline。

核心原則：

```text
A 路徑：現有 runtime overlay
  狀態：v1_diagnostic_only
  用途：繼續 runtime routing
  限制：不產生 promotion credit

B 路徑：Zero-Trust V2 promotion pipeline
  狀態：v2 evidence only
  用途：未來正式取代 A 路徑
  限制：未通過完整 gate 前不能宣稱 runtime default promotion
```

## 現況

目前 runtime apply artifact 已完成 P2-lite schema 分帳：

- `status=PASS`
- `runtime_update_allowed=true`
- `public_benchmark_allowed=false`
- `runtime_review_scope=overlay_only`
- `security_contract_version=v1_diagnostic_only`
- `promotion_credit_source=none`
- `v1_evidence_count=19`
- `v2_evidence_count=0`
- `v2_trust_mismatch_count=0`
- `requires_sandbox_attestation=true`
- `sandbox_attestation_status=missing_not_required_for_overlay_only`
- `v2_promotion_eligible=false`
- `external_reference_applied_count=19`
- `requires_curation_count=19`
- `reject_conflict_warning_count=1`

目前主要風險：

1. 19 個 applied replacement 多數仍是 `external_reference_candidate`。
2. 現有 evidence 只能作為 v1 diagnostic，不可折算 v2 promotion credit。
3. `browserbase-fetch` 有 cross-capability reject warning：`research_control_plane` applied，但 `xray` rejected。
4. 尚未有 runner-level sandbox attestation。
5. 尚未有 runtime-signed receipt。
6. 尚未有 clean-slate baseline sandwich。
7. Raw evidence 仍可能持續膨脹 `docs/reports/`。

## Retrieved Lessons

```text
source path:
nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md

applicability:
runtime_eligible 與 ablation_eligible 不可混用；external/reference winners 不能被當作 fully promoted runtime defaults。

plan change:
V2 先要求 curation/replay/attestation，而不是直接把目前 overlay 升格。現有 overlay 保持 A 路徑；V2 新建 B 路徑。
```

```text
source path:
docs/arch/NEXUS_SKILL_SELECTION_ZERO_TRUST_PROMOTION_POLICY.md

applicability:
現有政策已定義 reject conflict gate、external candidate boundary、schema-only v2 gate。

plan change:
V2 實作必須沿用這些欄位，不另造相近語義欄位。
```

```text
source path:
docs/reports/NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json

applicability:
目前 overlay 已明確 `v2_evidence_count=0`、`promotion_credit_source=none`。

plan change:
V2 plan 從 replay/shadow 收集新證據開始，不允許沿用舊 v1 evidence 直接 promotion。
```

## Scope

### In Scope

- 定義 V2 promotion 的 artifact schema。
- 定義 19 個 applied replacement 的 curation backlog。
- 定義 runtime-signed receipt contract。
- 定義 sandbox attestation contract。
- 定義 clean-slate baseline sandwich contract。
- 定義 V2 replay/shadow matrix。
- 定義 promotion threshold contract。
- 定義 manual apply、downgrade、revert policy。
- 定義 evidence store migration path。
- 定義測試與 rollout 順序。

### Out of Scope

- 不立即移除目前 runtime overlay。
- 不立即把 19 個 replacement revert。
- 不立即啟用 public benchmark。
- 不在第一階段實作完整物理 sandbox。
- 不把 v1 evidence 折算為 v2 promotion credit。
- 不讓 skill 自行產生 promotion receipt。

## V2-0：不可破壞邊界

### 目標

保留目前可用 runtime overlay，同時防止語義上升格。

### 必要規則

- 現有 overlay 繼續使用 `runtime_review_scope=overlay_only`。
- 現有 applied replacement 保持 `requires_curation=true`。
- 現有 evidence 保持：
  - `security_contract_version=v1_diagnostic_only`
  - `promotion_credit_source=none`
  - `v2_evidence_count=0`
  - `v2_promotion_eligible=false`
- V2 pipeline 的輸出不得覆寫 A 路徑，除非 manual apply gate 通過。

### 驗收

- Runtime smoke 仍 `34/34 PASS`。
- Public benchmark 仍 `false`。
- 任何 V2 失敗不得降低現有 runtime overlay 可用性。

## V2-1：Curation Backlog for 19 Applied Replacements

### 目標

把 19 個 applied replacement 轉成可追蹤的 curation backlog。

### Artifact

新增：

```text
docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json
```

建議 schema：

```json
{
  "schema": "nexus.zero_trust_v2.curation_backlog.v1",
  "status": "PASS",
  "source_runtime_apply_decision": "docs/reports/NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json",
  "summary": {
    "candidate_count": 19,
    "requires_curation_count": 19,
    "cross_capability_reject_warning_count": 1,
    "v2_ready_count": 0
  },
  "items": [
    {
      "capability_id": "...",
      "skill_id": "...",
      "source_status": "external_reference_candidate",
      "current_runtime_scope": "overlay_only_requires_curation",
      "curation_status": "PENDING",
      "priority": "P0|P1|P2",
      "risk_flags": ["cross_capability_reject_conflict"],
      "required_next_steps": [
        "source_review",
        "xray_static_scan",
        "v2_replay",
        "sandbox_shadow"
      ]
    }
  ]
}
```

### Priority

- P0：security / governance / file / policy / browser / external network 類 capability。
- P1：核心工程能力，例如 codeintel、repair_loop、sandbox_replay。
- P2：低風險或非敏感 productivity 類。

### 驗收

- 19 個 applied replacement 全部出現在 backlog。
- `browserbase-fetch` 帶有 `cross_capability_reject_conflict` risk flag。
- backlog 不改 runtime overlay。

## V2-2：Runtime-Signed Receipt Schema

### 目標

把 skill output 與 promotion receipt 分離。

### 規則

- Skill output 只能是 raw observation。
- Promotion credit 只能由 runtime observer 簽發。
- Receipt signature 不得由 skill 自填。
- Receipt signature 不得透過 `runner_env` 傳入。

### Schema

```json
{
  "receipt_provenance": "runtime_signed",
  "receipt_signature": "...",
  "receipt_signature_algorithm": "hmac-sha256|ed25519",
  "receipt_signature_inputs": {
    "run_id": "...",
    "row_id": "...",
    "arm_id": "...",
    "capability_id": "...",
    "skill_id": "...",
    "artifact_hash": "...",
    "raw_observation_hash": "...",
    "receipt_hash": "..."
  },
  "observer": {
    "issuer": "nexus.runtime_observer",
    "version": "..."
  }
}
```

### Stop Conditions

- Missing `receipt_signature` -> `BLOCKED_BY_POLICY`
- `receipt_provenance != runtime_signed` -> non-promotion diagnostic only
- Skill-supplied attribution -> no promotion credit

## V2-3：Sandbox Attestation Schema

### 目標

未信任 executable skill 不能靠環境變數自證安全。

### Schema

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

### Implementation Path

1. `mocked_non_promotion`：先支援測試與 schema，不給 promotion credit。
2. `macos_sandbox`：本機 runner 先做最小隔離。
3. `linux_cgroup`：CI / container runner 再做硬限制。

### Stop Conditions

- executable arm 缺 attestation -> `BLOCKED_BY_POLICY`
- `network_disabled != true` -> no promotion
- `workspace_isolated != true` -> no promotion
- `teardown_status != PASS` -> runner quarantine

## V2-4：Clean-Slate Baseline Sandwich

### 目標

防止 skill 污染 baseline，製造假的 positive delta。

### Flow

```text
baseline_before
  -> skill_arm
  -> baseline_after
```

### Schema

```json
{
  "baseline_sandwich": {
    "enabled": true,
    "baseline_before_hash": "...",
    "skill_arm_hash": "...",
    "baseline_after_hash": "...",
    "baseline_delta_status": "CLEAN|POLLUTED|INCONCLUSIVE",
    "pollution_detector_provenance": "runtime_observer"
  },
  "cleanup_attestation": {
    "required": true,
    "teardown_status": "PASS|FAIL|INCONCLUSIVE",
    "runner_quarantine_status": "NONE|QUARANTINED",
    "signature": "..."
  }
}
```

### Stop Conditions

- `baseline_delta_status=POLLUTED` -> arm invalid
- `baseline_delta_status=INCONCLUSIVE` -> diagnostic only
- `teardown_status != PASS` -> quarantine runner

## V2-5：V2 Replay / Shadow Matrix

### 目標

為 backlog 中的候選建立 V2 evidence，不影響 A 路徑 runtime output。

### Matrix Arms

```text
capability_only_v2
candidate_skill_v2
wrong_or_quarantined_skill_v2
shadow_candidate_v2
```

### Required Fields

```json
{
  "security_contract_version": "v2",
  "promotion_credit_source": "v2_only",
  "requires_sandbox_attestation": true,
  "requires_runtime_signed_receipt": true,
  "requires_clean_slate_isolation": true,
  "requires_trust_mismatch_zero": true,
  "requires_negative_control_block": true
}
```

### Dispatch Rules

- Pre-live gate must run before runner dispatch.
- V1 rows can be copied as context but must remain `promotion_credit_source=none`.
- V2 rows cannot reuse v1 receipt hashes as promotion evidence.
- Shadow output must not affect runtime response.

## V2-6：Promotion Threshold Contract

### Minimum Requirements

```text
security_contract_version == v2
promotion_credit_source == v2_only
v2_evidence_count >= N
v2_trust_mismatch_count == 0
negative_control_blocked_count >= 1
receipt_provenance == runtime_signed
sandbox_attestation.status == PASS
baseline_delta_status == CLEAN
cleanup_attestation.teardown_status == PASS
public_benchmark_allowed == false unless separately approved
```

### Initial N

建議先用：

```text
N = 3 for local curation review
N = 10 for runtime review ready
N = 30 for public claim precheck
```

### Output

```json
{
  "schema": "nexus.zero_trust_v2.promotion_candidate.v1",
  "status": "READY_FOR_MANUAL_APPLY|BLOCKED|DIAGNOSTIC_ONLY",
  "capability_id": "...",
  "skill_id": "...",
  "v2_evidence_count": 10,
  "v2_trust_mismatch_count": 0,
  "promotion_credit_source": "v2_only",
  "manual_apply_required": true
}
```

## V2-7：Manual Apply / Downgrade / Revert Policy

### Manual Apply

V2 pass 不得自動改 runtime default。

必須產生：

- runtime policy patch plan
- evidence locator
- decision summary
- rollback plan
- reviewer sign-off field

### Downgrade

若 V2 replay 發現 current overlay skill 有安全問題：

```text
severity=critical -> block new runs + recommend immediate revert
severity=high -> stop promotion + mark requires investigation
severity=medium -> keep overlay + require additional V2 evidence
severity=low -> keep overlay + note warning
```

### Revert

Revert 必須保留：

- reverted capability
- previous skill
- reason
- evidence ref
- validation command

## V2-8：Evidence Store Migration

### 目標

避免 raw matrix / receipt 繼續灌爆 `docs/reports/`。

### Path

1. Git reports 保留 summary / decision / locator / hash。
2. Raw evidence 移到 SQLite 或 LanceDB。
3. LanceDB update 保留 delete+add 原子語義。
4. Manual Gate 時才導出最小審計報告。

### Locator Shape

```json
{
  "evidence_locator": {
    "store": "sqlite|lancedb",
    "path": "...",
    "collection": "...",
    "record_id": "...",
    "artifact_hash": "..."
  }
}
```

## V2-9：Testing and Rollout Strategy

### Test Slices

1. Schema-only unit tests
   - v1 rows cannot promotion
   - v2 rows require signed receipt
   - missing sandbox attestation blocks executable promotion
2. Runtime apply tests
   - current overlay remains PASS
   - V2 failure does not break A path
   - V2 pass still requires manual apply
3. Runner tests
   - mocked attestation is diagnostic only
   - network-disabled false blocks promotion
   - teardown fail quarantines runner
4. Evidence store tests
   - locator round-trip
   - delete+add atomic update
   - summary export only

### Commands

```bash
uv run pytest tests/ops/test_build_sf_final_runtime_apply.py
uv run pytest tests/learning/test_zero_trust_execution_security.py
uv run pytest tests/ops/test_zero_trust_v2_promotion.py
uv run scripts/ops/ci_gate.py
```

## Recommended Implementation Order

### Phase 1：Backlog + Contracts

Files:

- `scripts/ops/build_zero_trust_v2_curation_backlog.py`
- `tests/ops/test_build_zero_trust_v2_curation_backlog.py`
- `docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json`

Exit:

- 19 items in backlog
- all items `v2_promotion_eligible=false`
- `browserbase-fetch` has cross-capability warning

### Phase 2：Promotion Contract Evaluator

Files:

- `nexus/learning/zero_trust_v2_promotion.py`
- `tests/learning/test_zero_trust_v2_promotion.py`

Exit:

- v1 diagnostic rows cannot pass
- v2 rows missing receipt / sandbox / clean-slate cannot pass
- fully populated mock v2 row can reach `READY_FOR_MANUAL_APPLY`

### Phase 3：Runtime-Signed Receipt Mock

Files:

- `nexus/learning/zero_trust_v2_receipts.py`
- `tests/learning/test_zero_trust_v2_receipts.py`

Exit:

- deterministic signature input hash
- skill-supplied receipt rejected for promotion credit
- no signature secret in `runner_env`

### Phase 4：Sandbox Attestation Mock

Files:

- `nexus/learning/zero_trust_v2_sandbox.py`
- `tests/learning/test_zero_trust_v2_sandbox.py`

Exit:

- mocked attestation supports diagnostic tests
- executable promotion remains blocked unless attestation mode is approved
- teardown fail marks quarantine

### Phase 5：V2 Replay Matrix

Files:

- `scripts/ops/build_zero_trust_v2_replay_matrix.py`
- `tests/ops/test_build_zero_trust_v2_replay_matrix.py`

Exit:

- produces capability_only / candidate / negative_control / shadow rows
- all executable rows require sandbox attestation
- v1 evidence copied only as diagnostic context

### Phase 6：Manual Apply Gate

Files:

- `scripts/ops/build_zero_trust_v2_promotion_report.py`
- `tests/ops/test_build_zero_trust_v2_promotion_report.py`
- `scripts/ops/build_zero_trust_v2_runtime_apply.py`
- `tests/ops/test_build_zero_trust_v2_runtime_apply.py`

Exit:

- V2 promotion report separates `BLOCKED` from `READY_FOR_MANUAL_APPLY`
- V2 pass produces patch plan, not direct runtime mutation
- V2 failure keeps A path unchanged
- downgrade / revert policy included in artifact

## 目前實作狀態（2026-05-21）

已完成到可執行的 V2 control-plane baseline：

- Backlog：`docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json`
  - `candidate_count=19`
  - `requires_curation_count=19`
  - `v2_ready_count=0`
- Replay matrix：`docs/reports/NEXUS_ZERO_TRUST_V2_REPLAY_MATRIX_2026-05-21.json`
  - `row_count=76`
  - `arms_per_candidate=4`
  - `runtime_mutation_allowed=false`
  - `public_benchmark_allowed=false`
- Promotion report：`docs/reports/NEXUS_ZERO_TRUST_V2_PROMOTION_CANDIDATES_2026-05-21.json`
  - `candidate_arm_count=38`
  - `ready_for_manual_apply_count=0`
  - `blocked_count=38`
- Runtime apply plan：`docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_APPLY_PLAN_2026-05-21.json`
  - `patch_plan_count=0`
  - `runtime_update_allowed=false`
  - `automatic_apply_allowed=false`

注意：目前 V2 完成的是 control-plane schema、mock contract、reporting 與 fail-closed gate，不是完整物理 sandbox 上線。`mocked_non_promotion` attestation 只能用於診斷測試；正式 promotion 仍必須由 runner 產生 approved sandbox attestation、runtime-signed receipt、clean-slate baseline sandwich，且最後仍需 manual apply gate。

## Physical Sandbox Runner Slice（2026-05-21）

已新增最小物理 sandbox runner 切片：

- `nexus/learning/zero_trust_v2_physical_sandbox.py`
  - 建立 per-arm workspace / tmp。
  - 使用 child env allowlist。
  - 透過 macOS `sandbox-exec` profile 宣告 `deny network*`。
  - 產生 runner-owned `sandbox_attestation`、`artifact_hash`、HMAC signature。
  - teardown 後才寫入 `teardown_status`。
- `nexus/learning/zero_trust_v2_physical_runner.py`
  - 消耗 V2 replay rows。
  - 補 runtime-signed receipt、clean baseline sandwich、negative-control block accounting。
  - 預設 `promotion_credit_allowed=false`，所以 `/bin/echo` 或其他探針不能變成真實 skill promotion credit。
- `scripts/ops/build_zero_trust_v2_sandbox_probe.py`
  - 產生單次 sandbox attestation probe report。
- `scripts/ops/run_zero_trust_v2_physical_sandbox.py`
  - 從 replay matrix 取 row 進 physical sandbox wrapper。
  - 預設 probe-only；必須顯式 `--allow-promotion-credit` 才會把完整 row evidence 計為 V2 promotion credit。

目前實跑產物：

- `docs/reports/NEXUS_ZERO_TRUST_V2_SANDBOX_PROBE_2026-05-21.json`
  - `probe_status=PASS`
  - `promotion_eligible=true`
  - `sandbox_mode=macos_sandbox`
  - `runtime_mutation_allowed=false`
- `docs/reports/NEXUS_ZERO_TRUST_V2_PHYSICAL_SANDBOX_RUN_2026-05-21.json`
  - `executed_row_count=4`
  - `execution_status_counts={"BASELINE_ONLY": 1, "BLOCKED_BY_POLICY": 1, "PASS": 2}`
  - `probe_only=true`
  - `ready_for_manual_apply_count=0`
  - `runtime_mutation_allowed=false`

下一步統一方向：

1. 將 probe-only row runner 替換為真正 skill execution command builder。
2. 對每個 P0 candidate 跑 source review / xray scan / physical sandbox row。
3. 僅在 `promotion_credit_allowed=true` 且真實 skill execution receipt 完整時，寫入 V2 promotion evidence。
4. 由 V2 promotion report 產生 manual apply plan，再人工替換 V1 overlay。

## M1-M6 Execution Status（2026-05-21）

本輪已補齊 M1-M6 的可執行 control-plane/reporting path，但尚未完成任何 V2 default promotion。

新增產物：

- M1：`docs/reports/NEXUS_ZERO_TRUST_V2_SKILL_COMMAND_SPECS_2026-05-21.json`
  - P0 candidates：`5`
  - command ready：`1`
  - blocked：`4`
- M2/M3：`docs/reports/NEXUS_ZERO_TRUST_V2_PHYSICAL_SKILL_EVIDENCE_2026-05-21.json`
  - command ready：`1`
  - executed rows：`4`
  - materialization only：`true`
  - ready for manual apply：`0`
- M4：`docs/reports/NEXUS_ZERO_TRUST_V2_EVIDENCE_ACCUMULATION_2026-05-21.json`
  - candidate count：`1`
  - ready for manual apply：`0`
  - blocked：`1`
- M5：`docs/reports/NEXUS_ZERO_TRUST_V2_UNIFICATION_PLAN_2026-05-21.json`
  - patch plan count：`0`
  - V1 role：`runtime_overlay_primary_until_v2_ready`
- M6：`docs/reports/NEXUS_ZERO_TRUST_V2_34_CAPABILITY_ROLLOUT_STATUS_2026-05-21.json`
  - capability count：`34`
  - V2 default ready：`0`
  - V1 primary or existing：`34`
  - unification complete：`false`

解讀：

- M1-M6 的流程已可跑通。
- `SKILL.md` materialization 可以證明 source asset 可被隔離讀取與簽章，但不能證明 skill behavior。
- 因此本輪沒有任何 skill 取得 V2 promotion credit。
- 未來要真正統一 V1/V2，必須把 command spec 從 `SKILL.md` materialization 升級成 capability runner 的真實 skill behavior execution。

## M7-M12-3 Execution Status（2026-05-21）

已補齊 behavior-evidence 到 M12-3 final verdict 的 reporting path。

新增產物：

- M7/M8：`docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_EVIDENCE_2026-05-21.json`
  - candidates：`19`
  - P0：`5`
  - P1：`3`
  - P2：`11`
  - historical behavior pass：`0`
  - V2 behavior ready：`0`
- M9：`docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_PROMOTION_REPORT_2026-05-21.json`
  - candidates：`19`
  - ready for manual apply：`0`
  - blocked：`19`
- M10：`docs/reports/NEXUS_ZERO_TRUST_V2_MANUAL_APPLY_TRIAL_2026-05-21.json`
  - ready candidates：`0`
  - trial patch plan：`0`
- M11：`docs/reports/NEXUS_ZERO_TRUST_V2_P0_ROLLOUT_2026-05-21.json`
  - P0 candidates：`5`
  - P0 ready：`0`
  - P0 structured blocked：`5`
- M12-3：`docs/reports/NEXUS_ZERO_TRUST_V2_M12_34_CAPABILITY_FINAL_VERDICT_2026-05-21.json`
  - capabilities：`34`
  - V2 ready manual apply pending：`0`
  - structured blocked：`19`
  - no V2 candidate ready：`15`
  - M12-3 complete：`true`
  - V2 unification complete：`false`

解讀：

- M12-3 complete 的意思是 34 個 capability 都已有 V2 verdict。
- 這不代表 34 個 capability 已 V2 promoted。
- 目前所有候選都因缺少真 V2 behavior evidence 而 blocked。
- 下一步若要讓 V2 unification complete，必須讓 `capability_ab_runner` 在 physical sandbox 中產生 selected / injected / used / evidence / gate / outcome / trust_mismatch 的 V2 receipt。

## Stop Conditions

停止實作並回報：

- 任何變更會使 current runtime overlay smoke fail。
- 任何流程需要把 `NEXUS_SYSTEM_SALT` 寫入 repo 或 `runner_env`。
- 任何 skill-supplied receipt 被當成 promotion evidence。
- 任何 external reference candidate 被標記為 fully promoted without curation。
- 任何 V2 evidence store 需要 full corpus report read 才能決策。
- 任何 public benchmark flag 被打開。

## 最終完成定義

V2 完成不是「欄位存在」。

完成條件：

```text
current overlay remains usable
v1 evidence remains diagnostic only
19 applied replacements have curation backlog
at least one candidate can complete mocked V2 evidence path
promotion evaluator blocks incomplete V2 rows
manual apply artifact can be produced
no automatic runtime default mutation
public_benchmark_allowed remains false
```

## M13-M19 Execution Status（2026-05-21）

已補齊 fresh behavior runner 的 fail-closed 入口與 M13-M19 結算報告。

新增產物：

- M13：`docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json`
  - candidates：`19`
  - P0：`5`
  - P1：`3`
  - P2：`11`
  - ready for physical behavior run：`0`
  - blocked：`19`
  - promotion credit allowed：`false`
- M14-M19：`docs/reports/NEXUS_ZERO_TRUST_V2_M13_M19_COMPLETION_2026-05-21.json`
  - M13 adapter complete：`true`
  - M14 fresh behavior receipt path ready：`0`
  - M15 first candidate manual apply ready：`false`
  - M16 manual trial rollback gate ready：`false`
  - M17 P0 promoted：`0`
  - M17 P0 structured blocked：`5`
  - M18 P1/P2 promoted：`0`
  - M18 P1/P2 structured blocked：`14`
  - M19 V1 promotion shutdown boundary complete：`true`
  - V2 unification complete：`false`

解讀：

- `capability_ab_runner` adapter 已可組裝 fresh behavior run 的 command/env。
- adapter 會要求 `NEXUS_VALUE_HIDDEN_VERIFIER=1`、`NEXUS_BENCH_SKILL_MOUNTS=1`、`NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS=1`、`--task-id-filter`、`--evidence-bundle`、`--neutralize-history`、`--disable-learning-loop`。
- 目前 19 個候選都缺 fresh `task_ref`，因此全部 fail-closed。
- M19 的意思是 V1 可繼續作為 runtime fallback，但 V1/historical evidence 仍不能折算 V2 promotion credit。

後續路線圖：

- M20：為 P0 候選補 fresh task manifest/task id，禁止用 historical evidence ref 取代。
- M21：在 physical sandbox 跑 P0 fresh behavior receipt，產出 signed V2 receipt。
- M22：累積每個候選至少 3 次 clean V2 receipt，`trust_mismatch=0`。
- M23：開啟 manual apply trial artifact，仍禁止 automatic runtime mutation。
- M24：先替換 1 個低風險 capability，跑 rollback/smoke。
- M25：P0 批次推進；P1/P2 仍維持 structured blocked。
- M26：P1/P2 重複 M20-M25。
- M27：所有 34 capability V2 ready 後，才關閉 V1 promotion path。

## M20-M27 Execution Status（2026-05-21）

已補齊 fresh task_ref 到 V1 shutdown boundary 的 reporting path。

新增產物：

- M20：`docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_REFS_2026-05-21.json`
  - candidates：`19`
  - fresh task refs：`19`
  - P0：`5`
  - P1：`3`
  - P2：`11`
  - promotion credit allowed：`false`
- M20 manifest：`docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_MANIFEST_2026-05-21.json`
  - top-level public/preflight fields：`version`、`frozen`、`benchmark_id`、`description`、`tasks`
  - task count：`19`
- M21 matrix：`docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json`
  - ready for physical behavior run：`19`
  - blocked：`0`
  - promotion credit allowed：`false`
- M20-M27 verdict：`docs/reports/NEXUS_ZERO_TRUST_V2_M20_M27_COMPLETION_2026-05-21.json`
  - physical behavior executed：`0`
  - clean V2 receipts：`0`
  - manual apply trial ready：`0`
  - P0 promoted：`0`
  - P0 structured blocked：`5`
  - P1/P2 promoted：`0`
  - P1/P2 structured blocked：`14`
  - 34 capability V2 ready：`0`
  - V1 promotion path closed：`false`
  - V2 unification complete：`false`

解讀：

- M20 已完成 fresh task_ref 補齊。
- M21 已完成「可執行 command/env 產生」，但尚未實際跑 physical behavior execution。
- M22-M26 因沒有 signed clean V2 receipt，所以全部維持 structured blocked。
- M27 完成的是 shutdown boundary，不是 shutdown execution；V1 path 只有在 34 capability 都 V2 ready 後才可關閉。

下一步路線圖：

- M28：選 P0 中 1 個低風險 candidate 執行 physical behavior preflight。
- M29：執行同 candidate 的 3 次 signed V2 behavior run。
- M30：把 signed receipt 匯入 accumulation，驗證 `v2_evidence_count >= 3` 且 `trust_mismatch=0`。
- M31：產生單一 candidate manual apply trial。
- M32：manual ack 後做 1 capability canary apply + rollback smoke。
- M33：P0 全批次重複 M28-M32。
- M34：P1/P2 全批次重複 M28-M32。
- M35：34 capability 全部 V2 ready 後，產生 V1 path closure apply plan。

## M28-M35 Execution Status（2026-05-21）

已補齊 physical behavior execution plan、3-run receipt batch、canary rollback gate 與 V1 closure gate。

新增產物：

- M28-M35：`docs/reports/NEXUS_ZERO_TRUST_V2_M28_M35_EXECUTION_PLAN_2026-05-21.json`
  - selected canary：`1`
  - preflight ready：`true`
  - signed behavior run plan：`3`
  - signed behavior executed：`0`
  - existing receipt bundles：`0`
  - clean V2 receipts：`0`
  - manual apply trial ready：`0`
  - canary apply ready：`false`
  - P0 ready for execution：`5`
  - P1/P2 ready for execution：`14`
  - V1 path closure plan ready：`false`
  - V2 unification complete：`false`

解讀：

- M28 完成的是 preflight hook command 產生，不是執行。
- M29 完成的是 3-run batch plan，不是 signed receipt 本身。
- M30-M35 因尚未有 signed V2 behavior receipts，全部維持 blocked。
- 下一步要真正跨過 M30，必須執行 M28 preflight，再執行 M29 三次 physical behavior run，讓 receipt import gate 看到 3 個 clean evidence bundle。

下一步路線圖：

- M36：實際執行 M28 preflight command，檢查 runner/task/skill mount wiring。
- M37：修正 preflight blocker，直到 preflight PASS。
- M38：執行 M29 run-01/run-02/run-03，收集 signed V2 behavior receipts。
- M39：匯入 receipts，要求 3/3 clean、`trust_mismatch=0`、negative control blocked。
- M40：對單一 candidate 產生 manual apply trial。
- M41：manual ack 後做 canary apply + post-apply smoke + rollback proof。
- M42：P0 批次 rollout。
- M43：P1/P2 批次 rollout。
- M44：34 capability 全 V2 ready 後，關閉 V1 promotion path。

## M36-M44 Completion Status（2026-05-21）

已實際執行 M28 preflight，並把 M36-M44 的狀態收斂成 completion gate。這一段完成的是 runner wiring repair 與 closure boundary，不是 skill promotion。

新增產物：

- M36-M44：`docs/reports/NEXUS_ZERO_TRUST_V2_M36_M44_COMPLETION_2026-05-21.json`
  - M36 preflight status：`PASS`
  - M36 preflight failures：`0`
  - M36 preflight warnings：`2`
  - M37 blocker repair complete：`true`
  - M38 signed behavior run plan：`3`
  - M38 signed behavior executed：`0`
  - M39 clean V2 receipts：`0`
  - M40 manual apply trial ready：`0`
  - M41 canary apply ready：`false`
  - M42 P0 ready for execution：`5`
  - M42 P0 promoted：`0`
  - M43 P1/P2 ready for execution：`14`
  - M43 P1/P2 promoted：`0`
  - M44 V2 ready capability：`0/34`
  - V1 path closure ready：`false`

M37 修正內容：

- behavior adapter 使用 `--gemini-model`，不再產生 runner 不支援的 `--model`。
- fresh task manifest 的 task row 不再寫入 private `zero_trust_v2` 欄位。
- `policy_capability_gate` 等 V2 capability 會映射成 runner core expected capability，例如 `mempalace_gate`，避免 preflight unknown capability fail。

目前邊界：

- M36 PASS 只代表 task/runner/skill mount wiring 可被 runner 接受。
- M38-M44 仍 blocked，因為尚未執行 3 次 signed V2 behavior run。
- 沒有 runtime mutation、automatic apply、public benchmark claim 或 promotion credit。
- V1 promotion path 仍必須保持開啟，直到 34 capability 都具備 V2 clean signed behavior receipt 並通過 rollout gate。

下一步路線圖：

- M45：執行 `run-01/run-02/run-03` physical behavior run，產生 3 份 evidence bundle。
- M46：匯入 signed receipts，要求 `3/3 clean`、`trust_mismatch=0`、negative control blocked。
- M47：對 `policy_capability_gate / browse` 產生 manual apply trial。
- M48：manual ack 後做單 capability canary apply、post-apply smoke 與 rollback proof。
- M49：把 P0 的 5 個 candidate 全部跑完 M45-M48。
- M50：把 P1/P2 的 14 個 candidate 全部跑完 M45-M48。
- M51：彙總 34 capability V2 ready 差距，補齊未覆蓋 capability。
- M52：只有在 34/34 V2 ready 後，才產生 V1 promotion path closure apply plan。

## M45-M52 Completion Status（2026-05-22）

已建立 behavior run hook，並實際嘗試 `policy_capability_gate / browse` 的 M45 run-01。結果是 runner 完成，但 behavior evidence 不乾淨，因此 M46-M52 正確 fail-closed。

新增產物：

- Behavior run hook：`docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUN_HOOK_2026-05-22.json`
  - run count：`1`
  - ready count：`1`
  - executed count：`0`
  - runtime mutation allowed：`false`
  - promotion credit allowed：`false`
- M45-M52：`docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json`
  - M45 behavior run plan：`3`
  - M45 behavior run executed：`1`
  - M45 clean V2 receipt：`0`
  - M45 status：`BLOCKED_AFTER_FIRST_RUN`
  - M46 receipt import ready：`false`
  - M47 manual apply trial ready：`false`
  - M48 canary apply ready：`false`
  - M49 P0 ready for execution：`5`
  - M49 P0 promoted：`0`
  - M50 P1/P2 ready for execution：`14`
  - M50 P1/P2 promoted：`0`
  - M51 V2 ready capability：`0/34`
  - M52 V1 closure ready：`false`

M45 run-01 阻擋原因：

- `receipt_data_contract_violation`
- `missing_required_capability_receipts`
- `missing_runtime_signed_v2_receipt`
- `no_eligible_behavior_row`
- `semantic_not_verified`
- `token_telemetry_incomplete`

解讀：

- M45 已從純計劃進到一次真實 canary behavior run。
- run-01 不能折算為 V2 promotion evidence，因為它缺少 runtime-signed V2 receipt 與 expected capability receipt。
- run-02/run-03 暫停是正確選擇；在 receipt bridge 修好前繼續跑只會產生更多不可匯入 evidence。
- M46-M52 均保持 blocked，沒有 runtime mutation、automatic apply、public benchmark claim 或 promotion credit。

到完成 V2 的後續 Milestone 任務卡：

- M53：實作 `expected_capability_receipt_bridge`，讓 `mempalace_gate` 等 expected capability 的 invoked/evidence/gate 狀態能變成 public-safe receipt，而不是只出現在內部 telemetry。
- M54：實作 `runtime_signed_behavior_receipt_export`，把 V2 runtime observer 簽章寫入 behavior evidence bundle，並用 `verify_runtime_signed_receipt` 匯入。
- M55：修正 M45 canary task 的 delivery/semantic verification，要求 `eligible_behavior_rows >= 1` 且 `semantic_completed=true`。
- M56：重新執行 canary `run-01/run-02/run-03`，要求 `3/3 clean V2 receipts`。
- M57：M46 receipt import PASS 後產生 manual apply trial packet，仍不直接 mutation。
- M58：manual ack 後做 canary dry-run apply、post-apply smoke、rollback proof。
- M59：canary apply PASS 後跑 P0 5 個 candidate 的同款三連 run 與 receipt import。
- M60：P0 全 PASS 後跑 P1/P2 14 個 candidate。
- M61：補齊非本次 19 candidate 覆蓋不到的 capability，直到 `34/34` 都有 V2 ready path。
- M62：產生 V1 closure decision，要求 `34/34`、manual records complete、rollback records complete、public benchmark gate 仍獨立。
- M63：人工批准後才切 V2 default overlay，保留 V1 rollback path。
- M64：post-unification smoke、rollback drill、public claim gate 分離審核。

## Unified Mainline Closeout（2026-05-22）

已把 M53-M64 V2 統一主線落成 fail-closed closeout artifact。結果不是 V2 runtime 統一，而是確認目前不能安全統一。

新增產物：

- Unified mainline：`docs/reports/NEXUS_ZERO_TRUST_V2_UNIFIED_MAINLINE_2026-05-22.json`
  - milestone count：`12`
  - milestone pass：`0`
  - milestone blocked：`12`
  - clean V2 receipt：`0`
  - V2 ready capability：`0/34`
  - V2 unification complete：`false`
  - runtime mutation allowed：`false`
  - promotion credit allowed：`false`

目前 root blockers：

- `missing_required_capability_receipts`
- `missing_runtime_signed_v2_receipt`
- `no_eligible_behavior_row`
- `receipt_data_contract_violation`
- `semantic_not_verified`
- `token_telemetry_incomplete`

M53-M64 狀態：

- M53 `expected_capability_receipt_bridge`：blocked，`mempalace_gate` public-safe receipt 不成立。
- M54 `runtime_signed_behavior_receipt_export`：blocked，behavior bundle 尚無 runtime-signed V2 receipt。
- M55 `canary_semantic_delivery_repair`：blocked，沒有 eligible behavior row，semantic 未驗證。
- M56 `canary_three_clean_receipts`：blocked，`clean_v2_receipt_count=0/3`。
- M57-M58 manual apply / canary dry-run：blocked，因 canary 不乾淨。
- M59-M60 P0 / P1/P2 rollout：blocked，因 canary 不乾淨且 P0 未完成。
- M61-M64 34 capability coverage / V1 closure / V2 default apply / post-unification：blocked，因 `v2_ready_capability_count=0/34`。

下一個真修復順序：

1. 修 `mempalace_gate` receipt gate：只允許從真正 `gate_passed=true` 的 runtime receipt 轉成 public-safe receipt，不能從 selected/evidence-only 偽造。
2. 修 runtime observer：把 V2 HMAC receipt export 到 behavior evidence bundle，並由 importer 驗簽。
3. 修 canary task delivery：讓 `compute_backoff` 類 task 產生 patch、通過 hidden verifier、`semantic_completed=true`。
4. 重跑 canary 三連，達到 `3/3 clean` 後才回到 manual apply。
