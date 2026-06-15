# 🛡️ Nexus Swarm SRE Runbook

[NEXUS v22 ACTIVE] - 本目錄包含了 Nexus Swarm 生產叢集的所有運維指令與自動化工具。

## 📖 目錄索引
- **[🚨 故障恢復 SOP](failover.md)**: 緊急情況下的重啟與恢復指南。
- **[📊 監控與儀表板](grafana-dashboard.json)**: Grafana 指標定義。
- **[🔄 備份與還原系統](backup.sh)**: `backup.sh` 與 `restore.sh` 操作說明。
- **[📉 治理與週報](weekly-shadow-report.py)**: `reports/` 目錄下的審計分析。

## 🛡️ 緊急應變入口 (Quick Access)
1. **檢查節點狀態**: `nexus:swarm status` 或 `curl :9100/cluster/status`
2. **重試失敗陰影審計**: `nexus:swarm shadow-audit --pr <num>`
3. **查看集群監控**: `kubectl port-forward svc/grafana 3000:80 -n monitoring`

## 📅 自動化排程
- **每日備份**: 建議 cron `0 2 * * * ./sre-runbook/backup.sh`
- **每週週報**: 建議 cron `0 9 * * 1 ./sre-runbook/weekly-shadow-report.py`

## 🛠️ 驗證工具
- **[ ✅ 一鍵全鏈驗證](deploy-p5-day2.sh)**: 執行 `deploy-p5-day2.sh` 以確保運維流程可用性。

## ⚖️ CLI 表面積與環境變數注入協定 (Parity-Safe Injection)
為防止在擴充 CLI 能力時破壞 AST `ParityAuditor` 的簽名審計，所有非 positional/keyword 預置參數必須通過環境變數注入 (Environment Variable Injection)，而不得修改 `run_shadow_eval` 的 Python 頂層函數簽名。
* **變數名稱**：`NEXUS_ABSTAIN_DATASET_PATH`
* **對應 CLI 參數**：`--abstain-dataset` (由 `scripts/bench/s2t_shadow_eval.py` 在 `__main__` 解析時自動寫入)
* **用途**：在不改變 Python 公開簽名的前提下，作為 parity-safe 的 runtime injection 管道傳遞可選的放棄評估資料集路徑。

