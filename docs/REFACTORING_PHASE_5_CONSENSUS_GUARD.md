# 🛡️ Nexus Consensus Guard v0.5 Spec

## 協同循環 (D-R-V-A-P)
1. **DISCOVER**: 每個 Swarm 定期廣播 Belief Fingerprint，計算 Drift Score。
2. **RECONCILE**: 針對高漂移信念提出 Bayesian 修訂提案。
3. **VOTE**: 基於 Trust Tier 與 Swarm Size 執行 CRDT 權重投票。
4. **ARBITRATE**: MUSE Oracle 或指揮官執行最終決斷。
5. **PROPAGATE**: 全網同步共識狀態，觸發 v0.4 自癒鏈。

## 技術指標
- **BELIEF_DRIFT_RATE**: 跨 Swarm 衝突率 (目標 < 5%)
- **CONSENSUS_TIME**: 達成共識時間 (目標 < 2min)
