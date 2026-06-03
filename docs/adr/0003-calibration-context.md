# ADR 0003: 置信度校準 (Calibration) Context 的獨立化

## 狀態
已接受 (Accepted)

## 背景
大模型生成的 `confidence` 往往存在 Overconfidence 偏差。在 Nexus v26.5 中，棄權門檻被設置為硬編碼常數，這導致了部分「可挽救」的成功被安全棄權。

## 決策
建立獨立的 `Calibration` Context：
1. **數學校準**: 實施 Temperature Scaling (TS)，將信心值從原始分布修正至 Logit 空間。
2. **量化指標**: 以 ECE (Expected Calibration Error) 作為校準質量的衡量基準。
3. **策略驅動**: `AbstainPolicy` 現在基於「校準後的信心」進行決策。

## 後果
- **優點**: 
  - 顯著降低 ECE (實測降低 46%)。
  - 提高了棄權決策的安全性與精準度。
  - 為未來的 Isotonic Regression 等更複雜方法預留了擴展位。
- **缺點**: 
  - 校準模型需要額外的 Validation Split 數據進行擬合。
