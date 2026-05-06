# Nexus S2T Runtime Policy and Training Continuation Plan

日期：2026-05-05

## 判斷

S2T 不應被設計成 Gemini Flash 專用補丁。它應成為 Nexus 的模型無關 runtime policy layer：在高風險節點生成多個候選，讓 selector / reranker / verifier / repair gate 選出可驗證交付，而不是直接相信第一個候選。

Agent Lightning 與 ml-intern 不應先進 runtime 主路徑。正確順序是：

1. Nexus S2T 先在 runtime 產生可信決策與 trace。
2. Agent Lightning 消化 S2T trace，優化 prompt、selector policy、preference / reward model。
3. ml-intern 自動化 post-training 研究迴圈，負責資料整理、訓練腳本、GPU job、評估與報告。
4. Nexus benchmark / gate 決定是否吸收訓練成果，不讓研究 agent 直接改 production control plane。

## 目標

- 把 Nexus 現有 Route Decision、Claim Gate、Delivery Gate、Hyper / Repair、CodeIntel / MemPalace / Belief 訊號組合成 S2T 控制層。
- 先在 shadow mode 量測「如果 S2T 介入，是否會選到更可驗證的候選」。
- 在 Strict mode 將 S2T 用於 claim、repair、delivery 前的 fail-closed 節點。
- 輸出可訓練 trace，讓 Agent Lightning / ml-intern 能接續，而不是重新解析自然語言報告。
- 完成從規劃、契約、實作、測試、benchmark、訓練接續到採納 gate 的長流程。

## 非目標

- 不直接訓練底模作為第一階段。
- 不讓 S2T 繞過現有 A/C、Claim Gate、Delivery Gate。
- 不讓 selector 的敘述理由取代 empirical verifier。
- 不讓 ml-intern 自動修改 Nexus runtime 預設策略。
- 不把 frozen 12x2 benchmark 的 100% 結果當成唯一成功標準。

## 核心架構

```text
Task Input
  -> Route / Risk Classifier
  -> Candidate Generator
  -> S2T Selector / Reranker
  -> Verifier / Claim Gate
  -> Repair / Second Pass
  -> Delivery Gate
  -> S2T Trace Writer
  -> Agent Lightning / ml-intern Dataset Export
```

S2T 是 inference-time policy improvement。Agent Lightning 是 training-time policy distillation / optimization。ml-intern 是 training research automation。

## Runtime Modes

| Mode | 對象 | 行為 | 預設風險 |
| --- | --- | --- | --- |
| Shadow | 所有模型 | 記錄候選與 selector 判斷，但不改最終輸出 | 低 |
| Lite | Flash / 便宜模型 | 高頻 top-k rerank，低成本 verifier | 中 |
| Standard | Pro / 高階模型 | 只在高風險 route / repair / evidence 節點 rerank | 中 |
| Strict | claim / delivery / public report | selector + verifier + delivery gate 必過 | 低交付風險，高成本 |

初始只允許 Shadow 與 Strict。Lite / Standard 必須等 Shadow 數據證明 selector 有正 lift 後再啟用。

## S2T Trace Contract

新增契約建議：

- `nexus/contracts/s2t_trace.py`
- `nexus/contracts/s2t_policy.py`
- `nexus/contracts/s2t_export.py`

最小 event schema：

```json
{
  "schema_version": "s2t.v1",
  "task_id": "nexus-value-repair-001",
  "run_id": "2026-05-05T00:00:00Z",
  "model": "gemini-3-flash-preview",
  "mode": "shadow|lite|standard|strict",
  "phase": "P|X|D|R|A|C",
  "risk_tier": "low|medium|high|public_claim",
  "route_decision_ref": ".nexus/reports/...",
  "candidate_set_id": "candset-001",
  "candidates": [
    {
      "candidate_id": "A",
      "source": "model_first_pass|repair_pass|route_variant|tool_plan",
      "content_ref": ".nexus/reports/s2t/candidates/A.json",
      "claimed_outcome": "patch passes targeted tests",
      "static_score": 0.64,
      "selector_score": 0.71,
      "risk_flags": ["missing_test_evidence"]
    }
  ],
  "selected_candidate_id": "B",
  "selection_reason_codes": [
    "has_empirical_test_evidence",
    "lower_claim_risk",
    "matches_route_decision"
  ],
  "verifier": {
    "name": "semantic_verifier|claim_gate|delivery_gate|pytest",
    "result": "pass|fail|not_run",
    "evidence_ref": ".nexus/reports/..."
  },
  "repair": {
    "attempted": true,
    "repair_candidate_id": "R1",
    "repair_result": "verified|rejected|budget_exhausted"
  },
  "final_delivery": {
    "semantic_verified": true,
    "trust_mismatch": false,
    "delivery_gate": "pass|fail"
  }
}
```

Trace 寫入規則：

- JSONL append，只追加，不覆寫。
- content_ref 指向 artifact，不把長 patch / 長 report 全塞進 event。
- public report 只能引用 gate-passed trace。
- training export 必須先做 redaction。

## Selector Scoring

第一版不要上 ML selector，先用可解釋規則：

| Score Component | 權重 | 來源 |
| --- | --- | --- |
| empirical evidence present | 0.30 | tests / verifier / artifact refs |
| route alignment | 0.20 | CapabilityPlanner / RouteDecision |
| claim risk reduction | 0.20 | Claim Gate / public gate |
| repair plausibility | 0.15 | targeted failure signature / diff scope |
| cost / latency budget | 0.10 | model calls / wall time / tokens |
| memory consistency | 0.05 | MemPalace / CodeIntel |

選擇規則：

- verifier fail 的候選不得被選為 final。
- public claim 缺 gate evidence 時必須 fail-closed。
- 若 top-1 與 top-2 分差低於閾值，進入 second-pass verifier。
- 若所有候選都 fail，輸出 `NO_VERIFIED_CANDIDATE`，不得敘述成功。

## Agent Lightning 接續點

Agent Lightning 官方定位是可用於任意 agent framework 的優化框架，支援 Reinforcement Learning、Automatic Prompt Optimization、Supervised Fine-tuning 等方法，並以 spans / store / trainer 連接 rollout 與訓練。

Nexus 的接法：

```text
S2T Trace JSONL
  -> redacted span converter
  -> Agent Lightning LightningStore
  -> APO / SFT / preference optimization
  -> updated selector prompt / policy resource
  -> Nexus benchmark gate
```

第一階段只使用：

- APO：優化 selector prompt、repair prompt、claim gate prompt。
- SFT / preference export：把「原 top-1 失敗候選 vs verifier 接受候選」轉成偏好資料。

暫緩：

- Full RL。
- 自動更新 production prompt。
- 用未經 hidden verifier 的 reward 做採納。

## ml-intern 接續點

ml-intern 適合放在 research automation lane，負責 post-training 實驗，不直接接管 runtime。

```text
S2T training dataset
  -> ml-intern experiment brief
  -> dataset repair / training script
  -> HF Jobs / local training
  -> evaluation reports
  -> Nexus benchmark import
  -> adoption gate
```

適合交給 ml-intern：

- 將 S2T trace 轉 Hugging Face dataset。
- 建立 preference / SFT / GRPO candidate schemas。
- 跑小模型 selector / reranker 訓練。
- 比較 rule selector、prompt selector、trained selector。
- 產生訓練與 failure analysis 報告。

不交給 ml-intern：

- 修改 default route policy。
- 修改 public claim gate。
- 直接發布 benchmark claim。
- 直接替換 Nexus runtime selector。

## 指標

Runtime 指標：

- `s2t_shadow_counterfactual_lift`
- `candidate_top1_fail_rate`
- `selector_override_rate`
- `selector_override_verified_rate`
- `second_pass_rescue_rate`
- `no_verified_candidate_rate`
- `claim_gate_rescue_rate`
- `delivery_gate_rescue_rate`
- `trust_mismatch_rate`
- `time_to_verified`
- `cost_per_verified_task`

Training 指標：

- `preference_pair_count`
- `accepted_candidate_entropy`
- `reward_hacking_incident_rate`
- `trained_selector_win_rate`
- `prompt_policy_regression_rate`
- `benchmark_generalization_delta`

採納門檻：

- Shadow mode 至少 30 個 eligible rows。
- `selector_override_verified_rate` 必須高於原 top-1 verified rate。
- `trust_mismatch_rate` 不得上升。
- Strict mode 不得降低 public claim gate precision。
- 訓練版 selector 必須在 held-out tasks 上勝過 rule selector，否則只保留為研究 artifact。

## Phase 0: Spec / Contract

目標：只定義 schema、policy、export，不接 runtime 主路徑。

實作：

- 新增 S2T trace / policy / export contracts。
- 新增 JSON serialization / redaction tests。
- 定義 `NO_VERIFIED_CANDIDATE` 與 fail-closed 語義。

Acceptance:

- contracts 可 round-trip JSON。
- redaction 會移除 token / secret / private path 類型欄位。
- invalid verifier result 無法被標為 final success。

Verification:

- `uv run pytest tests/contracts/test_s2t_contracts.py`
- `uv run pytest tests/contracts/test_s2t_redaction.py`

## Phase 1: Shadow Mode

目標：不改現有輸出，只記錄 counterfactual。

接線點：

- route / planner output 後。
- repair candidate 生成後。
- claim / delivery gate 前。

實作：

- `S2TShadowRecorder` 收集候選。
- `RuleBasedS2TSelector` 產生 counterfactual selected candidate。
- trace 寫入 `.nexus/reports/s2t_trace/<run_id>.jsonl`。

Acceptance:

- Shadow mode off 時行為完全不變。
- Shadow mode on 時 final delivery 不受 selector 影響。
- 每個 eligible task 至少有 candidate_set、selector_score、verifier outcome。

Verification:

- `uv run pytest tests/services/test_s2t_shadow.py`
- `uv run pytest tests/ops/test_s2t_trace_writer.py`

## Phase 2: Strict Gate for Claim / Delivery

目標：只在高風險節點介入 final decision。

規則：

- public claim 必須有 selected candidate + verifier evidence。
- delivery 前若 selector 判定 evidence insufficient，輸出 blocked receipt。
- repair 前若 top candidate 無 empirical evidence，觸發 second-pass verifier。

Acceptance:

- 缺 evidence 的 public claim 被 block。
- 有 verified candidate 的 delivery 可通過。
- 無 verified candidate 時不能生成成功報告。

Verification:

- `uv run pytest tests/gates/test_s2t_claim_gate.py`
- `uv run pytest tests/gates/test_s2t_delivery_gate.py`
- `uv run pytest tests/services/test_s2t_no_verified_candidate.py`

## Phase 3: Repair / Candidate Integration

目標：讓 S2T 真正改善 repair 選擇。

實作：

- Repair phase 產生 top-k patch / plan candidates。
- Selector 對 candidate 進行排序。
- Verifier 對 top candidate 執行 targeted tests。
- 若 top candidate fail，嘗試 top-2 / top-3，直到 budget exhausted。

Acceptance:

- candidate-heavy repair task 會產生多候選 trace。
- selector 選擇與 verifier 結果可被重放。
- budget exhausted 不會被報成成功。

Verification:

- `uv run pytest tests/services/test_s2t_repair_selector.py`
- `uv run pytest tests/integration/test_s2t_repair_loop.py`

## Phase 4: Benchmark Lane

目標：建立 S2T 是否值得啟用的 evidence-grade 評估。

比較組：

- Bare model。
- Nexus current。
- Nexus + S2T Shadow。
- Nexus + S2T Strict。
- Nexus + S2T Repair。

任務集：

- candidate-rich bugfix。
- misleading tests。
- evidence/context 多約束。
- public claim risk。
- route ambiguity。
- long context repair。

Acceptance:

- 報告包含 solve rate、semantic verified、trust mismatch、time-to-verified、cost-per-verified、selector override verified rate。
- public claim 必須走 performance / wearing / capability / cost gates。
- 若 solve-rate 不提升，也必須證明 trust mismatch、cost 或 observability 有改善。

Verification:

- `uv run python scripts/bench/run_s2t_shadow_benchmark.py --profile smoke`
- `uv run python scripts/bench/run_s2t_ab_eval.py --baseline nexus-current --treatment nexus-s2t-strict`

## Phase 5: Agent Lightning Export

目標：把 S2T traces 轉為 Agent Lightning 可吃的 spans / tasks / resources。

實作：

- `scripts/ops/export_s2t_agent_lightning.py`
- 支援 task、rollout、candidate span、verifier span、reward / preference label。
- 匯出前執行 redaction。

資料映射：

| Nexus S2T | Agent Lightning |
| --- | --- |
| task_id | Task |
| candidate set | Rollout / Span group |
| selector score | Span attribute |
| verifier pass/fail | reward / feedback |
| accepted candidate | positive preference |
| rejected top-1 | negative preference |

Acceptance:

- 匯出資料可被 Agent Lightning demo trainer 載入。
- rejected / accepted pair 數量與 source trace 對得上。
- secret scanner 通過。

Verification:

- `uv run pytest tests/ops/test_export_s2t_agent_lightning.py`
- `uv run python scripts/ops/export_s2t_agent_lightning.py --input .nexus/reports/s2t_trace --output .nexus/exports/agent_lightning --dry-run`

## Phase 6: Agent Lightning APO / SFT

目標：先優化 prompt / selector policy，不直接 RL。

實驗：

- selector prompt APO。
- repair prompt APO。
- claim gate prompt APO。
- preference SFT for selector explanation / ranking。

採納門檻：

- 在 held-out S2T tasks 上勝過 rule selector。
- 不增加 trust mismatch。
- 不降低 public claim precision。
- 產物以 versioned resource 引入，不覆寫 default。

Verification:

- `agentlightning` local smoke。
- Nexus held-out benchmark。
- regression: Strict Gate precision 不下降。

## Phase 7: ml-intern Research Automation

目標：讓 ml-intern 自動化 post-training 實驗，但輸出必須回到 Nexus gate。

輸入 brief：

```text
Use Nexus S2T traces to train or improve a selector/reranker.
Do not modify Nexus runtime defaults.
Produce dataset card, training script, eval script, model/prompt artifact, and failure analysis.
Compare against rule selector and prompt selector on held-out Nexus tasks.
```

輸出要求：

- dataset card。
- training script。
- eval script。
- run logs。
- model / prompt artifact。
- failure analysis。
- adoption recommendation。

Acceptance:

- 所有 artifact 可重跑。
- 評估結果可匯入 Nexus benchmark report。
- reward hacking / data leakage 檢查有明確結果。

Verification:

- ml-intern session trace retained privately。
- Nexus benchmark import pass。
- public claim gate 不允許直接引用 ml-intern 自評。

## Phase 8: Adoption Gate

目標：決定訓練成果是否進入 Nexus runtime。

採納候選：

- trained selector。
- optimized selector prompt。
- optimized repair prompt。
- reward model。

採納規則：

- 先 shadow。
- 再 Strict opt-in。
- 最後才可進 Lite / Standard。
- public claim 仍需原 Nexus gate。

拒絕條件：

- held-out regression。
- trust mismatch 上升。
- verifier 被 prompt gaming。
- cost-per-verified 不合理上升。
- 無法重現 ml-intern / Agent Lightning 結果。

## Dependency Graph

```text
S2T contracts
  -> trace writer
  -> shadow recorder
  -> rule selector
  -> strict gate integration
  -> repair candidate integration
  -> benchmark lane
  -> Agent Lightning export
  -> APO / SFT experiments
  -> ml-intern automation
  -> adoption gate
```

## Task Board

### T1: S2T Contracts

Description: Define trace, policy, candidate, verifier, and export data contracts.

Acceptance:

- JSON round-trip tests pass。
- final success cannot be true when verifier failed。
- redaction policy is explicit。

Verification:

- `uv run pytest tests/contracts/test_s2t_contracts.py`

Dependencies: None

Files likely touched:

- `nexus/contracts/s2t_trace.py`
- `nexus/contracts/s2t_policy.py`
- `tests/contracts/test_s2t_contracts.py`

### T2: Trace Writer

Description: Add append-only S2T JSONL writer with artifact refs.

Acceptance:

- append-only behavior。
- stable schema_version。
- invalid path / invalid event fails closed。

Verification:

- `uv run pytest tests/ops/test_s2t_trace_writer.py`

Dependencies: T1

### T3: Rule Selector

Description: Implement explainable rule-based selector as baseline.

Acceptance:

- score components visible。
- verifier-failed candidate cannot win。
- tie triggers second-pass requirement。

Verification:

- `uv run pytest tests/services/test_s2t_selector.py`

Dependencies: T1

### T4: Shadow Recorder

Description: Wire S2T in shadow mode at route / repair / gate boundaries.

Acceptance:

- existing behavior unchanged。
- counterfactual selected candidate recorded。
- eligible task coverage visible。

Verification:

- `uv run pytest tests/services/test_s2t_shadow.py`

Dependencies: T1, T2, T3

### T5: Strict Claim / Delivery Gate

Description: Require selector + verifier evidence for high-risk claim and delivery nodes.

Acceptance:

- missing evidence blocks claim。
- verified candidate passes。
- no verified candidate cannot claim success。

Verification:

- `uv run pytest tests/gates/test_s2t_claim_gate.py tests/gates/test_s2t_delivery_gate.py`

Dependencies: T1-T4

### T6: Repair Candidate Loop

Description: Add top-k repair candidate selection and verifier fallback.

Acceptance:

- top-k candidate trace exists。
- verifier fail tries next candidate within budget。
- budget exhausted fail-closed。

Verification:

- `uv run pytest tests/integration/test_s2t_repair_loop.py`

Dependencies: T1-T5

### T7: Benchmark Smoke

Description: Add smoke benchmark lane for Nexus current vs S2T.

Acceptance:

- report includes selector-specific metrics。
- public claim gate consumes S2T evidence。
- treatment/baseline labels cannot be inverted。

Verification:

- `uv run python scripts/bench/run_s2t_ab_eval.py --profile smoke`

Dependencies: T4-T6

### T8: Agent Lightning Export

Description: Convert S2T traces to Agent Lightning-friendly spans and preference data.

Acceptance:

- accepted / rejected pairs match source trace。
- redaction pass required。
- dry-run summary reports row counts。

Verification:

- `uv run pytest tests/ops/test_export_s2t_agent_lightning.py`

Dependencies: T1, T2, T7

### T9: Agent Lightning APO / SFT Experiment

Description: Run first prompt / selector optimization experiment from exported traces.

Acceptance:

- trained / optimized artifact versioned。
- held-out eval produced。
- no automatic runtime adoption。

Verification:

- Agent Lightning smoke command recorded in experiment report。
- Nexus held-out benchmark pass。

Dependencies: T8

### T10: ml-intern Research Lane

Description: Use ml-intern to automate post-training experiments from S2T dataset.

Acceptance:

- dataset card, training script, eval script, logs, artifact, failure analysis present。
- leakage / reward hacking analysis present。
- Nexus import pass。

Verification:

- ml-intern session trace retained privately。
- Nexus benchmark import pass。

Dependencies: T8, T9

### T11: Adoption Gate

Description: Decide whether optimized selector / prompt enters Nexus runtime.

Acceptance:

- shadow eval passes。
- Strict opt-in passes。
- trust mismatch does not rise。
- public claim precision does not drop。

Verification:

- `uv run python scripts/bench/run_s2t_ab_eval.py --baseline nexus-s2t-rule --treatment nexus-s2t-trained`
- `uv run scripts/ops/ci_gate.py --dry-run`

Dependencies: T7-T10

## Checkpoints

### Checkpoint A: Contracts

- T1-T3 complete。
- Contract tests pass。
- No runtime behavior changed。

### Checkpoint B: Shadow Evidence

- T4 complete。
- At least 30 eligible S2T shadow rows。
- Counterfactual lift report generated。

### Checkpoint C: Strict Runtime

- T5-T6 complete。
- Strict mode improves or preserves semantic verified / trust mismatch。
- Delivery Gate and Claim Gate remain fail-closed。

### Checkpoint D: Training Export

- T8 complete。
- Agent Lightning export dry-run passes。
- Redaction pass blocks unsafe traces。

### Checkpoint E: Training Experiment

- T9-T10 complete。
- Agent Lightning and ml-intern artifacts are reproducible。
- Nexus benchmark decides adoption。

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| selector gaming verifier | High | hidden verifier, held-out eval, public claim split |
| cost / latency growth | Medium | mode tiers, second-pass only on risk threshold |
| trace leaks secrets | High | redaction before export, private datasets by default |
| trained selector overfits benchmark | High | held-out tasks, harder set, no direct adoption |
| ml-intern changes production policy | High | research lane only, adoption gate required |
| shadow data not representative | Medium | collect across repair, route, claim, delivery task types |
| 100% frozen benchmark masks gains | Medium | harder candidate-rich benchmark |

## Open Questions

- S2T candidate generation should start from repair-only or route+repair together?
- Should initial selector use only deterministic rules, or allow LLM judge in shadow mode?
- What is the minimum private trace redaction policy before Agent Lightning export?
- Which model should be first target for selector distillation: Flash, Pro, or a cheap local reranker?

## External References

- Agent Lightning GitHub: https://github.com/microsoft/agent-lightning
- Agent Lightning docs: https://microsoft.github.io/agent-lightning/latest/
- Agent Lightning Microsoft Research page: https://www.microsoft.com/en-us/research/project/agent-lightning/
- ml-intern CLI reference link from Hugging Face trace dataset: https://github.com/huggingface/ml-intern
- ml-intern session trace dataset warning and format: https://huggingface.co/datasets/lewtun/ml-intern-sessions

## Recommendation

Immediate next implementation should be T1-T4 only:

1. S2T contracts。
2. Trace writer。
3. Rule selector。
4. Shadow recorder。

Do not implement Agent Lightning or ml-intern integration until Shadow mode has enough eligible rows to prove that selector decisions are useful.
