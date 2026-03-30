# Nexus v9 Autonomic: Quick Start Guide | 快速上手指南 ⚡

---

## 1. Installation | 安裝

**[EN]** Nexus v9 requires Python 3.9+ and valid LLM API keys.
**[ZH]** Nexus v9 需要 Python 3.9+ 以及有效的 LLM API 金鑰。

```bash
# Clone the repository | 複製儲存庫
git clone https://github.com/nexus-ai/nexus-v9.git
cd nexus-v9

# Install dependencies | 安裝依賴
pip install -r requirements.txt

# Set up environment | 設定環境變數
export OPENAI_API_KEY="your_api_key"
export GOOGLE_API_KEY="your_gemini_key"
```

---

## 2. Autonomic Intelligence | 自主智慧

**[EN]** Nexus v9 introduces the **Crystal Analyzer**. After running some tasks, trigger a learning cycle to optimize routing weights.
**[ZH]** Nexus v9 引入了 **Crystal 分析器**。在執行一些任務後，啟動學習循環以優化路由權重。

```bash
# Analyze tracelogs and crystallize experience
# 分析執行日誌並結晶經驗
python3 scripts/nexus_cli.py nexus:crystal
```

---

## 3. Delivery Mode | 交付模式

**[EN]** `nexus:bug`, `nexus:feature`, and `nexus:runner` now support a delivery gate. Start with `--delivery-mode ask` so Nexus explicitly asks whether the current task needs high-standard delivery.

**[ZH]** `nexus:bug`、`nexus:feature`、`nexus:runner` 現在都支援交付門。建議從 `--delivery-mode ask` 開始，讓 Nexus 明確詢問這次任務是否需要高標交付。

```bash
# Ask before enforcing high-standard delivery on a bugfix
# 修 bug 前先詢問是否啟用高標交付
python3 scripts/engine/nexus_cli.py nexus:bug \
  --task "fix hydration error on dynamic routes" \
  --delivery-mode ask

# Ask before enforcing high-standard delivery on a feature
# 做功能前先詢問是否啟用高標交付
python3 scripts/engine/nexus_cli.py nexus:feature \
  --task "migrate session storage to redis" \
  --delivery-mode ask

# Run task orchestration with delivery confirmation
# 啟動任務編排並先確認交付標準
python3 scripts/engine/nexus_cli.py nexus:runner --delivery-mode ask
```

**[EN]** When `high` is selected, Nexus enforces completion verification before reporting delivery. For `bug` and `feature`, it can auto-suggest verification commands for Python, Rust, and Go projects when `--verify` is omitted, then prints the exact commands used and the delivery report paths.

**[ZH]** 當使用者選擇 `high` 時，Nexus 會在交付前強制完成驗證。對 `bug` 與 `feature` 來說，如果沒有給 `--verify`，系統會自動推建議驗證命令，支援 Python、Rust、Go，並在 CLI 顯示本次實際採用的驗證命令與交付報告路徑。

完整規則請見 [`docs/DELIVERY_CONTRACT_CN.md`](docs/DELIVERY_CONTRACT_CN.md)。

---

## 4. Self-Check / Self-Heal | 自檢與自癒

**[EN]** `nexus:check` now supports graded health audits. Use `quick` for a local snapshot, `standard` for a single benchmark replay, `high` for a stricter single-case health gate, and `full` for the heaviest benchmark lane. `nexus:self-heal` supports `dry-run`, `standard`, and `strict`.

**[ZH]** `nexus:check` 現在支援分級自檢。`quick` 只看本地健康快照，`standard` 會跑單 case benchmark，`high` 會用更嚴格門檻檢查單 case 健康，`full` 則走最重的 benchmark lane。`nexus:self-heal` 則支援 `dry-run`、`standard`、`strict`。

```bash
# Snapshot-only health check
# 只看快照的快速自檢
python3 scripts/engine/nexus_cli.py nexus:check --level quick

# Single-case benchmark health audit
# 單 case benchmark 健康審計
python3 scripts/engine/nexus_cli.py nexus:check --level standard

# Strict self-heal with health recovery requirement
# 嚴格自癒，要求修後健康恢復
python3 scripts/engine/nexus_cli.py nexus:self-heal --mode strict
```

---

## 5. Full-Chain Validation | 總合驗證

**[EN]** Use `--full-chain` to run a complete P-D-R-A cycle with integrated fallback support.
**[ZH]** 使用 `--full-chain` 執行完整的 P-D-R-A 循環，內建備援支援。

```bash
# Verify a feature end-to-end with fallback protection
# 具備備援保護的端到端功能驗證
python3 scripts/nexus_cli.py nexus:test --full-chain "voice narration UI"
```

---

## 4. Skills & Resilience | 職能與韌性 🧠🚀

**[EN]** Nexus v9 automatically routes to the best skill and provides **Fallback Resilience** if the primary skill fails.
**[ZH]** Nexus v9 自動路由至最佳職能，並在首選職能失效時提供**備援韌性**。

```bash
# Example: Fallback Chain in action
# 範例：備援鏈運作中
python3 scripts/nexus_cli.py nexus:feature --task "optimize database indexes" --bypass-cb
```
**[EN]** Observe the `🛡️ [v9 Override]` or `🎯 [SkillsRouter]` logs to see autonomic decisions.
**[ZH]** 觀察 `🛡️ [v9 Override]` 或 `🎯 [SkillsRouter]` 日誌，查看自主決策過程。

---

## 5. WarRoom v9 Telemetry | 戰情室遙測

**[EN]** Real-time monitoring of skill hit rates and performance metrics.
**[ZH]** 即時監控職能命中率與效能指標。

```bash
python3 scripts/nexus_cli.py nexus:warroom
```

---
**Build Smarter. Evolve Faster.** 🫡🦾💎🚀✨🚩
