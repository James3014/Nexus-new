# 🛡️ Nexus Neural Architecture Search v0.7 Spec

## 進化循環 (O-M-S-D)
1. **OBSERVE**: 監控當前拓撲效能指標。
2. **MUTATE**: 隨機微調 Peering 密度、角色權重與共識閾值。
3. **SURVIVE**: 遺傳算法篩選 Top 20% 優秀基因。
4. **DEPLOY**: 部署最佳拓撲至主艦隊。

## 獎勵函數 (Reward Function)
Reward = (HitRate * 0.4) + (SpeedScore * 0.3) + (Efficiency * 0.2) + (Stability * 0.1)
