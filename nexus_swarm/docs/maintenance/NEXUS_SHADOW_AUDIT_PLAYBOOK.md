# NEXUS_SHADOW_AUDIT_PLAYBOOK

## 什麼是影子稽核？
在不阻斷部署流程的前提下，讓分佈式蜂群對全量 PR 進行審計，用來累積數據並驗證準確度。

## 執行 SOP
1. **啟動集群**：設定 5-10 個 Node。
2. **開啟 Bypass**：`NEXUS_GATE_BYPASS=true`。
3. **分析統計**：每週從 `DiagnosticReport` 中提取 False Positive 比率。
