# NEXUS_SRE_RUNBOOK_V1

## 🚨 緊急處置：Fail-Open (Bypass)
如果 Nexus 導致 CI 阻斷，請立即在流水線環境變數中設定：
```bash
export NEXUS_GATE_BYPASS=true
```
**注意：在此模式下，所有 PR 將會預設通過。**

## 📊 重要監控指標 (Prometheus)
- **地址**: `http://localhost:9100/metrics`
- **關鍵指標**:
  - `nexus_tasks_processed_total`: 吞吐能力。
  - `nexus_tasks_failed_total`: 異常趨勢（突發增加代表有 Bug 或環境異常）。
  - `nexus_task_latency_seconds`: P95 延遲應 < 5s。

## 🔄 重啟方式
- **本地**: `pkill -SIGTERM swarm-manager` -> `swarm-manager -nodes nodes.json`
- **Systemd**: `sudo systemctl restart nexus-swarm-manager`
- **Kubernetes**: `kubectl rollout restart deployment/nexus-swarm`
