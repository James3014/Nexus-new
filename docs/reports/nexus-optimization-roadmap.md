# Nexus 本地模型優化：統一路線圖

**版本**：v4（更新版）
**生成時間**：2026-06-15
**真實基準**：60-90s/task（2026-06-15 最新數據）
**目標**：60-90s → ≤50s（追平雲端 Gemini bare ~49s）
**基準 Commit**：`fad8f32e`
**最新 Commit**：`96e00ce4`

---

## 一、現況

### 真實戰績

| 任務 | 耗時 | 修復檔案 |
|------|------|----------|
| bug-1781469615 | 76.53s | coordinator.py |
| bug-1781454307 | 56.36s | coordinator.py |

**優化關鍵**：
- Commit `62f798cf`：`num_predict` 限制為 512，防止本地推理「邏輯溢出」
- S2T v2：低風險決策分流，減輕重型推理鏈負擔

**與雲端對比**：Gemini bare 歷史基準 ~49s，差距已縮小至 2x 以內。

### 已完成的基礎建設

| Phase | 標題 | 狀態 | 關鍵改動 |
|-------|------|------|----------|
| Phase 1 | 驗證已實作修復 | ✅ DONE | Ollama keep_alive=30m, timeout=120s |
| Phase 1.5 | Runner 與 Governance | ⚠️ PARTIAL | `--llm-baseline` override + mempalace bypass 已完成，uv run fallback 遺留 |
| Phase 6 | Persistent Worker | ✅ DONE | `--persistent-worker` flag, JSON protocol, gap dashboard |

### 已放棄或延後的 Phase

| Phase | 標題 | 狀態 | 原因 |
|-------|------|------|------|
| Phase 2 | Ollama MLX Backend | ❌ 放棄 | inference 只佔 ~15-20s，patch generation 佔 ~20-30s，ROI 不如 prompt 優化 |
| Phase 3 | Quantization | ❌ 驗證失敗 | Q3 量化在 16GB Mac 上仍 >180s，Ollama GGUF 後端已成瓶頸 |
| Phase 4 | MLX Native | ❌ 延後 | 同 Phase 2 理由 |
| Phase 5 | Speculative Decoding | ❌ 取消 | Apple Silicon 上不保證加速，acceptance rate <40-50% 反而變慢 |

---

## 二、瓶頸分析（基於 60s 基準）

### Repair Pipeline 結構

```
Phase 1 (Reproduction) → Phase 2 (Planning) → Phase 3 (Localization) → Phase 4 (Patch Synthesis) → Phase 5 (Verification)
```

### 時間分佈

| 瓶頸 | 代碼位置 | 佔比（估） | 嚴重度 |
|------|----------|-----------|--------|
| **Patch generation** | `patch_synthesis.py` | ~20-30s | 🔴 High — 最大單項瓶頸 |
| **Model inference** | `llm_client.py` → Ollama | ~15-20s (warm) | 🟡 Medium |
| **Localization** | `granular_localizer.py` | ~10-15s | 🟡 Medium — BM25 + AST 已夠快 |
| **Verification** | `verification.py` | ~5-10s | 🟢 Low |
| **Retry overhead** | `repair_loop_service.py` | ~0-30s (if retry) | 🟡 Medium |

**關鍵結論**：瓶頸不是「找不到 bug」，而是「生成 patch 的 LLM call 太慢」。

---

## 三、統一方向：從 60s 到 ≤50s

### 核心策略：減少 LLM Call 次數 + Token 消耗

```
現狀: [Planning ~5s] + [Localization ~10s] + [Patch Generation ~25s] + [Verification ~8s] = ~48s (best case)
                                                            ↓
目標: [FAST Planning ~1s] + [FAST Localization ~3s] + [精簡 Patch ~15s] + [Verification ~8s] = ~27s
```

### P0：減少 LLM Call 次數（最大 ROI）

| 動作 | 代碼改動 | 預期收益 | 風險 |
|------|----------|----------|------|
| **FAST_MODE 擴展到 Localization** | `planning.py:70-76` — 用 deterministic AST analysis 取代 BM25 + LLM | planning + localization 合併省 ~5-10s | 低 |
| **Retry 時注入 failure reason** | `repair_loop_service.py:38-70` — 在下一轮 user_prompt 加 "Previous attempt failed: {failure_reason}" | retry 次數 -30% | 極低 |
| **First-pass patch success rate** | `patch_synthesis.py` — 改善 prompt 質量，讓 model 第一次就產出正確 patch | 減少 retry → 省 20-30s/次 | 低 |

### P1：減少 Token 消耗（縮短 inference time）

| 動作 | 代碼改動 | 預期收益 | 風險 |
|------|----------|----------|------|
| **Dynamic context window** | `surgical_context.py:9-10` — 根據 file criticality 動態調整 window size | token -20%，inference time -3-5s | 低 |
| **Patch prompt 精簡** | `prompt_builder.py` — 減少 system prompt 冗餘，保留核心指令 | token -15%，inference time -2-3s | 低 |
| **Interleaved generation** | `patch_synthesis.py` — 讓 LLM 同時 reasoning + patch | 減少一次 LLM call → 省 ~15-20s | 中 |

### P2：提升 Patch Quality（減少 retry）

| 動作 | 代碼改動 | 預期收益 | 風險 |
|------|----------|----------|------|
| **Runtime evidence for localization** | 新增 `runtime_evidence.py` — 用 `sys.settrace` 捕捉 call sequence | hit@1 +10%，first-pass success +15% | 低 |
| **Failure Memory Bank** | `repair_loop_service.py` + `skill_outcomes.py` | 重複錯誤率 -40% | 中 |
| **AST call graph** | `granular_localizer.py` — 加 call graph centrality scoring | localization 準確度 +10% | 低 |

---

## 四、論文依據

### 解法 1：Dynamic Analysis（DAIRA, 2603.22048）
- **做法**：用 lightweight tracing tools 捕捉 runtime evidence（call stacks, variable states）
- **效果**：SWE-bench Verified 79.4% resolution rate，token -25%，成本 -10%
- **Nexus 對應**：`nexus_cli.py` 已有 `faulthandler.enable()`，可擴展為 fault localization signal

### 解法 2：AST-aware RAG（BLAgent, 2605.17965）
- **做法**：path-augmented AST-based chunking + dual-perspective query transformation
- **效果**：SWE-bench Lite Top-1 78%（open-source），比最強 baseline 便宜 18x
- **Nexus 對應**：`granular_localizer.py` 已有 AST parsing，可加 call graph + semantic reranking

### 解法 3：Data-flow Graph（ARISE, 2605.03117）
- **做法**：Statement-level nodes + intra-procedural definition-use edges
- **效果**：Function Recall@1 +17pp，Line Recall@1 +15pp，Pass@1 +4.7pp
- **Nexus 對應**：`granular_localizer.py` 的 `localize()` 已有 AST walk，可加 data-flow edges

### 解法 4：Action-Criticality Scoring（CICL, 2606.08151）
- **做法**：Action shift scoring + outcome uplift + necessity + negative-transfer risk
- **效果**：SWE-bench Verified hit@1 從 0.58 → 0.78
- **Nexus 對應**：`surgical_context.py` 用固定 window=150 lines，可改為動態 criticality-based

### 解法 5：Failure Memory Bank（FailureMem, 2603.17826）
- **做法**：Failure Memory Bank — 將 past repair attempts 轉換為 reusable guidance
- **效果**：SWE-bench Multimodal resolved rate +3.7%
- **Nexus 對應**：`repair_loop_service.py` 的 retry loop 完全不注入失敗原因

### 解法 6：Interleaved Generation（InterleaveThinker, 2606.13679）
- **做法**：Interleaving thinking and code generation in a single pass
- **效果**：減少 repair 迭代次數
- **Nexus 對應**：`patch_synthesis.py` 是 sequential flow，可改為 interleaved

---

## 五、執行計畫

### 本週（~3 天）

| Day | 動作 | 代碼改動 | 驗證方式 |
|-----|------|----------|----------|
| D1 | **FAST_MODE 擴展到 Localization** | `planning.py` — 加 `NEXUS_FAST_MODE` flag 讓 localization 也走 deterministic path | 用 bug-1781454307 測試，確認 planning + localization 合併時間 <5s |
| D2 | **Retry 注入 failure reason** | `repair_loop_service.py:38-70` — 在 user_prompt 加 failure context | 故意製造一次失敗的 patch，確認 retry 時 prompt 包含 failure reason |
| D3 | **Dynamic context window** | `surgical_context.py:9-10` — 根據 file criticality 動態調整 | 比較 token 消耗：舊 window=150 vs 新 dynamic |

### 下週（~5 天）

| Day | 動作 | 代碼改動 | 驗證方式 |
|-----|------|----------|----------|
| D4-5 | **Patch prompt 精簡** | `prompt_builder.py` — 減少 system prompt 冗餘 | 比較 token 消耗和 patch quality |
| D6-7 | **Runtime evidence capture** | 新增 `runtime_evidence.py` — 用 `sys.settrace` 捕捉 call sequence | 注入 localization，確認 hit@1 提升 |
| D8 | **Failure Memory Bank** | `repair_loop_service.py` + `skill_outcomes.py` | 製造重複失敗場景，確認 failure memory 被注入 |

---

## 六、臨時代碼清理

| 位置 | 內容 | 建議 |
|------|------|------|
| `s2t_strict.py:254` | `print(f"... [S2T Advisor Ollama Error]: ...")` | 移除或改為 logging |
| `s2t_strict.py:253-255` | `import traceback; traceback.print_exc()` | 移除 debug-level output |
| `nexus_cli.py:9-10` | `import faulthandler; faulthandler.enable()` | 可保留，對生產無害 |

---

## 七、最激進的觀點

1. **最大的瓶頸是 patch generation 的 LLM call，不是 localization**。在 60-90s 基準下，localization 已經被 BM25 + AST 優化到 ~10-15s。真正的時間花在 `patch_synthesis.py` 的 LLM call（~20-30s）和可能的 retry（~20-30s）。

2. **`num_predict=512` 是關鍵優化**。Commit `62f798cf` 證明了限制 output token 比增加 input context 更有效。「更短的 patch prompt」比「更豐富的 context」更有價值。

3. **FAST_MODE 是被低估的加速器**。`planning.py:70-76` 的 `NEXUS_FAST_MODE` 用 deterministic symbol extraction 跳過 LLM planning。擴展到 localization 可以再省 5-10s。

4. **Interleaved generation 是從 60s 到 40s 的關鍵**。讓 LLM 在同一個 pass 中完成 reasoning + patch generation，可以省掉一次 LLM call 的 overhead（~15-20s）。

5. **雲端 vs 本地的差距不在 inference speed，而在 prompt engineering**。Gemini bare ~49s vs Nexus ~60-90s 的差距，主要來自 Nexus 的 prompt 更長和可能的 retry。

---

## 八、執行結果（2026-06-15 更新）

### 核心指標對比

| 指標 | 改善前 | 改善後 | 變化 |
|:---|:---:|:---:|:---:|
| **Execution time** | 141s | 65s | **-54%** |
| **Total time** | 164s | 83s | **-49%** |
| **Model tokens** | 0 (未追蹤) | 6,275 | 可觀測 |
| **Gate tests** | 29/31 | 31/31 | +2 |
| **Prompt tokens** | ~500 | ~189 | **-62%** |

### 時間分佈對比

```
改善前 (141s execution):
  P: 10s | D: 6s | R: 86s (model 0s + overhead 86s) | A: 1s

改善後 (65s execution):
  P: 9s | D: 5s | R: 45s (model 12s + overhead 33s) | A: 1s
```

### 各改動實際效果

| 改動 | 執行時間影響 | 說明 |
|:---|:---:|:---|
| **num_predict 512** | 141s → 64s | **唯一真正加速**。Model 從 1718 tokens → 512 tokens |
| Token tracking fix | 0 → 6275 tokens | 可觀測性，不影響速度 |
| Lazy imports | 17s → 17s | 第二次執行時已 cached，無感 |
| D1 FAST_MODE routing | — | 正確性改善，不影響速度 |
| D2 Retry injection | — | 減少 retry 次數，不影響單次速度 |
| D3 Dynamic window | — | Token 優化，不影響速度 |
| D4 Prompt 精簡 | — | Token 優化，不影響速度 |
| D8 Failure Memory | — | 正確性改善，不影響速度 |
| AST call graph | — | Localization 準確度，不影響速度 |
| Interleaved generation | — | 減少 LLM call 次數，不影響單次速度 |

### Commit 清單

| Commit | 內容 |
|:---|:---|
| `c8806a71` | R phase model invocation 修復 |
| `06a8d918` | Lazy imports 優化 |
| `62f798cf` | num_predict 限制 |
| `11e6ae67` | Token tracking 修復 |
| `ffcb597b` | D1: FAST_MODE 動態路由 |
| `e7982921` | D2: Retry failure injection |
| `7af62eb9` | D3: Dynamic context window |
| `36c2961e` | D4: Patch prompt 精簡 |
| `4924c3ee` | D5: Benchmark results |
| `2be15a79` | D8: Failure Memory Bank |
| `1932d40d` | 臨時代碼清理 |
| `d2341d3a` | AST call graph scoring |
| `96e00ce4` | Interleaved generation |

### 根本問題分析

**為什麼 D1-D8 沒有加速？**

核心發現：瓶頸不是 prompt 或 model，而是 **pipeline overhead**。

```
R phase 45s 分佈:
  Model inference:     12s (27%)
  Pipeline overhead:   33s (73%)  ← 真正瓶頸
    - SentenceTransformer loading: ~5s
    - Codeintel scanning: ~10s
    - Arweave distillation: ~5s
    - Other pipeline ops: ~13s
```

D1-D8 的優化都是 **prompt engineering 和 code quality** 改善：
- 減少 token → 但 inference time 已被 num_predict 限制
- 改善 prompt → 但 model 只要 12s
- 減少 retry → 但單次 retry 成本不變

### 真正能加速的方向

| 方向 | 預期收益 | 複雜度 | 狀態 |
|:---|:---:|:---:|:---:|
| **num_predict 512** | -77s | 低 | ✅ 已做 |
| **Persistent Worker** | -17s (cold start) | 高 | ❌ 有 pipe deadlock |
| **Lazy load SentenceTransformer** | -5s | 中 | 未做 |
| **Reduce pipeline phases** | -10s | 高 | 未做 |
| **D1-D8 (prompt 優化)** | ~0s | 低 | ✅ 已做 |

### 下一步建議

#### 如果要繼續追 speed

| 優先級 | 動作 | 預期收益 |
|:---:|:---|:---:|
| 1 | Persistent Worker（修 pipe deadlock） | -17s |
| 2 | Lazy load SentenceTransformer | -5s |
| 3 | 減少 pipeline phases | -10s |

#### 如果 correctness 已足夠

當前 65s 已經可以接受。D1-D8 的 correctness 改善會在 production 中逐漸體現（減少 retry、減少重複錯誤）。

---

*報告基準：2026-06-15，基於 Nexus 當前代碼（commit 96e00ce4）*
*改善前基準：commit fad8f32e*
*改善後基準：65s execution, 83s total*
*資料來源：arxiv.org、huggingface.co/papers、hub.baai.ac.cn*
