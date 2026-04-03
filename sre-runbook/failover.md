# 🛡️ Nexus Swarm Failover & Recovery SOP

[NEXUS v22 ACTIVE] - 本文件定義了 Swarm 分佈式叢集的故障排除與恢復標準作業程序。

## 1. Manager 控制面故障
故障特徵：所有 Node 回報 `Heartbeat failed`，或 Desk 無法獲取叢集狀態。

### 🛡️ 滾動重啟 (Rolling Restart)
```bash
kubectl rollout restart deployment nexus-swarm-manager -n nexus
kubectl rollout status deployment nexus-swarm-manager -n nexus
```

## 2. NodeMission 區域性故障
故障特徵：特定 Region 的節點顯示為 `STALE` 或 `OFFLINE`。

### 🛡️ 區域重啟 (Region-aware Restart)
```bash
# 重啟 us-east 節點
kubectl rollout restart deployment nexus-swarm-node-us-east -n nexus
kubectl rollout status deployment nexus-swarm-node-us-east -n nexus --timeout=120s
```

## 3. PostgreSQL 數據層故障
故障特徵：Manager Log 報錯 `DB connection failed` 或數據無法更新。

### 🛡️ 主備切換 (Postgres Promote)
若主節點失效，手動提升從節點：
```bash
kubectl exec nexus-swarm-db-1 -n nexus -- pg_ctl promote
```

### 🛡️ 狀態一致性修復
```bash
kubectl patch statefulset nexus-swarm-db -p '{"spec":{"template":{"metadata":{"annotations":{"prometheus.io/scrape":"false"}}}}}'
```

## 4. 影子審計 (Shadow Audit) 異常
故障特徵：`calibration.json` 停止更新或誤報率異常。

### 🛡️ 重置治理狀態
```bash
uv run python scripts/engine/nexus_cli.py nexus:swarm shadow-audit --reset
```

## 5. 災難恢復 (Disaster Recovery)
若叢集完全崩潰，執行全量還原：
```bash
./sre-runbook/restore.sh <backup-archive.tar.gz> nexus
```
