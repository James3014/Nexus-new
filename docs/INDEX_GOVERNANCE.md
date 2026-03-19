# Nexus Governance & Rules

## Token 口徑（唯一判定規則）
1. 每輪 benchmark 必須記錄 `total_raw_tokens`。
2. 若 `total_raw_tokens > 0`：該輪模式標記 `RAW_AUDIT`。
3. 若 `total_raw_tokens = 0`：該輪模式標記 `AUDIT_ESTIMATE`。
4. 文件對外敘述一律使用「最新驗收快照時間點」。

## PM 執行硬規則
1. 主工作交給 `Gemini CLI` 分身執行。
2. 主代理只負責派工、驗收、收斂。
3. 第一優先目標：維持 `ci_gate PASS` 基線。

## 執行授權規則（Default Authorization）
1. 依路線圖直接開跑，不等待逐步確認。
2. 僅破壞性操作、憑證、規格衝突才暫停。

## AUTO-EXECUTE（No-Ask）硬規則
1. 預設模式：AUTO-EXECUTE。
2. 禁止詢問「是否繼續」。

---
*Created by Nex-CEx Orchestrator*
