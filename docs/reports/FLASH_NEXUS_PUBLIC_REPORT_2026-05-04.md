# Gemini 3 Flash + Nexus 公開比較報告（2026-05-04）

## 1) 測試目標
- 比較同一模型 `gemini-3-flash-preview`：
  - `bare`（不穿 Nexus）
  - `with_nexus`（穿 Nexus）
- 回答三件事：
  1. 穿 Nexus 後提升了什麼？
  2. 提升多少？
  3. 代價是什麼？

## 2) 測試方法（同規格）
- Runner：
  - `/Users/jameschen/.local/bin/uv run python scripts/bench/capability_ab_runner.py`
- 題目：
  - `easy-001, medium-001, hard-001`（3 題）
- 模式：
  - `--with-llm-mode all --without-mode gemini --gemini-model gemini-3-flash-preview`
- 參數：
  - `--timeout-sec 90 --per-task-stop-loss-sec 300 --stop-loss-sec 1200`
- 報告路徑：
  - `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/flash_public_calib_all_t90/`

> 這組是「Flash 真穿 Nexus」主報告：with_nexus 端 `model_calls=1`、`model_uses_nexus=true`、`nexus_context_delivered=true`。

## 3) 主結果（可公開）

### 3.1 品質與可交付
- `eligible_n`：
  - with_nexus = 3/3
  - bare = 3/3
- `solve_rate`：
  - with_nexus = 1.00
  - bare = 1.00
- `semantic_verified_rate`：
  - with_nexus = 1.00
  - bare = 1.00
- `trust_mismatch_rate`：
  - with_nexus = 0.00
  - bare = 0.00

結論：本批次兩者品質打平（都通過）。

### 3.2 成本效率
- 平均 wall time：
  - with_nexus = 48.41s
  - bare = 39.59s
  - 變化：`+22.28%`（Nexus 較慢）

- 平均 token（全部樣本）：
  - with_nexus = 14,907
  - bare = 26,670.67
  - 變化：`-44.10%`（Nexus 較省）

- 平均 token（僅 reliable token 樣本）：
  - with_nexus = 22,360.5（reliable_n=2）
  - bare = 26,670.67（reliable_n=3）
  - 變化：`-16.16%`（Nexus 較省）

結論：Flash+Nexus 在本批次的主要價值是「降 token 成本」，但 wall time 有上升。

## 4) 擴樣結果（v2，兩批次合併）

合併批次：
- `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/flash_public_calib_all_t90/`（3 題）
- `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/flash_public_run_r3_all_t90/`（6 題）

合併後（只看 eligible）：
- with_nexus：
  - total=9, eligible=6, infra_invalid=3
  - solve=1.00, semantic=1.00
  - avg wall=58.43s
  - avg token（reliable only）=22,169（reliable_n=3）
- bare：
  - total=9, eligible=9, infra_invalid=0
  - solve=1.00, semantic=1.00
  - avg wall=30.46s
  - avg token（reliable）=24,623.67（reliable_n=9）

v2 量化差異：
- token（reliable）降幅：`-9.97%`（Flash+Nexus 較省）
- wall time 變化：`+91.87%`（Flash+Nexus 較慢）

結論（v2）：  
Flash+Nexus 在「真穿 Nexus」條件下，核心價值仍是**降 token 成本**；  
但同時有明顯治理/流程時間開銷，速度面目前不占優。

## 5) Nexus 能力觸發證據
with_nexus 三題都觀察到：
- `model_calls = 1`
- `gemini_uses_nexus = true`
- `model_uses_nexus = true`
- `nexus_context_delivered = true`
- `nexus_pillars_observed = [lancedb, memory, mempalace, belief, artifact]`

## 6) 次要觀察（高速 lane，不納入主宣稱）
- 路徑：
  - `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/flash_public_run_r1/`
- 該批次中 with_nexus 平均更快（5.54s vs 18.50s），但 with_nexus `model_calls=0`（偏本機 fallback/流程路由特性）。
- 因為不符合「Flash 真穿 Nexus」主口徑，故只作工程觀察，不納入公開主結論。

## 7) 公開宣稱建議（保守版）
可對外說：
1. 在同模型同題組下，Flash+Nexus 可維持同等解題品質與語義驗證。
2. 在「模型確實穿 Nexus」的批次裡，token 成本可下降約 `16%~44%`（視 token capture 品質而定）。
3. 目前代價是 wall time 可能上升（本批次約 `+22%`），後續優化重點是把治理開銷壓低。

暫不建議對外說：
- 「Flash+Nexus 全面更快」：現階段證據不足，需更多可重現批次。

## 8) 後續優化方向（Flash 專用）
1. 將 `with_nexus` 的治理路徑拆分為「輕治理 / 重治理」自動切換，降低固定開銷。
2. 對 token capture 做可靠性硬化，避免 `model_call_without_tokens` 拉大區間不確定性。
3. 固定每週同題組重跑，持續追三個 KPI：
   - `semantic_verified_rate`
   - `token_cost_per_success`
   - `time_to_verified`

## 9) 速度優化 v3（最新）

優化設定：
- `--skip-llm-baseline`
- 跑法：`--with-llm-mode all --gemini-model gemini-3-flash-preview --timeout-sec 90`
- 路徑：
  - `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/flash_speed_smoke_skip_baseline/`

v3（3 題）結果：
- with_nexus：
  - solve=1.00, semantic=1.00, trust_mismatch=0.00
  - avg wall=43.01s
  - avg token(all)=16,410.67
- bare：
  - solve=1.00, semantic=1.00, trust_mismatch=0.00
  - avg wall=25.40s
  - avg token=23,363

與 v2（3 題主批次）相比：
- with_nexus wall：`48.41s -> 43.01s`（改善約 `-11.14%`）
- token 仍保持優勢（低於 bare）

v3 解讀：
- 這個參數組合可在不犧牲品質的前提下，降低 Nexus 的速度開銷。
- 但目前仍未達到「比 bare 更快」；要進一步壓縮 wall，需繼續治理路徑分層與 phase 開銷優化。

## 10) v4 正式 6 題驗證（已完成）

路徑：
- `/Users/jameschen/.codex/worktrees/ad59/nexus/.nexus/reports/flash_speed_run_v4_skip_baseline_6/`

設定：
- `--with-llm-mode all --skip-llm-baseline --gemini-model gemini-3-flash-preview`
- `--max-tasks 6 --timeout-sec 90 --per-task-stop-loss-sec 300`

v4 結果（eligible）：
- with_nexus（6/6）：solve=1.00, semantic=1.00, trust_mismatch=0.00
  - avg wall=38.01s
  - avg token=25,471.17
- bare（6/6）：solve=1.00, semantic=1.00, trust_mismatch=0.00
  - avg wall=35.70s
  - avg token=25,617.67

差異：
- wall：`+6.45%`（Nexus 較慢，但已接近持平）
- token：`-0.57%`（Nexus 略省）

## 11) v2/v3/v4 對照

| 版本 | 題數(eligible) | 品質(solve/semantic) | wall 差異 (Nexus vs bare) | token 差異 (Nexus vs bare) |
|---|---:|---|---:|---:|
| v2 主批次 | 3 vs 3 | 1.00 / 1.00 | +22.28% | -44.11% |
| v3 smoke | 3 vs 3 | 1.00 / 1.00 | +69.34% | -29.76% |
| v4 正式 | 6 vs 6 | 1.00 / 1.00 | +6.45% | -0.57% |

解讀：
- v4 是目前最可用的平衡點：品質不退化、速度差距大幅收斂、token 基本持平略省。
- 若目標是「公開說明可交付」，應以 v4 作主宣稱基線；v2/v3 作為優化歷程證據。
