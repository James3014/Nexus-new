# Gemini 3 Flash + Nexus RLM Public Candidate Report

日期：2026-04-28

## 結論

這輪測試使用同一個模型 `gemini-3-flash-preview`，比較裸跑 Gemini 與「穿 Nexus」的 Gemini。結果顯示，Nexus 的主要價值不是讓模型變成另一個 agent，而是把同一個模型放進可驗證的工程交付框架中：治理邊界、證據驗收、Belief/Memory 決策、RLM trace、自我修復與 public claim gate。

在 8 題、2 trials 的 hidden-verifier benchmark 中：

| 指標 | Gemini bare | Gemini + Nexus | 差異 |
| --- | ---: | ---: | ---: |
| Solve rate | 37.5% | 100.0% | +62.5 pp |
| Eligible solve rate | 42.9% | 100.0% | +57.1 pp |
| Semantic verified | 37.5% | 100.0% | +62.5 pp |
| Trust mismatch | 0.0% | 0.0% | 0.0 pp |
| Avg wall time | 45.51s | 70.43s | +24.92s |
| Avg model calls | 0.94 | 1.62 | +0.68 |
| Token measured rate | 87.5% | 100.0% | +12.5 pp |
| Tokens / verified success | 97,534 | 44,623 | -54.2% |
| Model calls / verified success | 2.33 | 1.62 | -30.5% |

Public claim gate：PASS。

## Nexus 提升了什麼

1. 治理邊界：MemPalace / governance 題 bare 多次把 read-only、delete、unsafe operation 的邊界修錯；Nexus 2 題 x 2 trials 全部 VERIFIED。
2. 證據驗收：Artifact / Claim 題 bare 會接受缺 artifact 或錯誤 replay 欄位；Nexus 強制 claim 必須有可驗證 evidence。
3. Belief / Memory：bare 在低信心高風險 budget 與 prior-fix relevance 題上不穩；Nexus 把「何時保守、何時加證據」變成可測 contract。
4. RLM / self-heal：Nexus 16/16 都有 RLM trace，LLM self-heal active rate 62.5%，把失敗修補過程留下可審計軌跡。
5. 交付可信度：Nexus formal wearing valid 16/16，phase completion 16/16，claim verified 16/16。

## 成本與限制

這輪不是單純「更快」。Nexus 平均 wall time 較高，因為它多做治理、驗證與修復。但以 verified delivery 來看，Nexus 的每個成功交付 token 成本更低，因為 bare 花了不少 token 與時間仍未通過 hidden verifier。

因此公開說法應避免只說「Nexus 更快」。更準確的說法是：

> 在此固定 benchmark 上，Nexus 用較重的治理流程換來 100% verified delivery，且每個 verified success 的 token 與 model-call 成本低於裸跑 Gemini。

限制：

- 樣本仍是 8 題 x 2 trials，屬 public candidate，不是跨領域 production generalization。
- Bare 有 2 筆 infra invalid（parse_error、quota_exhausted），已從 eligible denominator 排除。
- 本輪 generated report 產生時 Swarm 欄位仍是舊邏輯，會高估為 100%；P23 已改成 evidence-backed Swarm，後續重跑才可宣稱 Swarm 使用率。
- Drone 目前仍需 public fixture 驗證；Nightshift 已拆出 recommended / invoked / recovered 欄位，後續需用專門題型補真實觸發。

## 自我更新 Meta-Framework 狀態

Nexus 目前已具備「會自我測試與自我優化」的核心骨架：

- A/B lab：同模型 bare vs Nexus 可重跑。
- Hidden verifier：不讓模型自評成功。
- Public claim gate：不能公開宣稱的 run 會被擋下。
- Evidence bundle：每筆 row 有 raw evidence、diff、trace。
- Failure-to-fix loop：本輪先發現 belief/scope 弱點，再補 contract，重跑後 Nexus 達到 16/16。

但它還沒有完全達成「自動移除或降級規則」：

- 尚未有 rule lifecycle：active / light / deprecated / removed_candidate。
- 尚未有週期化 eval catalog 判斷哪些能力已被新模型內化。
- 尚未有 cost-aware demotion gate，把太重但低收益的治理改成 light Nexus。

這會進入 P29。

## 後續 P22-P29

P22：公開報告可信化。補 P50/P95 wall time、tokens per verified success、model calls per verified success、phase wall-time share、runner command/env/git/model lock。

P23：MSA 真實觸發。修正 Swarm 過寬標記，將 Nightshift 拆成 recommended/invoked/recovered，新增 Drone/Nightshift public fixtures。

P24：Evidence bundle v2。加入 claim index、public gate failures、manifest SHA、git commit、timeout policy、model lock。

P25：降摩擦路由。低風險任務走 light Nexus，高風險才啟用 full Nexus/RLM/self-heal。

P26：治理審計回復硬化。缺 evidence、scope 漂移、低信心高風險不得默默通過。

P27：Benchmark skill。把 Gemini vs Gemini+Nexus 固定流程包成 skill，每次優化前後都能比較。

P28：RLM 內化。把 trace/budget/submit semantics 接入 R/X phase，讓內迴圈服從 MemPalace、Belief、CapabilityGate。

P29：自我更新框架。建立 rule lifecycle 與週期化 eval catalog，自動判斷哪些 Nexus 規則被模型內化、哪些仍保留、哪些需要降摩擦。

## Evidence

- Generated report: `.nexus/reports/bench_gemini3flash_rlm_v2_8task_2trials_public_candidate/gemini_nexus_report_1777358295.md`
- With Nexus rows: `.nexus/reports/bench_gemini3flash_rlm_v2_8task_2trials_public_candidate/with_nexus_1777358295.jsonl`
- Without Nexus rows: `.nexus/reports/bench_gemini3flash_rlm_v2_8task_2trials_public_candidate/without_nexus_1777358295.jsonl`
- Evidence bundle: `.nexus/reports/bench_gemini3flash_rlm_v2_8task_2trials_public_candidate/evidence_bundle.json`

## Lessons

- Bare/direct Gemini 必須有 hard timeout，否則單題可能拖到 900s 以上，污染 benchmark wall time。
- Per-task stop-loss 不應終止整批 benchmark；它應只把該 row 標成 infra invalid，讓 public claim gate 可以看到完整 task/trial matrix。
- Public report 不能只看 solve rate；要以 verified delivery、trust mismatch、tokens per verified success、model calls per verified success 一起判斷 Nexus 價值。
