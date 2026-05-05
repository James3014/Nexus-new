# Gemini 3 Flash + Nexus P16/P17 Benchmark Report

## [任務]
- 範圍：Gemini 3 Flash Preview，公開候選 A/B，12 tasks x 2 trials。
- 目的：先跑 Flash，不跑 Pro；驗證 Nexus 新路由是否能依情境選擇並使用能力，並完成 P17 route-quality 判讀。
- 結論：能力提升成立，但公開宣稱尚未通過。主要缺口不是 solve，而是路由選擇過寬，導致 P17 route-quality hard gate fail。

## [數據]

### A/B 結果
| 指標 | Bare Flash | Flash + Nexus | Delta |
| --- | ---: | ---: | ---: |
| Rows | 24 | 24 | n/a |
| Usable rows | 22/24 | 24/24 | +2 usable |
| Infra invalid rows | 2 | 0 | -2 |
| Raw solve rate | 50.0% | 100.0% | +50.0pp |
| Eligible solve rate | 54.5% | 100.0% | +45.5pp |
| Semantic verified | 50.0% | 100.0% | +50.0pp |
| Trust mismatch | 0.0% | 0.0% | 0.0pp |
| Avg wall time | 55.08s | 129.20s | +74.13s |
| Avg model calls | 0.92 | 1.00 | +0.08 |
| Token measured rate | 91.7% | 87.5% | -4.2pp |
| Local rescue rate | 0.0% | 16.7% | +16.7pp |

### P17 Route Quality
| 指標 | Bare Flash | Flash + Nexus | 判讀 |
| --- | ---: | ---: | --- |
| Selected -> Invoked | 0.0% | 48.2% | 未達 promotion 門檻 70% |
| Invoked -> Evidence | 0.0% | 100.0% | 達標 |
| Evidence -> Outcome | 0.0% | 100.0% | 達標 |
| Unnecessary Selected | 0.0% | 51.8% | 未達 promotion 門檻 <= 30% |
| Research evidence present | 0.0% | 100.0% | 達標 |
| Research gate passed | 0.0% | 100.0% | 達標 |
| Research preflight present | 0.0% | 0.0% | 缺 preflight decision evidence |
| Session ledger logged | 0.0% | 0.0% | 缺 research session packet audit trail |

### 能力調度判讀
- 已正確成為 public-safe 且全程 selected/invoked/evidence/gate/outcome：`artifact_gate`, `belief`, `claim_gate`, `codeintel`, `delivery_gate`, `memory`, `mempalace_gate`, `research`。
- `hyper`：20/24 selected/invoked/evidenced/gated/outcome，路由能依部分情境啟動。
- 過度選擇來源：`acceptance_check`, `autoreason`, `learn_mode`, `learn_phase_slo`, `plan_quality_gate`, `pregate`, `research_route`, `sandbox`, `ultra_review` 全部 24/24 selected-only。
- 條件式 selected-only：`ddtree` 4/24, `direct_mode` 4/24, `repair_loop` 4/24。
- `ultra_review`：24/24 selected，但 feature flag disabled，不能當作已執行能力宣稱。
- `autoreason`：24/24 selected，但 0/24 invoked/evidence/gate，是 capability-specific gate failure 主因。

### Gate 結果
| Gate | 結果 | 原因 |
| --- | --- | --- |
| Performance claim gate | PASS | solve / verified lift 明確 |
| Wearing claim gate | PASS | Nexus usage valid 100%，phase completion 100%，claim verified 100% |
| Cost claim gate | PASS | token public-safe claim YES |
| Capability-specific claim gate | FAIL | `autoreason:invoked+evidence+gate` 未成立 |
| Per-capability public gate | FAIL | 只有 `codeintel` 被列為 per-capability public-safe |
| Public claim gate | FAIL | route-quality 與 eligibility 未達公開宣稱要求 |

## [證據]
- benchmark output dir：`/Users/jameschen/Workspace/nexus/.nexus/reports/bench_gemini3flash_value12x2_20260505_p16`
- generated markdown：`/Users/jameschen/Workspace/nexus/.nexus/reports/bench_gemini3flash_value12x2_20260505_p16/gemini_nexus_report_1777948126.md`
- with Nexus JSONL：`/Users/jameschen/Workspace/nexus/.nexus/reports/bench_gemini3flash_value12x2_20260505_p16/with_nexus_1777948126.jsonl`
- without Nexus JSONL：`/Users/jameschen/Workspace/nexus/.nexus/reports/bench_gemini3flash_value12x2_20260505_p16/without_nexus_1777948126.jsonl`
- evidence bundle：`/Users/jameschen/Workspace/nexus/.nexus/reports/bench_gemini3flash_value12x2_20260505_p16/evidence_bundle.json`
- executed command：

```bash
NEXUS_VALUE_HIDDEN_VERIFIER=1 \
NEXUS_GEMINI_MODEL_NAME=gemini-3-flash-preview \
NEXUS_DIRECT_GEMINI_MODEL=gemini-3-flash-preview \
NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin \
NEXUS_GATEWAY_COMPACT_PROMPT=1 \
NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1 \
NEXUS_BENCH_GATEWAY_TIMEOUT_SEC=300 \
uv run python scripts/bench/capability_ab_runner.py \
  --tasks-file scripts/bench/public_benchmark_nexus_value_v1.json \
  --output-dir .nexus/reports/bench_gemini3flash_value12x2_20260505_p16 \
  --max-tasks 12 --repeat-trials 2 --timeout-sec 420 \
  --total-timeout-sec 7200 --stop-loss-sec 7200 --per-task-stop-loss-sec 600 \
  --difficulty all --repo-kind-filter all --force-flow hyper_sprint \
  --with-nexus-runner subprocess --with-llm-mode all --without-mode gemini \
  --force-learn-slo-ready --neutralize-history --disable-learning-loop \
  --materialize-missing --isolation-mode preserve_target \
  --evidence-bundle --markdown-report auto --progress-log
```

## [殘債]
- P17 未完成到可公開宣稱：`selected->invoked` 只有 48.2%，`unnecessary_selected` 仍 51.8%。
- `autoreason` 必須從 selected-only 改成條件式 invoked/evidenced/gated，或從公開路由 selected 集合移除。
- `ultra_review` feature-flag-disabled 時不能被選入 public claim path。
- `research_route`, `pregate`, `sandbox`, `learn_*`, `plan_quality_gate`, `acceptance_check` 應拆成 internal markers，不應污染 public route-quality funnel。
- Research 還缺 preflight decision 與 session ledger evidence，否則只能宣稱 research evidence/gate，不能宣稱完整 research workflow。

## [下一步]
- P17.1：把 selected-only marker 與 executable capability 拆開，Route Quality 只計 executable/public-safe candidates。
- P17.2：新增 `route_selected_reason`, `route_invocation_policy`, `skip_reason`，讓未 invoke 的能力有可審核跳過原因。
- P17.3：修 `autoreason`：只在多候選/修補/不確定任務被 selected；selected 後必須產出 judge evidence 或明確 skip receipt。
- P17.4：修 `ultra_review`：feature disabled 時只能記 recommendation，不得進 selected funnel。
- P17.5：補 research preflight + session ledger receipts。
- P17.6：重跑 Flash 12x2，promotion targets：selected->invoked >= 70%，invoked->evidence >= 95%，evidence->outcome >= 90%，unnecessary_selected <= 30%。
