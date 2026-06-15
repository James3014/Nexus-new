# Nexus Local Collaboration Roadmap v3 (Stable)

## 📌 核心原則 (Core Principles)
* **不改 L0 authority**：Runtime 治理與防禦為唯一主權，絕不交給任何模型。
* **保留 1.5B，但降級為 Optional**：作為非阻塞式前門篩選器。
* **以 3B shadow/advisor 為已證明主線**：3B 是目前最成熟、最接近 limited assist 的模型位。
* **7B/14B 只進 Experimental Deliberation Lane**：專注於高難度推理，不碰觸權威決策。
* **強制合約保護**：所有 adoption 都必須走 feature flag、fallback、per-row evidence、rollback drill。

---

## 🏗️ 架構分層 (Architecture Layers)

* **L0 Runtime Governance**: Rust/Python fail-closed runtime，持有 verifier、claim gate、delivery gate、policy boundary、authorization；這層是唯一 authority，不交給任何模型。
* **L1 Optional Front-Door Gatekeeper**: 1.5B 或 rule/proxy gate，只能輸出 `need_3b`, `need_deliberation`, `risk_tier`, `phase_hint`, `confidence_band`, `abstain_reason` 之類 hint，不得直接裁決。
* **L2 3B Shadow Advisor**: S2T selector/reranker advisor，維持 shadow-first / evidence-first；它是本 roadmap 目前最成熟、最接近 limited assist 的模型位。
* **L3 7B Worker Lane**: 負責候選生成、search/localize/repair 類 reasoning worker。
* **L4 14B Judge/Synthesizer**: 負責 synthesis、route-review、repair-review、research brief；仍無 authority，不碰 verifier/claim gate 主權。

---

## 🚀 執行階段 (Phases)

### Phase 0：Runtime Fitness Baseline
**目的**：先把本地模型協作的物理成本量清楚，不靠感覺。
**任務**：
* 固化 telemetry：cold-start latency, model load time, TTFT, steady-state TPS, e2e latency, thought/answer token ratio。
* 對 3B、7B、14B 分別建立 short / medium / long workload profile。
* 讓 `e2e_latency_delta`, `short_task_penalty_rate` 進正式 evidence row。
**驗收**：
* 每種模型至少有一份 baseline runtime report。
* 短任務與長任務的代價差異可量化。

### Phase 1：Rust 與 Policy 對齊
**目的**：先補齊 authority 底座，避免後面模型協作建立在半空中。
**任務**：
* 補 `receipt_verifier`, `flow_machine` 的單元與邊界測試。
* 建完整 rollback drill matrix。
* 將 policy-baseline-manifest 的 commit, schema version, test entry point, rollback status 封板。
**驗收**：
* Rust readiness matrix 裡 compile / unit / IPC / dual-run / mismatch / rollback 都有證據。
* 沒有任何模組只憑 smoke 就被寫成 sealed。

### Phase 2：3B 主線收斂
**目的**：把已經跑通的 3B shadow 路線正式定稿。
**任務**：
* 維持 S2T structured selector decisions，不用 hidden CoT。
* 固化 dataset card, redaction, held-out split。
* 固化 adoption gate 指標：`selector_override_verified_rate`, `trust_mismatch_rate`, `abstain_rate`, `cost_per_verified_task`, `public_claim_precision`。
* 完成 `READY_FOR_REVIEW` 所需 dossier 與 limited mount 邊界說明。
**驗收**：
* $\ge 30$ eligible shadow rows。
* held-out tasks 上 beat rule selector。
* trust mismatch 不增加，public-claim precision 不下降。

### Phase 3：Optional 1.5B Gatekeeper
**目的**：證明它能不能幫系統省成本，而非僅證明其聰明程度。
**定位**：Optional，非 blocker。可用真 1.5B，也可先用 rule/3B proxy stub 驗證 schema。
**任務**：
* 只輸出 gatekeeper v2 schema hints。
* 驗證它是否能降低 7B/14B 誤觸發率。
* 驗證 short tasks 的平均 E2E latency 是否真的下降。
**驗收**：
* 若整體 short/medium workload 的成本與 latency 明顯改善，才保留。
* 若無改善，直接退回 rule/proxy，不影響主線。

### Phase 4：7B/14B Deliberation Lane
**目的**：把 Fusion 式多模型協作做成 Nexus 受控車道。
**任務**：
* 建立 `LocalDeliberationLane`。
* 7B 生成主候選；14B 做 synthesis / route-review / repair-review。
* 輸出 deliberation fitness 指標。
**驗收**：
* 只在 high-uncertainty / high-value / research / repair-review tasks 上啟動。
* 不得碰 verifier, claim gate, delivery gate, default router replacement。

### Phase 5：Experimental Shadow Gate
**目的**：把所有新模型 / 新 serving 框架鎖在 shadow lane。
**任務**：
* 實作 `ExperimentalArchitectureGate`。
* 建立 maturity checklist。
* 每條實驗線都要求 rollback path, token budget, runtime fitness report。
**驗收**：
* 未過 maturity checklist 的模型不得進 main path。
* 新 serving 只能 shadow-first。

### Phase 6：Limited Assisted Adoption
**目的**：只在低風險、可回滾條件下做受限上線。
**任務**：
* 3B 申請 selector/reranker assist。
* 7B 申請 route-review assist。
* 14B 申請 synthesis assist。
* 必須受限於 feature flag, fallback to Python/rule path, per-row evidence, rollback drill 保護。
**驗收**：
* Allowed first mount 只限 strict-gated repair 或 route-review nodes。
* 不允許 default router replacement, verifier replacement, public claim gate replacement, policy auto-mutation。

---

## 🛑 絕對紅線 (What NOT to do)
* **不能** 讓任何模型變成 L0 authority。
* **不能** 把 1.5B、3B、7B、14B 任何一個寫成 verifier / claim gate / delivery gate 替代者。
* **不能** 因為 local collaboration 跑出漂亮結果，就直接改 runtime default。
* **不能** 沒有 feature flag、fallback、rollback drill 就做 limited adoption。
