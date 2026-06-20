# Benchmark Claim Policy v1.0

**建立日期**: 2026-06-16
**適用範圍**: 所有 Nexus benchmark 結果的公開主張與內部使用

---

## 1. Claim Tiers

### Tier 1: Public Claim（可公開主張）

**條件**（全部滿足）：
- `simulated = false`
- `claim_eligible = true`
- `model_calls >= 1`（有真實模型呼叫）
- `receipt_path` 非空（有持久化的 receipt 證據）
- `visible_passed = true` AND `hidden_passed = true`
- 執行時間 > 1 秒（排除 deterministic rescue 的 0.8s 任務）

**可主張的內容**：
- Solve rate（按 project、difficulty、category 拆解）
- Latency distribution（p50、p95）
- Token usage（prompt + completion）
- Model call count

### Tier 2: Internal Observation（內部觀測）

**條件**：
- `simulated = false`
- `claim_eligible = true`
- 但 `model_calls = 0`（deterministic rescue 路徑）

**可使用的內容**：
- 確定性路徑的覆蓋率
- Pipeline 基礎設施的可靠性指標
- **不可**用於外部能力宣稱

### Tier 3: Shadow / Simulation（影子 / 模擬）

**條件**：
- `simulated = true`，或
- `claim_eligible = false`

**可使用的內容**：
- 內部開發調試
- Pipeline 逻辑驗證
- **不可**用於任何形式的公開主張或 benchmark 報表

---

## 2. 不可引用的基準資料

以下資料因模擬性質或指標缺陷，**不可作為真實能力或治理品質的證據**：

| 資料來源 | 問題 | 不可引用原因 |
|---------|------|-------------|
| Token AB 180 runs (`runs_raw.jsonl`) | 所有 timestamp 在 1ms 內 | 模擬資料，非真實執行 |
| Differential Eval 300 tasks | `simulate_task()` 硬編碼規則 | 模擬資料，非真實執行 |
| Observation Cycle 01/02/03 | `MagicMock` + `run_simulation()` | 模擬資料，非真實執行 |
| Observation Cycle public_claim_precision | `public_claim_passed` 硬編碼 True | 治理指標永遠 100%，無實際意義 |
| nexus-value-* tasks (model_calls=0) | `nexus_deterministic_pre_model_rescue` | 確定性路徑，非模型能力 |

---

## 3. 公開主張格式

任何公開 benchmark 報表必須包含：

```markdown
## Benchmark Methodology

- **Dataset**: swebench_real_eval_manifest_v1.jsonl ({N} tasks)
- **Model**: {model_name} ({model_size})
- **Execution**: Real pipeline execution (not simulated)
- **Receipts**: All results backed by local_heal receipts
- **Claim tier**: Tier 1 (public claim eligible)

## Results

| Metric | Value |
|--------|-------|
| Solve rate | {solved}/{total} ({rate}%) |
| Solve rate (model-involved) | {model_solved}/{model_total} ({rate}%) |
| Median latency | {p50}s |
| p95 latency | {p95}s |
| Avg tokens per task | {tokens} |

## Per-Project Breakdown

| Project | Solved | Total | Rate |
|---------|--------|-------|------|
| ... | ... | ... | ... |
```

---

## 4. 反向驗證清單

在發佈任何 benchmark 報表前，必須確認：

- [ ] 所有引用的結果都來自 `claim_eligible = true` 的 receipt
- [ ] 沒有引用 `simulated = true` 的結果
- [ ] Solve rate 的分母是 deduplicated 的任務數
- [ ] 每個 solved task 都有對應的 receipt 路徑
- [ ] 報表中明確標註了 claim tier
- [ ] 沒有使用 `public_claim_passed` 硬編碼的治理指標

---

## 5. Receipt 寫入要求

每次 local_heal pipeline 執行後，必須寫入符合 `local_heal_receipt_v1.schema.json` 的 receipt：

1. **simulated** 欄位：如果 pipeline 走了 deterministic rescue 路徑且沒有呼叫模型，設為 `false`（因為這是真實的 pipeline 執行，只是沒有用到模型）。如果結果來自 `simulate_task()` 或 `MagicMock`，設為 `true`。

2. **claim_eligible** 欄位：只有同時滿足以下條件才設為 `true`：
   - `simulated = false`
   - 有完整的 phase 執行記錄
   - 有 persistent receipt 檔案

3. **failure_reason** 欄位：使用結構化失敗碼（見 `local_heal/errors.py` 的 `PatchErrorKind`）。

4. **evidence_refs** 欄位：列出所有相關的證據檔案路徑。
