# Nexus v9 Skills Router Decision Spec (Autonomic Upgrade)

## Purpose

這份文件定義了 Nexus v9 `skills_router.py` 的自主決策規格。與 v7 不同，v9 不再僅依賴靜態規則，而是導入了**動態權重演進**與**備援韌性鏈**。

目標是：

- **自學習 (Autonomic)**: 透過 `Crystal` 分析器從歷史軌跡中自動優化權重。
- **高可用 (High Availability)**: 支援 Top-K 候選路由，實現職能失效時的自動切換。
- **可解釋性 (Explainability)**: 雖然有權重調整，但決策過程依然透明可讀。

## Design Principle

Nexus v9 採用「分數加權 + 環境感知」機制：

- **Top-K Routing**: 不再只選「最強」，而是選出「一群精英」，為 Fallback 提供冗餘。
- **Crystal Weighting**: 從 `autonomic_weights.json` 載入基準分與動態修正分。
- **Context Scoring**: 根據 `task_id`、`files` 等環境訊號即時加分。

## Core Scoring Logic

```text
total_score = 
  base_weight 
  + skill_adjustment_weight (from Crystal learning)
  + trigger_match_weight (high signal)
  + environment_bonus (context match)
```

## Selection Rule (Top-K Fallback)

1.  **Filtering**: 只過濾出符合當前 `phase` (P/D/R/A/C) 的技能。
2.  **Scoring**: 對候選技能進行綜合計分。
3.  **Top-K Sort**: 依分數高低排序，回傳前 K 個 (預設 K=3) 職能。
4.  **Sequential Execution**: 在 CLI 執行層，若 Top-1 失敗，自動嘗試 Top-2。

## Autonomic Learning (Crystal Analyzer)

v9 正式打破了「不使用歷史學習」的限制：

- **Success Signal**: 權重向上修正 (`success_rate` 越高，加權越大)。
- **Failure Signal**: 權重下調或標記風險。
- **Crystallization**: 透過 `nexus:crystal` 將反思結果固化至 `autonomic_weights.json`。

## Review Rule

Router 依然保持高度透明：

- **Decision Trace**: 在 `SkillsRouter.route_candidates` 中紀錄得分明細。
- **WarRoom Telemetry**: 實時追蹤各職能的「選中率」與「成功率」。

## Validation Case Table (v9)

| Case | Expected Top-1 | Fallback Candidate | Expected Behavior |
| :--- | :--- | :--- | :--- |
| Fuzzy Request | `nexus-planner-expert` | `writing-plans` | 自動產出 PRD 計畫 |
| UI/UX Polish | `nexus-design-polish` | `openui-ui-gen` | 若美學拋光失敗，轉向生成新 UI |
| Complex Debug | `nexus-debug-expert` | `codebase_investigator` | RCA 失敗則進行代碼掃描 |

## Practical Conclusion

Nexus v9 Skills Router 的目標是實現：

> **自主導航、失敗自癒、經驗結晶。**
