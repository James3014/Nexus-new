# Skills Auto-Tune 研究入口（Nexus）

## 目的
把 `SkillsRouter` 的歷史決策紀錄，轉成可重跑的權重調整流程，讓 skill 選擇逐步貼近真實任務結果。

## 指令
先看建議（不改檔）：

```bash
python3 scripts/engine/nexus_cli.py nexus:skills-autotune
```

正式套用：

```bash
python3 scripts/engine/nexus_cli.py nexus:skills-autotune --apply
```

## 主要輸出
- 報告：`.nexus/metrics/skills_autotune_report.json`
- 權重（套用時）：`scripts/core/autonomic_weights.json`

## 參數
- `--min-samples`：最少樣本數（預設 `3`）
- `--baseline`：基準 outcome（預設 `0.55`）
- `--learning-rate`：調整速度（預設 `0.6`）

## 目前模型（v1）
- 輸入：`router_decisions.jsonl`（含 selected skill、score、phase）
- outcome proxy：
  - phase health（若可取得）+ route score 信心
  - 組合為 `proxy_outcome`
- 更新：對 `skill_adjustments[skill_id]` 做阻尼增減，限制在 `[-3, 8]`

## 注意
這是研究入口，不是最終強監督版。若要升級成生產閉環，下一步要把「任務結果真值」直接對齊到每次 skill 選擇。
