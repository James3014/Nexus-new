# ADR 0008: 證據驅動的策略晉升 (Evidence-Driven Promotion)

## 狀態
已接受 (Accepted)

## 背景
Challenge Lane 的實驗性策略如果不加限制地進入 Baseline，可能會導致嚴重的回歸失敗。

## 決策
任何在 Challenge Lane 驗證有效的策略要晉升到 Baseline，必須滿足：
1. **Challenge Gain**: 在 13 題攻堅組中展現顯著的 Oracle Gap Recovery。
2. **Baseline No-Regression**: 必須通過 110 題的 `BaselineGate` 驗證。
3. **Receipt Evidence**: 具備完整的物理審計收據。
4. **ADR Update**: 更新對應的架構決策記錄。

## 後果
- **優點**: 
  - 保證了系統性能的穩定單調遞增。
  - 建立了科學的晉升機制。
- **缺點**: 
  - 延緩了新功能上線的速度。
