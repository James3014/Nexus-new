# Gemini 3 Flash + Nexus 價值比對報告

日期：2026-05-01

## What

本次比對同一個模型、同一組任務：

- Baseline：`gemini-3-flash-preview` bare
- Treatment：`gemini-3-flash-preview` wearing Nexus
- 任務集：`scripts/bench/public_benchmark_nexus_value_v1.json`
- 規模：12 題 x 1 trial
- Hidden verifier：開啟
- Public claim gate：PASS
- Infra invalid：兩邊都是 0

核心結果：

| 指標 | Gemini bare | Gemini + Nexus | 提升 |
| :--- | ---: | ---: | ---: |
| Solve rate | 66.7% | 100.0% | +33.3pp |
| Eligible solve rate | 66.7% | 100.0% | +33.3pp |
| Semantic verified | 66.7% | 100.0% | +33.3pp |
| Trust mismatch | 0.0% | 0.0% | 0.0pp |
| Avg wall time | 32.57s | 49.16s | +16.59s |
| Avg model calls | 1.00 | 1.08 | +0.08 |
| Token measured rate | 100.0% | 100.0% | 0.0pp |

相對提升：

- Solve rate 從 66.7% 到 100.0%，相對提升約 50.0%。
- Verified delivery 從 66.7% 到 100.0%，相對提升約 50.0%。

## Why

這輪測出的 Nexus 價值不是單純「讓模型更會回答」，而是讓同一個 Gemini 3 Flash 進入可驗證、可回溯、可治理的交付模式。

Nexus 的主要價值集中在四類失敗補位：

1. 自癒修復：bare 在兩題 `test_repair` 失敗，Nexus 透過 Hyper / Delivery Gate 路徑補足並通過。
2. 上下文與記憶：bare 在一題 `docs_code_sync` 失敗，缺 `codeintel` 與 `memory`；Nexus 通過。
3. 信任與交付：bare 在一題 `ops_research` 失敗，缺 `claim_gate` 與 `delivery_gate`；Nexus 通過。
4. 路由證據：Nexus 12/12 都有 `route_decision_schema_version=nexus_route_decision_v1`，不是只靠舊 route stack。

代價也必須一起公開：

- Nexus 平均耗時較高：49.16s vs 32.57s。
- Nexus 平均 model calls 稍高：1.08 vs 1.00。
- 因此 Nexus 的產品定位應是高風險任務的可信交付戰甲，而不是所有低風險任務都無差別套最重流程。

## How

本輪使用正式 public-candidate runner，並啟用以下可信度條件：

- 同模型同題 A/B。
- Hidden verifier 開啟。
- Run eligibility schema 開啟，quota/auth/CLI/infra 問題不混入 solve-rate denominator。
- Evidence bundle 開啟。
- Markdown public report 開啟。
- Nexus wearing/context/route evidence 必須完整。
- Per-task stop-loss 600 秒，避免異常長耗時污染結果。

證據檔：

- Markdown report：`.nexus/reports/bench_gemini3flash_value12x1_20260501_route_gate_public/gemini_nexus_report_1777632584.md`
- Evidence bundle：`.nexus/reports/bench_gemini3flash_value12x1_20260501_route_gate_public/evidence_bundle.json`
- With Nexus JSONL：`.nexus/reports/bench_gemini3flash_value12x1_20260501_route_gate_public/with_nexus_1777632584.jsonl`
- Without Nexus JSONL：`.nexus/reports/bench_gemini3flash_value12x1_20260501_route_gate_public/without_nexus_1777632584.jsonl`

Public claim gate checks：

| Gate item | Result |
| :--- | :---: |
| same_model | PASS |
| same_task_trials | PASS |
| hidden_verifier_mode | PASS |
| run_eligibility_complete | PASS |
| trust_mismatch_free | PASS |
| nexus_wearing_valid_rate | 100.0% |
| model_uses_nexus_rate | 100.0% |
| nexus_context_delivered_rate | 100.0% |
| claim_verified_rate | 100.0% |
| route_decision_present_rate | 100.0% |
| artifact_hash_count | 48 |

## Per-Task Result

| Task | Category | Gemini bare | Gemini + Nexus | Nexus 補足能力 |
| :--- | :--- | :---: | :---: | :--- |
| nexus-value-hidden-001 | bugfix | VERIFIED | VERIFIED | Claim / Delivery evidence |
| nexus-value-hidden-002 | bugfix | VERIFIED | VERIFIED | Claim / Delivery evidence |
| nexus-value-repair-001 | test_repair | UNVERIFIED | VERIFIED | Hyper / Delivery Gate |
| nexus-value-repair-002 | test_repair | UNVERIFIED | VERIFIED | Hyper / Delivery Gate |
| nexus-value-gov-001 | refactor | VERIFIED | VERIFIED | MemPalace / Claim Gate |
| nexus-value-gov-002 | refactor | VERIFIED | VERIFIED | MemPalace / Claim Gate |
| nexus-value-evidence-001 | feature | VERIFIED | VERIFIED | Artifact / Claim Gate |
| nexus-value-evidence-002 | feature | VERIFIED | VERIFIED | Artifact / Claim / Delivery Gate |
| nexus-value-context-001 | docs_code_sync | VERIFIED | VERIFIED | CodeIntel / Memory |
| nexus-value-context-002 | docs_code_sync | UNVERIFIED | VERIFIED | CodeIntel / Memory |
| nexus-value-trust-001 | ops_research | VERIFIED | VERIFIED | Artifact / Claim / Delivery Gate |
| nexus-value-trust-002 | ops_research | UNVERIFIED | VERIFIED | Claim / Delivery Gate |

## COE：Bare 失敗題

### nexus-value-repair-001 / nexus-value-repair-002

- What：bare 在 test repair 題失敗，semantic status 為 `UNVERIFIED`。
- Why：缺 `hyper` 與 `delivery_gate`，模型直接修復後沒有足夠的交付驗證閉環。
- How：Nexus wearing 版本 2 題皆 `VERIFIED`，透過 Hyper 路由與 Delivery Gate 把修復結果收斂成可驗證交付。

### nexus-value-context-002

- What：bare 在 docs/code sync 題失敗，semantic status 為 `UNVERIFIED`。
- Why：缺 `codeintel` 與 `memory`，代表模型沒有足夠的程式碼影響範圍與既有上下文。
- How：Nexus wearing 版本 `VERIFIED`，CodeIntel / Memory 提供上下文與變更約束。

### nexus-value-trust-002

- What：bare 在 ops/research 信任題失敗，semantic status 為 `UNVERIFIED`。
- Why：缺 `claim_gate` 與 `delivery_gate`，結果無法形成可信交付。
- How：Nexus wearing 版本 `VERIFIED`，Claim Gate / Delivery Gate 補上可審計的驗收鏈。

## Public Claim Boundary

可說：

- 在這個固定 12 題 hidden-verifier benchmark 上，同一個 `gemini-3-flash-preview` 穿 Nexus 後，eligible solve rate 從 66.7% 提升到 100.0%，絕對提升 +33.3 percentage points。
- Nexus wearing evidence 12/12 有效，Gemini uses Nexus rate 100%，Nexus context delivered rate 100%，claim verified rate 100%。
- 這輪 public claim gate PASS，token measured rate 兩邊都是 100%。
- Nexus 的主要價值是 verified delivery、上下文/記憶注入、自癒修復與 fail-closed 交付治理。

不可過度宣稱：

- 這還不是多模型、多 trial 的最終公開總報告。
- 不可宣稱 Nexus 對所有任務都更快；本輪 Nexus 平均 wall time 較高。
- 不可宣稱 Swarm / Drone / Nightshift 的收益，因為本輪它們沒有真實觸發。
- `gemini-3.1-pro-preview` 尚未納入本報告；該模型 benchmark 需要再次確認外部 Gemini 傳輸本機 benchmark prompt/task data 的授權。

## Lesson

- Nexus 的主指標應是 verified delivery，而不是只看可見測試或模型自稱成功。
- 公開報告必須保留 public claim gate、evidence bundle、route decision evidence 與 eligibility schema。
- 低風險任務需要 light route 控制成本；高風險任務才應啟用完整 Nexus 治理。
- 下次跨模型比較前，必須先明確確認外部模型資料傳輸授權，避免 benchmark 因合規審核中斷。

## Repeat Observation：12 題 x 2 Trials

同日又補跑一次 `12 題 x 2 trials` repeat，用來觀察穩定性。這一輪不作 public PASS claim，因為 bare arm 有 1 筆 `timeout_before_model_call`，導致 evidence bundle 的 public claim gate 為 `FAIL`，原因是 `run_eligibility_incomplete`。

觀察數據：

| 指標 | Gemini bare | Gemini + Nexus | 備註 |
| :--- | ---: | ---: | :--- |
| Rows | 24 | 24 | 12 題 x 2 trials |
| Eligible rows | 23 | 24 | bare 有 1 筆 infra invalid |
| Infra invalid | 1 | 0 | `timeout_before_model_call` |
| Eligible verified | 14/23 | 24/24 | 不作 public PASS claim |
| Eligible solve rate | 60.9% | 100.0% | 觀察性 +39.1pp |
| Trust mismatch | 0.0% | 0.0% | 兩邊皆 0 |
| Avg wall time | 37.19s | 60.92s | Nexus 較慢 |
| Avg model calls | 0.96 | 1.08 | bare 受 infra invalid 影響 |
| Token measured rate | 95.8% | 100.0% | bare 受 infra invalid 影響 |

Repeat 類別觀察：

| Category | Gemini bare | Gemini + Nexus | 解讀 |
| :--- | :---: | :---: | :--- |
| `bugfix` | 4/4 | 4/4 | 兩邊都穩定 |
| `refactor` | 4/4 | 4/4 | 兩邊都穩定 |
| `feature` | 4/4 | 4/4 | 兩邊都穩定 |
| `test_repair` | 0/4 | 4/4 | Nexus 自癒/Hyper/Delivery Gate 價值穩定重現 |
| `docs_code_sync` | 0/3 eligible | 4/4 | CodeIntel / Memory 類缺口穩定重現；另有 1 筆 bare infra invalid |
| `ops_research` | 2/4 | 4/4 | Claim Gate / Delivery Gate 對信任題有穩定補位 |

Report Trust lesson：

- 這輪先發現 markdown report 與 evidence bundle gate 不一致：bundle 正確標 `FAIL`，markdown 曾誤報 `PASS`。
- 已修正 `scripts/bench/gemini_nexus_report.py`，讓 markdown public gate 也在任一 arm 有 infra-invalid row 時 fail closed。
- Regression：`uv run pytest -q tests/benchmark/test_gemini_nexus_report.py tests/benchmark/test_capability_ab_runner.py -k 'public_claim_gate or markdown_report or evidence_bundle'`，結果 `25 passed`。

Repeat 證據檔：

- Markdown report：`.nexus/reports/bench_gemini3flash_value12x2_20260501_route_gate_public/gemini_nexus_report_1777635318.md`
- Evidence bundle：`.nexus/reports/bench_gemini3flash_value12x2_20260501_route_gate_public/evidence_bundle.json`
- With Nexus JSONL：`.nexus/reports/bench_gemini3flash_value12x2_20260501_route_gate_public/with_nexus_1777635318.jsonl`
- Without Nexus JSONL：`.nexus/reports/bench_gemini3flash_value12x2_20260501_route_gate_public/without_nexus_1777635318.jsonl`

## Gemini 3.1 Pro Status

本輪曾準備跑 `gemini-3.1-pro-preview` 同規格 12 題，但執行被安全審核拒絕：該 benchmark 會把本機 benchmark prompt/task data 傳給外部 Gemini 3.1 Pro，而目前 tenant policy 禁止這類外部 disclosure。此模型暫不納入 2026-05-01 報告。
