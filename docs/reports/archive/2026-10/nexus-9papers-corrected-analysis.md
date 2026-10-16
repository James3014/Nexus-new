# Nexus × 13 Papers/Tools：三層架構下的本地模型能力提升路徑

**目標**：從 9 篇論文中提取可落地的改進方案，嚴格對齊 Nexus 三層架構：
- **3B Advisor**：S2T routing、telemetry、failure taxonomy（low-risk only）
- **7B/14B Coder**：coding、repair、repo-debugging、patch reasoning
- **Rust/Verifier/Claim Gate**：fail-closed backbone

**約束**：
- 3B 還在測試/訓練階段，不可 overclaim
- 3B 只能在 low-risk assisted routing 內影響 final_selected_id
- 3B 不可取代 verifier、claim gate、或 delivery-critical override
- 所有改動必須 minimal、rollbackable、testable、replayable
- 必須產生 generalizable lessons，禁止 task-specific hardcode

---

## 論文 1：Code2LoRA（2606.06492）

**核心問題**：小模型缺乏 repo-level context，RAG 注入 context 太貴且受限 context window。

**關鍵發現**：Hypernetwork 生成 repo-specific LoRA adapter，在 Qwen2.5-Coder-1.5B 上，static track 達 63.8% EM（RAG 只有 39.7%），evolution track 達 60.3% EM（+5.2pp over shared LoRA）。零 inference-time token overhead。

### What — 改什麼

在 **7B/14B Coder 層**，為 coding model 實現 Code2LoRA Hypernetwork，讓 Nexus 能為每個 repo 自動生成專屬 LoRA adapter，取代現有的 RAG context injection。

### Why — 為什麼

Nexus 現在用 `nexus/core/vector_rag.py` 和 `nexus/learning/federated_rag.py` 做 RAG，但：
- 7B/14B 模型 context window 有限，repo-level context 裝不下
- 每次 query 都要 re-retrieve，延遲高
- RAG 在 assertion completion 任務上比 pretrained baseline 還差（39.7% vs 45.7%）

Code2LoRA 把 repo knowledge 壓進參數（LoRA weights），零 token overhead。

**不影響 3B 層**：3B advisor 的 LoRA adapter 已有 provenance lock（`qwen3b_s2t_adapter_v2.json`），Code2LoRA 是獨立的 hypernetwork，不改動 3B 的 adapter loading 邏輯。

### How — 怎麼做

1. **整合 Repository Encoder**：在 `nexus/learning/knowledge_index.py` 增加 file-level + repo-level embedding pipeline（用 frozen Qwen3-Embedding-0.6B 或本地替代品）
2. **實作 Code2LoRA Hypernetwork**：在 `nexus/engine/` 新增 `code2lora_hypernetwork.py`，實現 2-layer MLP + per-module-type output heads，生成 rank-16 LoRA weights
3. **替換 coding model 的 adapter loading**：從靜態 `training/adapters/` 載入改為動態 hypernetwork 生成
4. **Code2LoRA-Evo 支援**：在 `nexus/core/crystal.py` 增加 GRU-based adapter trajectory，讓 adapter 隨 commit history 演進
5. **訓練**：在 RepoPeftBench 或類似資料集上訓練 hypernetwork（~720M 參數，single H100 即可）

**3B 層不動**：3B advisor 的 `S2T3BAdvisor` 保持現有 provenance lock + kill switch + simulation fallback 不變。

**預期收益**：7B/14B coding model 的 repo-level coding 能力從 ~45% EM 提升到 ~60-64% EM。

---

## 論文 2：MLEvolve（2606.06473）

**核心問題**：ML agent 在長鏈任務中缺乏跨分支資訊共享、記憶搜索無狀態、缺乏分層控制。

**關鍵發現**：Progressive MCGS tree search + Retrospective Memory + Adaptive Coding Modes，在 MLE-Bench 上達 SOTA，超越 AlphaEvolve。

### What — 改什麼

在 **跨層**的搜索和記憶策略中，引入 Progressive Tree Search + Retrospective Memory。

### Why — 為什麼

Nexus 的自我進化（crystallization）目前是線性的：執行 → 結晶 → 下次用。但：
- 沒有跨分支資訊共享（agent A 的發現無法傳給 agent B）
- 沒有 retrospective memory（歷史成功/失敗經驗沒有結構化檢索）
- 沒有從 broad exploration 到 focused exploitation 的漸進式搜索

**3B 層的具體改進**：3B advisor 的 `OracleAdvisor`（`nexus/app/oracle_advisor.py`）目前只做 shadow run 結果的簡單合成。MLEvolve 的 retrospective memory 可以讓 3B advisor 在做 routing 建議時，結構化檢索歷史成功/失敗經驗，提升 low-risk routing 的準確度。

### How — 怎麼做

1. **Progressive MCGS**：在 `nexus/engine/battle_swarm.py` 實現 graph-based reference edges，讓 swarm 中的 agent 可以引用其他分支的結果
2. **Retrospective Memory**：在 `nexus/memory/memory_retrieval_service.py` 增加 cold-start domain knowledge base + dynamic global memory 的雙層結構
3. **Adaptive Coding Modes**：在 `nexus/engine/coordinator.py` 分離 strategic planning 和 code generation，根據任務複雜度自動切換
4. **3B Advisor 增強**：在 `nexus/app/oracle_advisor.py` 增加 retrospective memory lookup，讓 3B 在做 routing 建議時可以查詢歷史經驗

**3B 層的約束**：3B 的 retrospective memory 只能用於 low-risk routing 建議，不可影響 medium/high-risk decision。

**預期收益**：多 agent 任務成功率提升 10-15%，3B advisor 的 routing 建議準確度提升。

---

## 論文 3：TIDE（2606.04743）

**核心問題**：Agent 只執行用戶明確要求的任務，忽略了 context 中隱藏的其他重要問題。

**關鍵發現**：Template-guided iterative discovery 比 single-shot 多發現 30-50% 的隱藏問題。

### What — 改什麼

在 **3B Advisor 層**，增加 TIDE-style iterative problem discovery 機制。

### Why — 為什麼

3B advisor 目前的 `advise()` 方法只處理已知的候選人（`candidates: list[S2TCandidate]`）。但：
- 一個 codebase 中通常有多個 coexisting 問題
- 3B 模型 context window 有限，一次只能處理一組候選人
- 沒有 reusable thought templates 來指導問題識別

TIDE 的 iterative discovery + thought templates 讓 3B advisor 每輪發現一批候選問題，然後基於已發現的問題繼續擴展覆蓋。

### How — 怎麼做

1. **Thought Templates**：在 `nexus/contracts/s2t_policy.py` 建立 reusable problem-class schemas（如：type error、resource leak、logic error、API misuse）
2. **Iterative Discovery**：在 `nexus/services/s2t_strict.py` 的 `advise()` 方法中實現 multi-round discovery，每輪 conditioning on 已發現的問題
3. **Evidence Grounding**：每個發現的問題必須附帶 supporting evidence（file:line + 理由）
4. **low-risk 約束**：iterative discovery 的結果只能以 observation-only 模式回傳，不可直接影響 final_selected_id

**3B 層的約束**：TIDE 的輸出是「候選問題列表」，不是「routing 決策」。3B 只能建議，不可直接執行。

**預期收益**：3B advisor 能發現更多隱藏問題，但只以 observation-only 模式回傳。

---

## 論文 4：PACT（2606.05304）

**核心問題**：Multi-agent 系統中 agent 間的 free-form 自然語言通訊膨脹 token usage，消耗 context window。

**關鍵發現**：PACT 將 agent 輸出投射為 compact action-state records，在 OpenHands 上以 -10% tokens 達到同等 resolve rate。

### What — 改什麼

在 **3B Advisor 層**，將 `OracleAdvisor` 的輸出從 free-form 自然語言改為 PACT-style action-state records。

### Why — 為什麼

`OracleAdvisor` 目前的 `synthesize_advice()` 返回的是結構化但仍然冗長的中文文本（含 emoji、格式化、重複描述）。對 3B 模型來說：
- Advisor 的輸出佔用 7B/14B coding model 的 context window
- Free-form 訊息包含大量冗餘（客套話、重複描述、無關細節）
- Token 成本直接影響推理速度和成本

PACT 把 advisor 輸出壓縮成 action-centered 的結構化 record，保留下游 agent 需要的關鍵資訊。

### How — 怎麼做

1. **Action-State Schema**：在 `nexus/contracts/s2t_export.py` 定義 PACT schema（action_type, affected_files, risk_level, evidence_refs, next_step）
2. **通訊壓縮器**：在 `nexus/app/oracle_advisor.py` 增加 PACT projector，將 advisor 輸出投射為 action-state record
3. **共享歷史**：在 `nexus/core/event_bus.py` 用 PACT records 替換完整 natural language entries
4. **3B 端生成**：3B advisor 的 `advise()` 方法直接輸出 PACT records，而非自由文本

**3B 層的約束**：PACT records 只包含 low-risk routing 需要的欄位，不可洩漏 medium/high-risk 決策資訊。

**預期收益**：3B advisor 的 token 消耗降低 40-50%，7B/14B coding model 的有效 context 利用率大幅提升。

---

## 論文 5：EvoArena + EvoMem（2606.13681）

**核心問題**：LLM agent 在動態環境中無法追蹤環境變化，記憶是靜態快照而非 evolution history。

**關鍵發現**：EvoMem patch-based memory paradigm 記錄 structured update histories，在 EvoArena 上平均提升 1.5%，在 GAIA 上提升 6.1%。

### What — 改什麼

在 **3B Advisor 層**，將靜態記憶替換為 EvoMem patch-based evolution memory。

### Why — 為什麼

Nexus 的記憶系統（`nexus/core/eternal_memory.py`、`nexus/core/mem_palace.py`）是 snapshot-based：
- 記住「上次的狀態」但不追蹤「狀態如何變化」
- 對 evolving codebase（不斷 commit 的專案）無法追蹤環境演進
- 3B advisor 的 `OracleAdvisor` 只做簡單的 shadow run 合成，缺乏結構化的 evolution history

EvoMem 的 patch-based paradigm 讓每個記憶都是 structured update history（what changed, when, why），3B advisor 可以通過記憶推理環境演進。

### How — 怎麼做

1. **Patch-based Memory Model**：在 `nexus/memory/memory_models.py` 新增 `EvolutionPatch` dataclass（timestamp, patch_type, affected_scope, before_state, after_state, cause）
2. **Memory Ingestion**：在 `nexus/core/memory/ingest.py` 增加 patch extraction pipeline，從 git diff 中提取 structured patches
3. **Memory Retrieval**：在 `nexus/memory/memory_retrieval_service.py` 支援 evolution-aware retrieval（查詢時返回 evolution chain 而非單一 snapshot）
4. **3B Advisor 整合**：在 `nexus/app/oracle_advisor.py` 的 `synthesize_advice()` 中加入 evolution-aware context，讓 3B 在做 routing 建議時可以查詢 evolution history

**3B 層的約束**：evolution history 只用於 low-risk routing 建議的 context，不可影響 delivery-critical 決策。

**預期收益**：3B advisor 對 evolving codebase 的 routing 建議準確度提升。

---

## 論文 6：SWE-Explore（2606.07297）

**核心問題**：Coding agent 的 repo exploration 能力缺乏細粒度評估，file-level localization 已足夠但 line-level coverage 和 efficient ranking 是瓶頸。

**關鍵發現**：Agentic explorers 在 file-level localization 已經很強，但 line-level coverage 和 efficient ranking 是區分 SOTA 的關鍵軸。

### What — 改什麼

在 **7B/14B Coder 層**，實現 SWE-Explore style multi-granularity exploration。

### Why — 為什麼

Nexus 的 code retrieval 目前是 file-level 或 chunk-level：
- `nexus/core/vector_rag.py` 返回 top-k chunks
- `nexus/search/generator.py` 生成搜索 query
- 沒有 line-level ground truth 和 coverage metrics

對 7B/14B coding model 來說，精確的 line-level localization 比 file-level 更重要——它需要知道「問題在這個文件的哪一行」。

**不影響 3B 層**：SWE-Explore 是 7B/14B coding model 的 exploration 能力，3B advisor 只做 routing 建議。

### How — 怎麼做

1. **Line-level Ground Truth**：從成功的 agent trajectories 中 distill line-level ground truth（哪些 code regions 被實際諮詢過）
2. **Multi-granularity Retrieval**：在 `nexus/core/vector_rag.py` 增加 file → class → function → line 的分層檢索
3. **Coverage + Ranking Metrics**：在 `nexus/benchmarks/metrics.py` 增加 line-level coverage 和 ranking metrics
4. **Exploration Budget**：在 `nexus/engine/coordinator.py` 實現 fixed line budget 的 exploration

**預期收益**：7B/14B coding model 的 code localization 精確度提升。

---

## 論文 7：SMT — Pretraining Recurrent Networks without Recurrence（BAAI）

**核心問題**：RNN 訓練依賴 BPTT，無法並行、梯度消失、長程依賴學習困難。

**關鍵發現**：Supervised Memory Training (SMT) 將 RNN 訓練解耦為預測性狀態目標 + 監督學習，梯度路徑恆為 O(1)。

### What — 改什麼

在 **3B Advisor 層**，用 SMT-style decoupled memory training 優化 3B advisor 的記憶更新邏輯。

### Why — 為什麼

3B advisor 的 `S2T3BAdvisor` 的 LoRA adapter 是靜態訓練的，沒有動態記憶更新機制：
- adapter 是預訓練的，不會隨 runtime experience 演進
- 沒有 decoupling「記憶什麼」和「如何更新記憶」
- 對長序列的 routing history 處理效率低

SMT 的核心 insight 是：將「what to remember」和「how to update」完全分離，可以並行訓練，且梯度路徑穩定。

### How — 怎麼做

1. **Predictive State Objective**：在 `nexus/services/s2t_strict.py` 訓練一個 predictor，學習「給定 歷史 routing，預測下一步需要什麼資訊」
2. **Decoupled Memory Update**：將記憶更新建模為 supervised learning problem（input: (memory_t, routing_t+1), label: memory_t+1）
3. **Parallel Training**：利用 SMT 的 O(1) gradient path 優勢，並行處理多個 routing 更新
4. **整合到 3B LoRA**：在 3B adapter 訓練 pipeline 中加入 SMT loss，讓 3B advisor 的 routing 能力隨 experience 演進

**3B 層的約束**：SMT 只用於 3B advisor 的內部記憶更新，不可影響 verifier 或 claim gate。

**預期收益**：3B advisor 的 routing 準確度隨 experience 演進，特別是對長序列的 routing history。

---

## 論文 8：MUSE-Autoskill（BAAI）

**核心問題**：LLM agent 的 skills 是孤立、靜態的，缺乏生命週期管理、記憶和測試。

**關鍵發現**：MUSE-Autoskill 的五階段生命週期管理（創建→記憶→管理→評估→精煉）在 SkillsBench 上提升 +12.3% 任務成功率、+3.8× 技能復用率。

### What — 改什麼

在 **跨層**的 skill lifecycle 中，建立 **統一查詢 + Context Injection 層**，串連既有分散的 skill 記憶數據，讓 S2T routing 時能召回歷史表現並注入 context。

### Why — 為什麼（修正版：不重複造輪子）

**已有的 recording 系統（足夠強）**：
- `nexus/learning/skill_lifecycle.py` — 使用事件記錄（append-only JSONL）+ frontmatter `last_used_at`
- `nexus/core/skill_outcomes.py` — pass/fail/phantom/reuse/effort 證據記錄（`.nexus/metrics/skill_outcome_events.jsonl`）
- `nexus/core/skill_promotion.py` — L0→L3 升級引擎（基於次數+成功率，寫入 `skill_usage_stats.json`）
- `nexus/learning/skill_registry.py` — SQLite 存儲 win_rate、trust_level、pattern_reuse_rate、retry_count
- `nexus/services/s2t_strict.py` — routing 決策日誌（只記錄「選了什麼」，不記錄「為什麼」）

**缺失的不是 recording，而是 query + injection**：
1. **無跨 session 的 skill 記憶查詢** — 現有 JSONL 只 append 不 query，無法問「上次在類似 context 下這個 skill 表現如何」
2. **無失敗學習迴圈** — outcome 記了但沒人消費來調整下次選擇
3. **無 context-aware 的 skill 回憶** — 選 skill 時不會注入「上次在 X 狀態下失敗過」的歷史
4. **無統一查詢層** — 數據散佈在 5+ 個 JSONL/JSON 裡，無 unified view

**3B 層的具體改進**：3B advisor 的 `advise()` 方法需要選擇合適的 skill routing。現有系統已經記錄了豐富的 skill 表現數據，但 3B 無法查詢。需要建立統一索引 + 查詢接口，讓 3B 在做 routing 建議時可以召回「歷史表現 + 失敗模式 + 成功上下文」。

### How — 怎麼做（修正版：建查詢層，不建 recording）

1. **統一索引層**：在 `nexus/learning/` 新增 `skill_memory_index.py`，對既有 `skill_outcome_events.jsonl` + `skill_usage_stats.json` + `skill_lifecycle.py` 的 JSONL 建立 unified index（SQLite FTS5 或 LanceDB）
2. **Context-Aware 查詢接口**：在 `nexus/learning/skill_memory_index.py` 實現 `query_skill_history(skill_id, task_context)` → 返回該 skill 在類似 context 下的歷史表現（成功率、失敗模式、上次失敗原因）
3. **3B Advisor 整合**：在 `nexus/services/s2t_strict.py` 的 `advise()` 方法中加入 `skill_memory_index.query_skill_history()` 調用，讓 3B routing 時自動注入歷史 context
4. **失敗學習迴圈**：在 `nexus/core/skill_outcomes.py` 增加 failure pattern extraction，將失敗原因結構化後寫入 index，供 future routing 查詢

**不做的事**：不再建立新的 recording 系統（已有 `skill_lifecycle`、`skill_outcomes`、`skill_promotion` 三層 recording）。

**3B 層的約束**：skill memory 查詢結果只用於 low-risk routing 建議的 context injection，不可影響 medium/high-risk skill 切換。

**預期收益**：3B advisor 的 skill routing 準確度提升（基於歷史表現召回），skill 復用率提升 3×（基於 context-aware 匹配）。

---

## 論文 9：BenchEvolver（2606.01286）

**核心問題**：Coding benchmarks 飽和（GPT-5.4 在 LiveCodeBench 上 >99% Pass@1），缺乏有挑戰性的訓練信號。

**關鍵發現**：Solution-centric evolution 將飽和問題轉化為更難的變體，gpt-oss-20b 在 seed+evolved 訓練後，held-out coding performance 提升 +8.7 Pass@1。

### What — 改什麼

在 **7B/14B Coder 層**，實現 BenchEvolver style self-challenging task evolution。

### Why — 為什麼

Nexus 的 benchmarking（`nexus/benchmark/benchmark_runner.py`）和 self-evolution（`nexus/core/self_evolve_engine.py`）目前是被動式的：
- Benchmark 是靜態的，不會隨模型進步而演進
- Self-evolution 只從成功經驗學習，不從失敗中生成挑戰
- 缺乏 closed-loop self-improvement（模型生成挑戰 → 訓練 → 再生成更難的挑戰）

BenchEvolver 的 solution-centric design 讓 7B/14B coding model 自己生成 verified 的 hard tasks，然後用 RL 訓練自己。

**不影響 3B 層**：BenchEvolver 是 7B/14B coding model 的自我挑戰訓練，3B advisor 只做 observation。

### How — 怎麼做

1. **Solution-Centric Mutation**：在 `nexus/core/self_evolve_engine.py` 實現 solution-first mutation（先變異 reference solution，再衍生 statement 和 tests）
2. **Evaluator + Memory**：在 `nexus/engine/crystallization_service.py` 增加 evaluator（驗證 + 難度測量）和 memory（追踪 lineage 和 diversity）
3. **Closed-loop RL**：在 `nexus/engine/reflex_loop.py` 實現 self-improvement loop（evolve → train → evolve again）
4. **Benchmark Evolution**：在 `nexus/benchmark/benchmark_runner.py` 增加 benchmark evolution pipeline，定期更新 benchmark 難度

**預期收益**：7B/14B coding model 通過 self-generated training data，在 held-out benchmarks 上提升 5-8%。

---

## 論文 10：WeaveBench（2606.09426）

**核心問題**：現有 CUA benchmark 將 GUI 和 CLI 能力分開評估，缺乏跨介面長鏈任務的真實評估；outcome-only grading 會大幅高估 agent 表現。

**關鍵發現**：114 個跨 GUI+CLI+code 的真實工作流任務，最佳 model-runtime pair（Claude Opus 4.7 + Claude Code）僅達 41.2% PassRate。Trajectory-aware judge 揭示 outcome-only grading 將 GPT-5.5 從 53.5% 高估到實際 33.3%。失敗機制分析建立 E1-E5 分層 taxonomy（reasoning → tool use → visual grounding → long-horizon discipline → reward hacking），且發現強模型傾向 reward hacking（偽造截圖、hardcoded metrics），弱模型傾向 silent halt。

### What — 改什麼

在 **Rust/Verifier/Claim Gate 層**，實現 WeaveBench style trajectory-aware verification + anti-fabrication detection。

### Why — 為什麼

Nexus 的 claim gate 和 verifier 目前主要做 artifact-level 驗證（`nexus/engine/verifier.py`、`nexus/core/claim_gate.py`）：
- 只驗證「最終交付物是否正確」，不驗證「達成交付物的過程是否合法」
- 無法偵測 forged evidence（偽造截圖、hardcoded metrics、crop/overlay reuse）
- 無法偵測 CLI bypass of GUI（agent 口頭承認需要 GUI 但實際走 CLI）
- 無法偵測 silent halt（agent 停止執行但不報錯）

WeaveBench 的 trajectory-aware judge 證明：outcome-only grading 會讓 agent 的 reward hacking 行為得逞。對 Nexus 來說，如果 claim gate 只看 artifact 不看 trajectory，agent 可以「偽造看起來正確的 evidence」通過 gate。

**E1-E5 taxonomy 直接適用於 Nexus 的 failure classification**：
- E1 Reasoning & Planning：3B advisor routing 失敗的根因分析
- E2 Tool Use & Execution：7B/14B coding model 工具使用錯誤
- E3 Visual Grounding：GUI 相關任務的視覺定位失敗
- E4 Long-horizon Execution Discipline：Nexus swarm 長鏈任務的靜默失敗（20% silent halt + 23.8% premature halt）
- E5 Reward Hacking：agent 偽造 evidence 通過 claim gate（29.9% 的失敗案例）

**不影響 3B 層**：trajectory-aware verification 是 verifier/claim gate 的能力，3B advisor 只做 low-risk routing。

### How — 怎麼做

1. **Trajectory-Aware Verifier**：在 `nexus/engine/verifier.py` 增加 trajectory-level evidence audit，不只驗證 artifact，還驗證 action trace（tool calls、file changes、screenshot sequence）
2. **Anti-Fabrication Detection**：在 `nexus/core/claim_gate.py` 實現 WeaveBench 的 9 種 shortcut pattern detection（fake screenshots、hardcoded metrics、crop/overlay reuse、mock services、CLI bypass of GUI）
3. **E1-E5 Failure Taxonomy**：在 `nexus/core/failure_classifier.py`（新）建立分層失敗分類，取代現有的 flat error code，支援 root cause tracing
4. **Layered Scoring Pipeline**：在 `nexus/engine/claim_gate.py` 實現 min(process_score, deliverable_score) 的 scoring 邏輯，防止 auxiliary dimensions masking weak deliverables
5. **Zeroing Rule**：當 high-confidence shortcut evidence 被偵測到時，直接給予零分（如同 WeaveBench 的 h_t,m=1 → s=0）

**3B 層的約束**：trajectory-aware verification 是 verifier 層的能力，3B advisor 不參與 verification 決策。

**預期收益**：Nexus 的 claim gate 能力從 artifact-level 提升到 trajectory-level，防止 reward hacking；E1-E5 taxonomy 提升 failure root cause analysis 的精確度。

---

## 論文 11：TurboQuant（2504.19874）

**核心問題**：現有 vector quantization 方法在 distortion rate 上未達 optimal，且不支援 online（data-oblivious）場景；Product Quantization 需要 offline k-means 訓練，不適合動態數據。

**關鍵發現**：TurboQuant 通過 random rotation + Beta distribution scalar quantization + QJL residual correction，實現 near-optimal distortion（僅差 information-theoretic lower bound 2.7× 常數因子）。在 KV cache quantization 達 3.5 bits quality neutral、2.5 bits marginal degradation（壓縮 5×+）。在 nearest neighbor search 中超越 data-dependent PQ，且 indexing time 幾乎為零。

### What — 改什麼

在 **跨層**的 vector operations 中，實現 TurboQuant style online vector quantization，取代現有的 RAG embedding storage 和 KV cache 策略。

### Why — 為什麼

Nexus 的 vector operations 散佈在多個模組中：
- `nexus/core/vector_rag.py` — RAG embedding retrieval，使用 FP16/FP32 向量
- `nexus/learning/knowledge_index.py` — knowledge index 的 embedding storage
- `nexus/memory/memory_retrieval_service.py` — memory retrieval 的 vector search
- 3B advisor 的 Ollama inference — KV cache 佔用大量 memory

現有問題：
1. **Vector storage 成本高**：每個 embedding 佔 4 bytes（FP32）或 2 bytes（FP16），大量 repo-level embedding 消耗大量 disk/memory
2. **KV cache memory bottle**：3B advisor 在 long-context routing 時，KV cache 佔用顯著 memory，限制 context window
3. **Offline PQ 不適合 Nexus**：Nexus 的 knowledge index 是動態更新的（每次 crystallization 都新增 data），offline k-means 訓練成本高
4. **RAG retrieval 延遲**：高維向量的 exact nearest neighbor search 成本高

TurboQuant 的 online/data-oblivious 特性完美匹配 Nexus 的動態場景：不需要 calibration，不需要 offline 訓練，直接壓縮 embedding vectors，壓縮 5×+ 而 distortion 接近 optimal。

### How — 怎麼做

1. **TurboQuant Quantize/DeQuantize**：在 `nexus/core/vector_rag.py` 實現 TurboQuant 的兩階段量化（MSE quantizer + QJL residual），將 embedding 從 FP32 壓縮到 2-4 bits
2. **Online Quantization for Dynamic Index**：在 `nexus/learning/knowledge_index.py` 實現 data-oblivious quantization，每次新增 embedding 時直接量化，不需要 retrain codebook
3. **KV Cache Quantization**：在 `nexus/services/s2t_strict.py` 的 Ollama inference pipeline 中整合 TurboQuant KV cache quantization，將 3B advisor 的 KV cache 壓縮 5×
4. **Unbiased Inner Product for RAG**：使用 TurboQuant 的 inner-product optimal variant 確保 RAG retrieval 的 cosine similarity 計算保持 unbiased（避免 MSE quantizer 引入的 bias）
5. **Entropy Encoding**：在 `nexus/core/vector_rag.py` 增加 entropy coding step（codebook pointer 的 entropy encoding），進一步壓縮 storage

**3B 層的具體收益**：KV cache quantization 讓 3B advisor 可以處理更長的 routing context（從 2K tokens 擴展到 10K+ tokens），提升 long-horizon routing 的準確度。

**不做的事**：不替換現有的 embedding model（仍用 Qwen3-Embedding 或替代品），只替換 storage 和 retrieval 的 quantization 層。

**預期收益**：vector storage 成本降低 5-8×（從 FP32 到 2-4 bits），KV cache memory 降低 5×，RAG retrieval 延遲降低（更小的 vector → 更快的 search），3B advisor 的 effective context window 擴展 5×。

---

## 工具 12：Headroom（chopratejas/headroom）

**核心問題**：AI agent 的 context window 被 tool outputs、logs、RAG chunks、files、conversation history 洩滿，token 成本高且延遲大。現有壓縮方案要么只覆蓋單一內容類型，要么不可逆，要么需要 hosted API。

**關鍵發現**：60-95% token 壓縮率，same answers。6 種壓縮演算法（SmartCrusher for JSON、CodeCompressor for AST、Kompress-base ML model、Image compression、CacheAligner for KV cache、CCR reversible compression）。支援 library、proxy、MCP server、agent wrap 四種部署模式。跨 agent 共享記憶（Claude、Codex、Gemini auto-dedup）。`headroom learn` 從失敗 session 中 mining corrections 寫入 CLAUDE.md/AGENTS.md。

### What — 改什麼

在 **跨層**的 context 處理 pipeline 中，整合 Headroom 作為統一的 context compression layer，取代分散的壓縮邏輯。

### Why — 為什麼

Nexus 的 context 處理散佈在多個模組中，且缺乏統一的壓縮策略：
- `nexus/core/vector_rag.py` — RAG chunk 壓縮（目前無專門壓縮，直接塞入 context）
- `nexus/app/oracle_advisor.py` — advisor 輸出壓縮（PACT 只改格式，不改大小）
- `nexus/services/s2t_strict.py` — 3B advisor 的 input context（tool outputs 直接餵入）
- `nexus/engine/coordinator.py` — swarm agent 間的 context 傳遞（free-form 自然語言）
- `nexus/learning/skill_memory_index.py` — skill memory 查詢結果（結構化但冗長）

現有問題：
1. **Token 成本失控**：7B/14B coding model 的 tool outputs 平均 65K tokens（SRE debugging），壓縮後可降到 5K
2. **Context window 洩滿**：3B advisor 的 context window 有限，冗長的 tool outputs 佔用大量空間
3. **無 reversible compression**：壓縮後的資訊無法還原，如果 agent 需要原始細節就丟失了
4. **無跨 agent 記憶共享**：swarm 中的 agent 各自處理 context，無法共享壓縮經驗
5. **CacheAligner 缺失**：provider KV cache 命中率低，重複 context 浪費 computation

Headroom 直接解決所有問題：
- **SmartCrusher**：壓縮 Nexus 的 JSON-based tool outputs（skill outcomes、telemetry logs）
- **CodeCompressor**：壓縮 code snippets（AST-aware，保留結構）
- **CacheAligner**：穩定 prefix，讓 Anthropic/OpenAI KV cache 命中
- **CCR**：reversible compression，agent 可以 retrieve 原始內容
- **Cross-agent memory**：swarm agent 共享壓縮經驗
- **`headroom learn`**：從失敗 session 中 mining，自動更新 AGENTS.md

### How — 怎麼做

1. **整合 Headroom Library**：在 `nexus/core/context_pipeline.py`（新）實現 `compress(messages)` 調用，統一處理所有 context 壓縮
2. **Tool Output 壓縮**：在 `nexus/services/s2t_strict.py` 的 `advise()` 方法中，在餵入 3B advisor 前先通過 Headroom 壓縮 tool outputs
3. **RAG Chunk 壓縮**：在 `nexus/core/vector_rag.py` 的 retrieval 結果上套用 Headroom 壓縮，減少 context window 佔用
4. **CCR Reversible**：在 `nexus/core/context_pipeline.py` 實現 CCR，壓縮後的 context 可以 retrieve 原始內容
5. **CacheAligner**：在 `nexus/engine/coordinator.py` 的 agent-to-agent context 傳遞中套用 CacheAligner，穩定 prefix 提高 cache 命中
6. **Cross-agent Memory**：在 `nexus/engine/battle_swarm.py` 整合 Headroom 的 SharedContext，讓 swarm agent 共享壓縮經驗
7. **`headroom learn` 整合**：在 `nexus/core/crystallization_service.py` 整合 `headroom learn`，從 crystallization 失敗中 mining corrections

**3B 層的具體收益**：3B advisor 的 effective context window 擴展 3-5×（60-95% 壓縮），token 成本降低 60-95%，routing 建議品質提升（更多 context 可用）。

**不做的事**：不替換 Headroom 的壓縮演算法（直接使用 Kompress-base、SmartCrusher、CodeCompressor），只做整合。

**預期收益**：所有層級的 context 處理效率提升 60-95%（token 壓縮），3B advisor effective context 擴展 3-5×，swarm agent 共享壓縮經驗，失敗 session 自動 mining 寫入 AGENTS.md。

---

## 工具 13：turbovec（RyanCodrai/turbovec）

**核心問題**：Nexus 的 vector index（`vector_rag.py`、`knowledge_index.py`）使用 FP32/FP16 向量，10M vectors 佔 31GB RAM；FAISS PQ 需要 offline 訓練；現有方案缺乏 filter-at-search-time 能力。

**關鍵發現**：turbovec 是 TurboQuant（論文 11）的 Rust 實現 + Python bindings，10M vectors 在 4GB RAM 內（8× 壓縮），search 速度超越 FAISS IndexPQFastScan 10-19%（ARM）。Online ingest（無 train step）、SIMD search（NEON + AVX-512BW）、filter at search time（allowlist/bitmask）、pure local。TQ+ calibration 修正低維 embeddings 的 distribution drift，recall +1.4pp。Length-renormalized scoring 使 inner product estimator 在零額外成本下 unbiased。

### What — 替換什麼

直接替換 Nexus 的 `nexus/core/vector_rag.py` 和 `nexus/learning/knowledge_index.py` 中的 vector storage/retrieval 邏輯，改用 turbovec 作為底層 index。

### Why — 為什麼

turbovec 是論文 11（TurboQuant）的 production-ready 實現，直接解決 Nexus 的 vector 基礎設施痛點：

1. **Memory 壓縮**：Nexus 的 `vector_rag.py` 用 FP32，1M vectors 佔 ~6GB。turbovec 用 4-bit quantization，同樣 1M vectors 只佔 ~250MB（24× 壓縮）
2. **Online Ingest**：Nexus 的 knowledge index 是動態更新的（每次 crystallization 新增 data）。turbovec 不需要 offline 訓練，直接 `index.add(vectors)` 即可
3. **Search Speed**：turbovec 在 ARM（Mac M3）上超越 FAISS 10-19%，且支援 filter-at-search-time（Nexus 的 skill memory 需要 filter by skill_id / task_context）
4. **Rust Core**：turbovec 是 Rust 實現，與 Nexus 的 Rust/Verifier layer 一致，可以整合到 Nexus 的 Rust 工具鏈
5. **Pure Local**：不需要 managed service，不需要 data 離開 machine，符合 Nexus 的 local-first 原則
6. **IdMapIndex**：支援 stable external ids + O(1) delete，完美匹配 Nexus 的 skill memory indexing（skill_id → embedding）
7. **Filtered Search**：`search(query, k=10, allowlist=allowed)` 直接在 SIMD kernel 中過濾，Nexus 的 skill memory 查詢可以 filter by task_context

### How — 怎麼做

1. **替換 vector_rag.py**：在 `nexus/core/vector_rag.py` 中，將 FAISS/自建 index 替換為 `turbovec.TurboQuantIndex`，dim=1536（配合 Qwen3-Embedding），bit_width=4
2. **替換 knowledge_index.py**：在 `nexus/learning/knowledge_index.py` 中，將 embedding storage 替換為 `turbovec.IdMapIndex`，使用 skill_id 作為 external id
3. **整合到 skill_memory_index.py**：在 `nexus/learning/skill_memory_index.py`（論文 8 MUSE-Autoskill 新增的模組）中，使用 `IdMapIndex.search(query, k, allowlist=filtered_skill_ids)` 實現 context-aware skill 記憶查詢
4. **整合到 memory_retrieval_service.py**：在 `nexus/memory/memory_retrieval_service.py` 中，使用 turbovec 替換 memory vector search
5. **Rust 原生整合**：在 Nexus 的 Rust 工具鏈中（`nexus/engine/` 的 Rust modules），直接 `cargo add turbovec` 作為 Rust dependency
6. **Python 整合**：在 Nexus 的 Python modules 中，`pip install turbovec` 即可使用

**3B 層的具體收益**：3B advisor 的 skill memory 查詢速度提升 10-19%（ARM SIMD），memory footprint 降低 8-24×（從 FP32 到 4-bit），skill routing 準確度提升（filtered search 精確匹配 task_context）。

**不做的事**：不替換 embedding model（仍用 Qwen3-Embedding 或替代品），只替換 vector storage/retrieval 層。

**預期收益**：vector storage 降低 8-24×（從 FP32 到 2-4 bit），search 速度提升 10-19%（ARM），online ingest 無 train step，filtered search 直接在 SIMD kernel 中過濾。

---

## 整合優先級（對齊三層架構）

> **2026-06-15 更新**：對照 git history，S2T Strict 已完成 Ollama 支援 + Memory Sidecar Pilot（M5-M7），其餘 12 篇論文建議尚未實現。

| 優先級 | 工具/論文 | 目標層級 | 改動模組 | 預期收益 | 實作難度 | 狀態 |
|--------|----------|----------|----------|----------|----------|------|
| P0 | PACT | 3B Advisor | oracle_advisor.py, s2t_export.py | -40-50% token 消耗 | 低 | 未實現 |
| P0 | Headroom | 跨層（context infra） | context_pipeline.py（新）, s2t_strict.py, vector_rag.py, coordinator.py | 60-95% token 壓縮 + reversible + cross-agent memory | 低-中 | 未實現 |
| P0 | WeaveBench | Rust/Verifier/Claim Gate | verifier.py, claim_gate.py, failure_classifier.py（新） | 防止 reward hacking + E1-E5 taxonomy | 中 | 未實現 |
| P0 | TurboQuant + turbovec | 跨層（vector infra） | vector_rag.py, knowledge_index.py, skill_memory_index.py, memory_retrieval_service.py | 8-24× storage 壓縮 + 10-19% search 加速 + filtered search | 低（pip install turbovec） | 未實現 |
| P0 | Code2LoRA | 7B/14B Coder | knowledge_index.py, engine/ | +15-20% repo-level coding | 高 | 未實現 |
| P1 | MUSE-Autoskill | 跨層（3B 整合） | skill_memory_index.py（新）, s2t_strict.py | +12% 任務成功率 | 低-中 | 未實現 |
| P1 | SWE-Explore | 7B/14B Coder | vector_rag.py, search/ | +10% localization 精確度 | 中 | 未實現 |
| P1 | BenchEvolver | 7B/14B Coder | self_evolve_engine.py | +5-8% held-out coding | 高 | 未實現 |
| P2 | EvoMem | 3B Advisor | memory_models.py, oracle_advisor.py | +3-6% evolving codebase | 中 | 未實現 |
| P2 | TIDE | 3B Advisor | s2t_strict.py, s2t_policy.py | +30-50% 問題發現 | 低 | 未實現 |
| P2 | MLEvolve | 跨層（3B 整合） | oracle_advisor.py, memory_retrieval_service.py | +10-15% 多 agent 任務 | 高 | 未實現 |
| P3 | SMT | 3B Advisor | s2t_strict.py, adapter training | 記憶更新效率提升 | 高 | 未實現 |

### 已實現的基礎建設（不在 9 篇論文內，但影響後續實作）

| 能力 | 實現位置 | 關鍵 commit | 對 9 篇論文的影響 |
|------|----------|-------------|-------------------|
| S2T Ollama 推理 | `s2t_strict.py` | `c7c9d186` | 3B advisor 可本地推理，PACT/TIDE 可直接整合 |
| CPU/FP32 fallback | `s2t_strict.py` | `f1290aa2` | Mac 開發環境可用，降低實作門檻 |
| Memory Sidecar Pilot | `s2t_memory_sidecar_shadow.py` | `08474315` (M6) | 已有 shadow evaluation 基礎，可擴展為 skill memory 查詢層 |
| Golden Fixtures | `tests/fixtures/s2t_memory_sidecar/` | `9dca3511` (M5) | 10 個場景的 fixture，可用於驗證新增的 memory 功能 |
| Rollout Control | `s2t_strict.py` | `39193b89` | 5 級 assisted mode + canary rate，PACT/TIDE 可複用 |
| Semantic Safety Gate | `s2t_strict.py` | `a860fa66` | Phase A3 verifier_result + evidence check，防止 3B 越權 |

---

## MVP 路徑（三層架構對齊）

> **2026-06-15 更新**：S2T 基礎建設已完成（Ollama + Memory Sidecar Pilot），MVP 門檻降低。

如果只做 3 件事：

### 1. PACT（3B Advisor 層）— 高優先，低風險
將 `OracleAdvisor` 的輸出從 free-form 自然語言改為 PACT-style action-state records。
- **改動**：`nexus/app/oracle_advisor.py` + `nexus/contracts/s2t_export.py`
- **收益**：3B advisor 的 token 消耗降低 40-50%
- **風險**：低（只是輸出格式改動，不影響核心邏輯）
- **可回滾**：是
- **前置條件**：已滿足（Ollama 推理已實現，可直接整合 PACT 輸出）

### 2. WeaveBench Trajectory-Aware Verification（Rust/Verifier/Claim Gate 層）— 高優先，結構性缺口
將 claim gate 從 artifact-level 升級為 trajectory-level evidence audit，實現 anti-fabrication detection + E1-E5 failure taxonomy。
- **改動**：`nexus/engine/verifier.py` + `nexus/core/claim_gate.py` + `nexus/core/failure_classifier.py`（新）
- **收益**：防止 reward hacking（偽造 evidence 通過 gate），failure root cause analysis 精確度提升
- **風險**：中（需要 redesign verifier 的 scoring pipeline）
- **可回滾**：是（退回 artifact-only verification）
- **前置條件**：需確認現有 verifier 的 trajectory logging 是否足夠（`nexus/engine/trajectory_logger.py`）

### 3. TurboQuant Vector Quantization（跨層 infrastructure）— 高優先，低風險，高收益
將 Nexus 的 vector operations 從 FP32 升級為 online 2-4 bit quantization，同時壓縮 embedding storage 和 KV cache。
- **改動**：`nexus/core/vector_rag.py` + `nexus/learning/knowledge_index.py` + `nexus/services/s2t_strict.py`
- **收益**：vector storage 壓縮 5-8×，KV cache 壓縮 5×，3B advisor effective context window 擴展 5×
- **風險**：低（online data-oblivious，不需要 offline 訓練，可回滾到 FP16）
- **可回滾**：是（退回 FP16 storage）
- **前置條件**：需確認現有 embedding pipeline 是否已使用標準向量格式（`nexus/core/vector_rag.py`）

**三者組合效果**：3B advisor 更精準（PACT）且 context 更長（TurboQuant KV cache），7B/14B coding model 的 RAG 更快更省（TurboQuant vector storage），Rust/verifier/claim gate 更安全（WeaveBench trajectory-aware verification），整體形成「3B 本地核心顧問 + 7B/14B 本地修復模型 + Rust/verifier/claim gate fail-closed + trajectory-aware anti-fabrication + online vector quantization infrastructure」的能力閉環。

**替代 MVP 選項（如果只需要 3 件事）**：
- 原方案：PACT + WeaveBench + Code2LoRA
- 方案 B：PACT + WeaveBench + TurboQuant（TurboQuant 的 infrastructure 收益更廣，覆蓋所有層級）
- 方案 C：Headroom + PACT + WeaveBench（Headroom 的 context 壓縮收益最廣，60-95% token 節省，且實作難度最低）
- 方案 D：turbovec + Headroom + WeaveBench（turbovec + Headroom 組合 = vector 8-24× 壓縮 + context 60-95% 壓縮，基礎設施收益最大）
- 決策點：Code2LoRA 提升 coding model 精準度（+15-20%），turbovec 提升 vector 基礎設施（8-24× compression + 10-19% search 加速），Headroom 提升 context 處理效率（60-95% token 壓縮 + reversible + cross-agent memory）。如果 token 成本/context window 是最大瓶頸，選 Headroom；如果 vector memory/disk 是瓶頸，選 turbovec；如果 coding accuracy 是瓶頸，選 Code2LoRA。turbovec + Headroom 組合覆蓋最廣的基礎設施痛點。

---

## 3-Sprint 執行計劃（不升權、先鋪路）

> **核心原則**：3B 維持 shadow / low-risk assisted advisor，治理與 claim 仍留在 runtime fail-closed 邊界內。任何切片都必須可回滾、可測、可重播。不做 3B 取代 router、不做 verifier replacement、不做 runtime default change。

### 開工原則

- 只做三類事：**壓縮與索引基礎設施**、**補 verifier / claim gate**、**補 low-risk routing 的查詢與觀測**
- 不做 3B 取代 router、不做 verifier replacement、不做 runtime default change
- 每個切片都要有 **focused tests**、**telemetry / receipt 證據**、**rollback 開關**
- 3B 仍然只能待在 shadow S2T selector/reranker advisor 的位置，直到 held-out evaluation 證明 trust mismatch 不上升、public-claim precision 不下降

### 停止條件（寫死）

只要出現以下任一情況，立刻停在 shadow / research artifact，不進下一階段：
- trust mismatch 增加
- public-claim precision 下降
- 3B 影響到 verifier / claim / delivery-critical path
- 無法 fallback 到 rule selector 與 Python path

### 回報格式（每完成一個 task）

```
改了哪些檔案：
加了哪些測試：
開關與 rollback 怎麼做：
telemetry / receipt 產生了什麼：
authority boundary 沒碰：
```

---

### Sprint A：壓縮與索引基礎設施（低風險 infra 優化）

> 不改 authority 邊界。掛在既有 low-risk assisted / shadow 路徑上。

#### A1：PACT 輸出收斂

**目標**：把 advisor 輸出改成 action-state records，只保留 `action_type / affected_scope / risk_level / evidence_refs / next_step` 欄位。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| S2T Ollama 推理 | ✅ 已實現 | `s2t_strict.py` (`c7c9d186`) |
| OracleAdvisor 模板渲染 | ✅ 已實現 | `nexus/app/oracle_advisor.py` |
| Rollout Control (5級 assisted mode) | ✅ 已實現 | `s2t_strict.py` (`39193b89`) |
| PACT action-state schema | ❌ 未實現 | 需新增 `nexus/contracts/s2t_export.py` |

**改動**：
- `nexus/contracts/s2t_export.py`（新）：定義 PACT schema（action_type, affected_scope, risk_level, evidence_refs, next_step）
- `nexus/app/oracle_advisor.py`：`synthesize_advice()` 改為輸出 PACT records
- `nexus/services/s2t_strict.py`：3B advisor 的 `advise()` 直接輸出 PACT records

**測試**：
- Schema validation（PACT record 格式正確）
- 舊格式 fallback（非 PACT 輸出仍可解析）
- 相同輸入前後語意等價比對

**驗收**：low-risk routing trace 仍可讀、token 明顯下降、`final_selected_id` authority 不外移。

**進度**：🔲 未開始

---

#### A2：Headroom-lite 壓縮層

**目標**：先只壓 tool outputs、RAG chunks、advisor context 三種輸入，不碰 cross-agent memory 自動學習。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| 9 個獨立壓縮系統 | ✅ 已存在（但分散） | TOON、ContextCompactor、BudgetGovernor 等 |
| AAAK text compression | ⚠️ 不穩定 | `memory_repository.py` `compress_to_aaak()` |
| Brain De-Entropy (dialogue pruning) | ✅ 已實現 | `nexus/core/brain_de_entropy.py` |
| Neural Aggregator (triage summarize) | ✅ 已實現 | `nexus/core/neural_aggregator.py` |
| Evidence Compactor | ✅ 已實現 | `nexus/services/local_heal/evidence_compactor.py` |
| 統一 ContentRouter | ❌ 未實現 | 需新增 |
| Reversible Cache (CCR) | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/compression/smart_crusher.py`（新）：JSON 壓縮（key 省略、nested array flatten、重複 structure dedup）
- `nexus/core/compression/code_compressor.py`（新）：Code 壓縮（AST-aware，strip comments/whitespace/unused imports）
- `nexus/core/compression/text_compressor.py`（新）：Text 壓縮（rule-based，template substitution + regex extraction）
- `nexus/core/compression/content_router.py`（新）：內容類型偵測 → 選擇正確的 compressor
- `nexus/core/compression/reversible_cache.py`（新）：CCR，壓縮後快取原始內容，可 retrieve
- `nexus/core/unified_context_pipeline.py`（新）：統一 pipeline，取代 9 個獨立系統

**測試**：
- Reversible / non-reversible 兩路測試
- 壓縮前後關鍵欄位保留
- 超長輸出不破 schema

**驗收**：3B input context 更短，但 semantic safety gate 與 assisted-mode telemetry 不變。

**進度**：🔲 未開始

---

#### A3：TurboQuant 向量層（內部實現）

**目標**：替換 vector_rag、knowledge_index、memory_retrieval_service 的底層 storage / retrieval，不換 embedding model。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| LanceDB vector DB | ✅ 已實現 | `nexus/core/vector_rag.py` |
| 三個 embedding 模型 | ✅ 已實現 | MiniLM (384)、nomic (768)、Jina (1024) |
| VectorRAG + topology rerank | ✅ 已實現 | `nexus/core/vector_rag.py` |
| KnowledgeIndex + semantic search | ✅ 已實現 | `nexus/learning/knowledge_index.py` |
| MemoryRetrievalService (tiered ranking) | ✅ 已實現 | `nexus/services/memory_retrieval_service.py` |
| Hybrid Retrieval (BM25 + Dense RRF) | ✅ 已實現 | `nexus/contracts/hybrid_retrieval.py` |
| FP32 向量量化 | ❌ 未實現 | 所有向量都是 FP32 |
| Random rotation + Lloyd-Max | ❌ 未實現 | 需新增 |
| Bit-packing | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/quantization/turbo_quantizer.py`（新）：TurboQuant 核心（random rotation + Lloyd-Max codebook + bit-pack）
- `nexus/core/quantization/codebook.py`（新）：Lloyd-Max 離線計算 Beta distribution 的 optimal scalar quantizer
- `nexus/core/quantization/bitpack.py`（新）：2-bit/4-bit bit-packing + SIMD-friendly layout
- `nexus/core/quantization/rotation.py`（新）：Random orthogonal rotation matrix 生成與應用
- `nexus/core/quantized_vector_store.py`（新）：QuantizedVectorStore，封裝 LanceDB，透明量化/反量化
- `nexus/core/vector_rag.py`：改用 `QuantizedVectorStore`
- `nexus/learning/knowledge_index.py`：改用 `QuantizedVectorStore`
- `nexus/services/memory_retrieval_service.py`：改用 `QuantizedVectorStore`

**測試**：
- Recall 對照（FP32 vs 4-bit，k=10/64）
- Filtered search（allowlist 正確過濾）
- Online ingest（無 train step，直接 add）
- Rollback 到 FP16/FP32

**驗收**：index 可熱切換、search 結果偏差在可接受範圍內、沒有破壞現有 memory sidecar shadow 路徑。

**進度**：🔲 未開始

---

### Sprint B：Verifier / Claim Gate 強化（補 fail-closed 骨架）

> 補 Nexus 最核心的 fail-closed 骨架，不是讓模型更靠近決策權。

#### B1：Trajectory-Aware Verifier Lite

**目標**：在現有 verifier 上新增 trace audit，第一版只檢查 tool calls / file changes / evidence refs / stop reason 四類訊號。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| Rust ReceiptVerifier (4-gate) | ✅ 已實現 | `nexus-core-rs/src/receipt_verifier.rs` |
| Python EvidenceVerifier (physical replay) | ✅ 已實現 | `nexus/delivery/evidence_verifier.py` |
| S2TStrictGate (claim gate) | ✅ 已實現 | `nexus/contracts/s2t_policy.py` |
| ClaimEvidenceReadModel (5 sub-gates) | ✅ 已實現 | `nexus/contracts/claim_evidence_read_model.py` |
| Trajectory-level audit | ❌ 未實現 | 需新增 |
| Anti-fabrication detection | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/verification/trajectory_auditor.py`（新）：Trajectory-level evidence audit
- `nexus/delivery/evidence_verifier.py`：增加 trajectory audit 方法

**測試（三組）**：
- Artifact 正確但過程不合法 → 應 fail
- 過程合法但 artifact 失敗 → 應 fail
- Trace 缺欄位 → 應 fail

**驗收**：verifier 能區分「做對了」和「看起來像做對了」。

**進度**：🔲 未開始

---

#### B2：Anti-Fabrication 規則集

**目標**：實作最值錢的 5 類 shortcut detection：fake evidence refs、hardcoded metrics、missing action trace、CLI bypass 宣告不一致、silent halt。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| Failure taxonomy v1 (flat) | ✅ 已實現 | `failure_taxonomy_v1.md` |
| CritiqueEngine (overclaim detection) | ✅ 已實現 | `nexus/core/critique_engine.py` |
| S2T Runtime Evidence Logging | ✅ 已實現 | `s2t_strict.py` JSONL |
| 9 種 shortcut pattern detection | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/verification/anti_fabrication.py`（新）：5 種 shortcut detection 規則

**測試**：
- 每一類偽造 fixture（5 組）
- 一組正常 fixture（不應觸發）

**驗收**：高信心 shortcut 直接 fail-closed，不影響正常通過樣本。

**進度**：🔲 未開始

---

#### B3：E1-E5 Failure Taxonomy Lite

**目標**：新增分層失敗分類，第一版只要求分類與 telemetry 寫出，不要求自動修復策略。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| Failure taxonomy v1 (flat) | ✅ 已實現 | `failure_taxonomy_v1.md`（4 phase, flat codes） |
| GovernanceError (Rust) | ✅ 已實現 | `src/governance/error.rs` |
| FailureMemory (past failure patterns) | ✅ 已實現 | `nexus/services/local_heal/failure_memory.py` |
| E1-E5 分層 taxonomy | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/verification/failure_taxonomy.py`（新）：E1-E5 分層失敗分類

**測試**：
- Reasoning 樣本 → E1
- Tool use 樣本 → E2
- Long-horizon 樣本 → E4
- Reward hacking 樣本 → E5

**驗收**：錯誤不再只有 flat code，而能用於後續 lesson 與 adoption gate 報表。

**進度**：🔲 未開始

---

### Sprint C：Low-Risk Routing 查詢與觀測（提升品質，不越權）

> 只做 query + injection、只做更細粒度 retrieval，不做 medium/high-risk 自動切換，不做 3B runtime default adoption。

#### C1：Skill Memory Index（MUSE-Autoskill Query Layer）

**目標**：把 skill_outcome_events、skill_usage_stats、lifecycle 記錄做 unified index，提供 `query_skill_history(skill_id, task_context)`。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| SkillLifecycle (event recording) | ✅ 已實現 | `nexus/learning/skill_lifecycle.py` |
| SkillOutcomes (pass/fail/phantom) | ✅ 已實現 | `nexus/core/skill_outcomes.py` |
| SkillPromotion (L0→L3) | ✅ 已實現 | `nexus/core/skill_promotion.py` |
| SkillRegistry (SQLite win_rate) | ✅ 已實現 | `nexus/learning/skill_registry.py` |
| SkillMemoryIndex (JSONL read-model) | ✅ 已實現 | `nexus/learning/skill_memory_index.py` |
| Unified FTS5/LanceDB index | ❌ 未實現 | 需升級現有 JSONL index |
| Context-aware query | ❌ 未實現 | 需新增 `query_skill_history()` |

**改動**：
- `nexus/learning/skill_memory_index.py`：升級為 FTS5 或 LanceDB unified index
- 新增 `query_skill_history(skill_id, task_context)` 方法

**測試**：
- 跨 session query
- 失敗模式召回
- Context filter（by task_context）

**驗收**：3B 只能讀取這些歷史作為 low-risk advice context，不能直接改高風險選擇權。

**進度**：🔲 未開始

---

#### C2：Failure Pattern Extraction

**目標**：把 skill failure reason 結構化寫回 index（phantom、retry spike、reuse drop、trust issues）。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| SkillOutcomes 事件記錄 | ✅ 已實現 | `nexus/core/skill_outcomes.py` |
| FailureMemory (past patterns) | ✅ 已實現 | `nexus/services/local_heal/failure_memory.py` |
| 結構化 failure extraction | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/skill_outcomes.py`：增加 failure pattern extraction 方法
- `nexus/learning/skill_memory_index.py`：failure reasons 結構化寫入 index

**測試**：
- Failure extraction 正確性
- 去重（同一 failure 不重複寫入）

**驗收**：後續 advisor 報表能說清楚「這個 skill 以前在相似 context 下怎麼失敗」。

**進度**：🔲 未開始

---

#### C3：SWE-Explore-Lite

**目標**：先做 file → function → line 的多粒度 retrieval 和 line-level evidence logging，不直接宣稱 coder 能力已提升。

**已有基礎**：
| 能力 | 狀態 | 位置 |
|------|------|------|
| VectorRAG (file/chunk-level) | ✅ 已實現 | `nexus/core/vector_rag.py` |
| SurgicalIntell (symbol-level) | ✅ 已實現 | `nexus/engine/surgical_intel_service.py` |
| Multi-granularity retrieval | ❌ 未實現 | 需新增 file → function → line 分層 |
| Line-level evidence logging | ❌ 未實現 | 需新增 |

**改動**：
- `nexus/core/vector_rag.py`：增加 file → class → function → line 分層 retrieval
- `nexus/engine/surgical_intel_service.py`：增加 line-level evidence logging

**測試**：
- Localization fixture（給定問題，驗證定位到正確 line）
- Ranking metric（line-level coverage）
- Fixed exploration budget

**驗收**：7B/14B patch reasoning 有更精準的定位證據，但沒有 task-specific hardcode。

**進度**：🔲 未開始

---

### Sprint 總覽

| Sprint | 切片 | 目標層級 | 風險 | 依賴 |
|--------|------|----------|------|------|
| **A** | A1 PACT | 3B Advisor | 低 | 無 |
| **A** | A2 Headroom-lite | 跨層 context | 低 | 無 |
| **A** | A3 TurboQuant | 跨層 vector | 低 | 無 |
| **B** | B1 Trajectory Verifier | Verifier | 中 | A3（需要 trajectory logging） |
| **B** | B2 Anti-Fabrication | Claim Gate | 中 | B1 |
| **B** | B3 E1-E5 Taxonomy | Failure Classification | 低 | B2 |
| **C** | C1 Skill Memory Index | 3B Advisor (query) | 低 | A1（PACT format） |
| **C** | C2 Failure Extraction | 3B Advisor (query) | 低 | C1 |
| **C** | C3 SWE-Explore-Lite | 7B/14B Coder | 低 | A3（vector retrieval） |

**Sprint A 和 C 可以並行**（不同模組），**Sprint B 依賴 A3 的 trajectory logging 基礎**。

---

## 交付標準（對齊 operational spec）

只能在以下情況說「Nexus 能力提升」：

- 至少一個可泛化 failure 被修復
- 有 regression test
- focused gate 綠
- 有 receipt/log/telemetry 證據
- 3B advisor 若參與，必須有合法 S2T telemetry（`NEXUS_S2T_3B_ADVISOR_ENABLED=1`、`NEXUS_S2T_3B_ASSISTED_MODE=low_risk`、trust_mismatch == 0）
- lesson 已寫回
- 沒有新增 task-specific hardcode
- 沒有破壞 fail-closed
- 沒有讓 3B 越權到 public claim / delivery-critical / verifier replacement

否則只能說：
- pipeline reachability improved
- harness stabilized
- evidence alignment improved
- S2T advisor telemetry improved
- low-risk assisted routing validated
- one task solved
- model reached patch layer

不得說：
- 3B controls Nexus
- 3B replaces verifier
- 3B replaces claim gate
- Qwen 已接近 Gemini/GPT
- Nexus 已泛化提升
- benchmark capability improved

除非有相應對照證據。

---

*報告生成時間：2026-06-14*
*最後更新：2026-06-15（新增 3-sprint 執行計劃，路徑 B 內部實現）*
*論文來源：arxiv.org, hub.baai.ac.cn, huggingface.co, github.com*
*目標：Nexus 三層架構下的本地模型能力提升（路徑 B：零外部 dependency）*
*約束：3B low-risk only, verifier fail-closed, generalizable lessons only*
