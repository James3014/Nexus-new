# 2026-03-17 Nexus 10-Case Benchmark 比較分析

## 本次實跑
指令：
```bash
/Users/jameschen/.local/bin/uv run scripts/nexus_cli.py nexus:benchmark --framework truth-audit --tasks 10 --output nexus_benchmark_20260317_2.csv --model codex --target nexus
```

輸出檔：`/Users/jameschen/Downloads/Muse-Nexus/nexus_benchmark_20260317_2.csv`

## 核心成績（本次）
- 任務數：10
- 成功率：100% (10/10 PASS)
- 平均 tokens：0.0
- 非零 token 任務：0/10
- 平均耗時：3.859s
- P95 耗時：4.4s
- 平均健康度：100.0
- 最大漂移：0.0
- Phase path：全部 `P -> D -> R -> A -> C`
- review_status：`APPROVED` 5、`UNKNOWN` 5

## 與前次（ci_benchmark.csv）比較
- 成功率：持平（100% -> 100%）
- 平均 tokens：持平（0.0 -> 0.0）
- 非零 token 任務：持平（0 -> 0）
- 平均耗時：小幅進步（3.991s -> 3.859s）
- 健康/漂移：持平（100.0 / 0.0）

## 優勢
1. 穩定性高：10/10 全 PASS，無漂移。
2. 速度快：平均 < 4s，P95 4.4s。
3. 流程一致：phase path 全一致，治理路徑穩定。

## 短板
1. **TRU-101 仍是主短板**：benchmark 全部 token=0，無法做成本對標。
2. review_status 有 50% 為 `UNKNOWN`，審核結果訊號不夠穩定。
3. phase path 全部不含 X，導致 token 主要來源無法在 benchmark 鏈路顯示。

## 關鍵判讀
- 目前系統在「治理穩定性」已達高分。
- 但在「成本可觀測性（tokens）」仍不足，導致外部可比性受限。
- 已知同日單跑 `TOKEN-CHECK` 可抓到 `total_tokens=1327`，代表解析器非失效，問題在 benchmark 情境未觸發可計費來源或未回傳 usage。

## 下一步（優先順序）
1. 在 benchmark 至少保留 2~3 個強制 X-phase case，驗證非零 token。
2. 在 `coordinator.run_benchmark` 增加 `token_source` 欄位（X/R/A）與 `token_capture_status`。
3. 將 `review_status=UNKNOWN` 視為警示並在 CI gate 增加比例閾值（例如 UNKNOWN <= 20%）。

## 當前總評
- 治理成績：A-
- 對外競技成績：B（受 token 可觀測性限制）
