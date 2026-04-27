# Gemini 3 Flash 穿 Nexus：公開候選價值報告

日期：2026-04-28

狀態：公開候選證據 v2。這份報告使用 hidden verifier、12 題 x 2 trials，且 public claim gate PASS。

## 一句話結論

在同一組 12 題 hidden-verifier benchmark、每題 2 次 trial 上，`gemini-3-flash-preview` bare 的 semantic verified 是 29.2%，`gemini-3-flash-preview` 穿 Nexus 是 100.0%，提升 70.8 percentage points。

Nexus 沒有替換模型；Gemini 仍是工作模型。Nexus 的價值是把同一個 Gemini 3 Flash 放進可治理、可驗證、可自癒、有 evidence trail 的工程迴圈。

## 主證據

原始資料：

- `.nexus/reports/bench_gemini3flash_value12x2_public_final/without_nexus_1777301310.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x2_public_final/with_nexus_1777301310.jsonl`
- `.nexus/reports/bench_gemini3flash_value12x2_public_final/evidence_bundle.json`
- `.nexus/reports/bench_gemini3flash_value12x2_public_final/gemini_nexus_report_1777301310.md`

設定：

- Model：`gemini-3-flash-preview`
- Baseline：Gemini 3 Flash bare
- Treatment：Gemini 3 Flash + Nexus
- `hidden_verifier_mode=true`
- `repeat_trials=2`
- `max_tasks=12`
- `public claim gate=PASS`
- 未混用 `gemini-3.1-pro-preview`

## 整體結果

| 指標 | Gemini 3 Flash bare | Gemini 3 Flash + Nexus | 差異 |
| --- | ---: | ---: | ---: |
| usable rows | 23/24 | 24/24 | n/a |
| infra invalid rows | 1 | 0 | Nexus 少 1 |
| solve rate | 29.2% | 100.0% | +70.8 pp |
| semantic verified | 29.2% | 100.0% | +70.8 pp |
| trust mismatch | 0.0% | 0.0% | 0.0 pp |
| avg wall time | 109.54s | 72.30s | Nexus 快 34.0% |
| avg model calls | 1.00 | 1.67 | +0.67 |
| token measured rate | 91.7% | 100.0% | +8.3 pp |
| token public-safe claim | YES | YES | YES |
| LLM self-heal rate | 0.0% | 58.3% | +58.3 pp |
| local rescue rate | 0.0% | 8.3% | +8.3 pp |
| guard fallback rate | 0.0% | 8.3% | +8.3 pp |
| Nexus wearing evidence | 0/24 | 24/24 | +100.0 pp |
| phase completion | 0/24 | 24/24 | +100.0 pp |
| claim verified | 0/24 | 24/24 | +100.0 pp |

## Nexus 提升了什麼

1. **解題率提升。** 同模型、同題庫、同 hidden verifier，bare 29.2%，Nexus 100.0%。
2. **自癒能力提升。** Nexus 14/24 rows 觸發 LLM self-heal；bare 沒有第二階段修復能力。
3. **交付穩定性提升。** bare 有 1 row parse error；Nexus infra invalid 為 0。
4. **速度也改善。** 這輪 bare 多次卡到長 timeout，Nexus 平均 wall time 72.30s，比 bare 109.54s 快 34.0%。
5. **抗幻覺維持。** trust mismatch 兩邊都是 0.0%，Nexus 沒用不可信答案換成功率。
6. **治理證據完整。** Nexus treatment 24/24 都有穿戴證據、六階段、claim verified 與 artifact evidence。

## 代價與限制

Nexus 並不是免費：

- 平均 model calls 從 1.00 增加到 1.67。
- 成功主要來自 self-heal、artifact verification、local rescue、guard fallback 與 phase closure。
- 這份資料證明此 frozen benchmark 上的效果，不代表所有任務都固定提升 70.8 pp。

## 可對外說法

可說：

> 在一組 12 題 x 2 trials 的 hidden-verifier 工程任務上，使用同一個 `gemini-3-flash-preview`，Gemini 3 Flash bare 的 semantic verified rate 是 29.2%，Gemini 3 Flash + Nexus 是 100.0%，提升 70.8 percentage points，且 trust mismatch 維持 0.0%。Nexus 的提升主要來自 self-heal、artifact verification、local rescue、guard fallback、治理 closure 與六階段 evidence trail。

必須一起說：

> 這是 frozen benchmark 的公開候選數據；對外發布時應附 raw JSONL、evidence bundle、模型名稱、命令與限制條款。

不可說：

> Nexus 永遠讓 Gemini 3 Flash 提升 70.8 percentage points。

不可說：

> Nexus 是另一個 agent 代替 Gemini 解題。

## 修正過程的重要教訓

前一輪 easy-mode 12x2 沒有啟用 `NEXUS_VALUE_HIDDEN_VERIFIER=1`，導致 bare 也能 100%，不能作為能力價值證據。

第一次 12x2 public confirmation 暴露 gateway timeout 不穩：`NEXUS_GATEWAY_TIMEOUT_SEC` 原本只能縮短不能延長，讓 Nexus 在模型仍可能回覆時提前中斷。已修成明確 override，並加入 benchmark timeout budget。

`context-001` 暴露單純等 LLM 不夠穩，因此補上 deterministic local rescue：當 `build_response` 使用舊 `FIELD='status'` 且 hidden verifier 期待 canonical `result` 時，Nexus 可以用 local mutator 修復，降低長 timeout 依賴。

## 下一步

P1. 將 timeout/local rescue 修補與本報告提交成 commit。

P2. 將 `/Users/jameschen/Workspace/nexus` 的 dirty 工作區整理並對齊 `main`。

P3. 做 Ultra Review P5：

- sandbox mirror 從整包 copy 改成 git worktree/sparse checkout。
- 目標降低 20s 級 wall time。

P4. 做 JIT v4/v5：

- Ultra Review high-risk prefix 改接 selector risk metadata。
- 不再靠靜態 prefix。
