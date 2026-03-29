# Nexus v9 Autonomic: Zero-Drift Intelligence 🧬💎🚀

> **⚠️ Nexus 不是 Agent。Nexus 是戰甲 (Battlesuit)。**
> 任何 AI 模型穿上 Nexus 都會獲得 P-X-D-R-A-C 六階段自癒管線與學習系統。
> 學習系統屬於 Nexus（戰甲），不屬於穿它的模型。經驗累積在戰甲裡，換模型也不會丟失。

> **Beyond loops. Autonomic evolution, experience crystallization, and fallback resilience.**
> **超越循環。自主演進、經驗結晶與備援韌性。**

[![Success Rate](https://img.shields.io/badge/Live-99.5%25-brightgreen)](benchmark_report.json)
[![Status](https://img.shields.io/badge/Status-v9.0.0--Stable-blue)](v9_release_roadmap.md)
[![Engine](https://img.shields.io/badge/Engine-v9--Autonomic-red)](v9_build_spec.md)

---

## 🏟️ Overview | 概覽

**[EN]** Nexus v9 is the first autonomic AI development interface. It doesn't just execute loops; it learns from every execution trace to optimize its own decision weights and provides transparent fallback chains for mission-critical reliability.

**[ZH]** Nexus v9 是首個具備「自主演進」能力的 AI 開發介面。它不再只是單純執行循環，而是能從每一次的執行軌跡中學習，自動優化自身的決策權重，並為關鍵任務提供透明的備援鏈，確保極致的可靠性。

---

## 🏆 Key Features | 核心特性

*   **💎 Crystal Experience Crystallization**: Active learning from `tracelog.jsonl` to optimize router weights automatically.
    *   **Crystal 經驗結晶化**: 從 `tracelog.jsonl` 中主動學習，自動優化路由權重，實現職能演進。
*   **🚀 Fallback Resilience Chain**: Automatic switch to Top-K candidates if the primary skill fails.
    *   **備援韌性鏈**: 當首選職能失效時，自動切換至 Top-K 候選職能，確保任務零中斷。
*   **P-D-R-A-C Lifecycle**: Formalized autonomic state machine for zero-drift development.
    *   **P-D-R-A-C 生命週期**: 正式化自主演進狀態機，終結幻覺，實現精準研發。
*   **FlashJudge 8.0 (Enhanced)**: Higher fidelity gate with semantic drift detection.
    *   **FlashJudge 8.0 (強化版)**: 具備語義漂移偵測的高保真品質門禁。
*   **Stadium Explorer (WarRoom v9)**: Real-time telemetry for skill hit rates and autonomic adjustments.
    *   **戰場探索者 (戰情室 v9)**: 職能命中率與自學習調權的實時遙測面板。
*   **🌙 Night Shift Code Factory [V9]**: Fully integrated autonomic production line.
    *   **夜班代碼工廠 (v9)**: 深度整合自主演進邏輯，實現 24/7 無人值守高品質生產。
*   **Soul Protocols (Forbidden Transitions)**: Mechanized guardrails for absolute safety.
    *   **靈魂協議**: 機械化狀態機護欄，確保決策路徑 100% 正確。

---

## 🚀 Quick Start | 快速上手

```bash
# Fix a bug with v9 Autonomic Precision
# 以 v9 自主精度修復 Bug
python3 scripts/engine/nexus_cli.py nexus:bug --task "fix hydration error on dynamic routes" --delivery-mode ask --silent

# Build a feature with top-tier resilience
# 具備高韌性的新功能開發
python3 scripts/engine/nexus_cli.py nexus:feature --task "migrate session storage to redis" --domain django --delivery-mode ask

# Trigger autonomic learning cycle
# 啟動自主演進學習循環
python3 scripts/engine/nexus_cli.py nexus:crystal
```

---

## 🛡️ Verified Delivery | 高標交付

**[EN]** Nexus now supports a delivery gate across `bug`, `feature`, and `runner` flows. Use `--delivery-mode ask` to let the operator choose whether the current task requires high-standard delivery before completion is reported.

**[ZH]** Nexus 現在已在 `bug`、`feature`、`runner` 三條任務流接上交付門。使用 `--delivery-mode ask`，系統會在任務開始時主動詢問操作者，是否要啟用高標交付。

```bash
# Ask the operator whether this bugfix needs high-standard delivery
# 主動詢問這次 bug 修復是否需要高標交付
python3 scripts/engine/nexus_cli.py nexus:bug \
  --task "fix login callback regression" \
  --delivery-mode ask

# Ask the operator whether this feature needs high-standard delivery
# 主動詢問這次功能開發是否需要高標交付
python3 scripts/engine/nexus_cli.py nexus:feature \
  --task "add SSO audit trail" \
  --delivery-mode ask

# Run the task runner and ask before enforcing completion gate
# 在任務編排前先詢問是否啟用 completion gate
python3 scripts/engine/nexus_cli.py nexus:runner --delivery-mode ask
```

**[EN]** If the operator selects `high`, Nexus will enforce the completion gate before marking the task as delivered. For `bug` and `feature`, Nexus can auto-suggest verification commands for Python, Rust, and Go projects when `--verify` is omitted. The CLI also prints the verification commands it used and the generated delivery report paths.

**[ZH]** 若操作者選擇 `high`，Nexus 會在任務標記完成前強制通過 completion gate。對 `bug` 與 `feature` 而言，如果沒有提供 `--verify`，Nexus 會自動推建議驗證命令，支援 Python、Rust、Go 專案。CLI 也會直接輸出本次實際採用的驗證命令與生成的交付報告路徑。

更多規則請見 [`docs/DELIVERY_CONTRACT_CN.md`](docs/DELIVERY_CONTRACT_CN.md)。

For pilot chat usage, the canonical entry is now `scripts/nexus_pilot_cli.py`; `scripts/nexus_chat_cli.py` remains only as a compatibility shim.

Pilot 聊天入口現在以 `scripts/nexus_pilot_cli.py` 為正式名稱；`scripts/nexus_chat_cli.py` 僅保留相容 shim 角色。

---

## 📊 Full-Chain Verification | 總合驗證

```bash
# Run end-to-end P-D-R-A verification for a complex feature
# 為複雜功能執行端到端 P-D-R-A 總合驗證
nexus:test --full-chain "voice narration feature"
```

---

## 🗺️ Navigation | 導航

For detailed project architecture, refactor roadmap, and script ownership, please refer to the **[Project Index (docs/INDEX.md)](docs/INDEX.md)**.

關於專案架構、重構路線圖與腳本所有權的詳細資訊，請參閱 **[專案索引 (docs/INDEX.md)](docs/INDEX.md)**。

---
**Nexus v9: The engine that grows with the project.** 🫡🦾💎🚀✨🚩
**Nexus v9: 與項目共同成長的自主引擎。**

# Certified by v9 Autonomic Superpowers
