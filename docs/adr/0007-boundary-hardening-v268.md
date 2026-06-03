# ADR 0007: v26.8 物理邊界加固與去特例化

## 狀態
已接受 (Accepted)

## 背景
雖然 v26.7 已經切分了 Bounded Contexts，但模組間仍存在潛在的橫向滲透風險。為了維持系統的「Good Taste」，我們需要將邊界硬化為 CI 可驗證的規則。

## 決策
1. **依賴鏈硬化**: 嚴格實施單向依賴 `feedback -> retry_policy -> calibration -> abstention -> evaluation`。
2. **去特例化**: 主控制器不得包含任何基於題目索引或特定失敗模式的 `if/else`。所有決策必須轉移至 Data-driven Policy。
3. **架構測試 (v6)**: 引入 `TestArchitectureBoundariesV4`，物理鎖定上述規則。

## 後果
- **優點**: 
  - 系統具備極高的穩定性與不可退化性。
  - 控制流變得極度透明。
- **缺點**: 
  - 增加了維護架構測試的開發成本。
