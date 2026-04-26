# 🧪 Wisdom Layer & Strategy Tuning
**[PHYSICAL_STATUS: STRATEGY_TUNING | COMPLEXITY_AWARE]**

## 1. 感知式任務路由
Nexus 透過 `ContextHub` 實作複雜度感應，決定是否啟動「高階治理模式」。

## ⚙️ 實體化優化規約
- **複雜度感應 (Sensing)**: 
    - **門檻**: `complexity_score > 0.7` 或包含關鍵字（如 `0-day`, `critical`）。
    - **動作**: 提升任務優先級並標註 `nas_autotune_needed`。
- **策略同步循環**: 
    - **實作**: `nexus/core/optimize/loop.py`。
    - **機制**: 自動將 `policy_updates.json` 的權重同步至 `skills_router.yaml`。
- **知識注入器 (KnowledgeInjector)**: 
    - 已從 `ContextHub` 拆分出獨立類別，負責高勝率技能推薦與歷史智慧注入。

## 2. 物理對位
- **配置**: `configs/skills_router.yaml`。
- **日誌**: 全面結構化日誌化，消滅 `print()`。

---
**[Source: Truth Realignment Audit Stage 7 - 2026-04-20]**
